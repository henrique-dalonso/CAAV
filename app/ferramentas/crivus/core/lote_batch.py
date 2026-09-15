"""Roteamento por atraso + qualidade do Processamento em Lote, e
submissão/coleta da API de Lote de verdade da Anthropic. Mesma
arquitetura de `nucleo_relatorios/core/robo_lote.py` (cliente, preparar,
submeter, coletar resultados), reescrita contra AnalisePublicacao/
LoteCrivus — não é literalmente compartilhada, é um model/fluxo
diferente.

Henrique, coordenador, 2026-09-14 — correção no dia seguinte ao ar (o
desenho original tinha um caminho síncrono/"urgente" pra casos
atrasados; foi INVERTIDO por decisão do coordenador responsável):

- Só a 1ª data da planilha (DATA DA PUBLICAÇÃO) importa — "podemos
  ignorar 100% a segunda data" (DATA DA IMPORTAÇÃO). Ela ainda é lida e
  guardada (ver lote_manager.py), mas não entra em NENHUMA decisão de
  roteamento ou ordem aqui.
- Uma linha com 2+ dias corridos desde a publicação está "atrasada".
  Atrasada NUNCA vai pra IA — nem na hora, nem depois: é marcada
  `status="atrasado"` e excluída de propósito do processamento
  automático, pra ser tratada manualmente pelo time. Motivo do
  coordenador: dar prioridade ao caso E evitar que uma movimentação nova
  tenha acontecido no meio tempo do atraso sem ninguém perceber (uma IA
  lendo o teor antigo não saberia disso).

Henrique, diretoria, 2026-09-15 — 2ª exclusão, por QUALIDADE do teor (a
diretoria viu o Crivus e pediu mais rigor: só processar pela análise
completa o que for "nitidamente útil", garantindo qualidade máxima; o
resto é descartado e apontado na planilha de saída). Harness de 2
camadas, cada uma só roda pra quem sobrou da anterior:
1. regra grátis (`_teor_obviamente_invalido`): teor curto demais pra ser
   um texto de verdade (ex: extração truncada) é descartado na hora, sem
   IA nenhuma.
2. pré-análise barata (`avaliar_confiabilidade_teor`, MODELO_TRIAGEM em
   ia_cliente.py): lê só o teor e decide se dá pra confiar numa análise
   baseada nisso. Reprovado = descartado, com o motivo que a própria IA
   deu. Aprovado = segue pendente, `_submeter_pendentes_por_lote` pega
   em seguida no mesmo ciclo.
Ambas viram `status="descartado"` — categoria própria (nem "erro", que é
falha técnica, nem "atrasado", que é por prazo).

Ordem de cada ciclo (Henrique aprovou 2026-09-15): atraso (grátis) ->
qualidade camada 1 (grátis) -> qualidade camada 2 (IA barata) -> só
então análise completa (API de Lote). "Atrasado" e "descartado" viram
STATUS="EXECUTAR MANUALMENTE" na planilha de saída (ver
gerar_planilha_saida em lote_manager.py), diferenciados só pelo MOTIVO.

Uma linha só é avaliada ENQUANTO ainda está esperando despacho
(`batch_id IS NULL`) — depois de submetida pra API de Lote, não dá pra
"puxar de volta" se ela envelhecer e ficar atrasada no meio do caminho."""

from datetime import date
from pathlib import Path

from sqlmodel import select

from app.ferramentas.crivus.core.ia_cliente import (
    avaliar_confiabilidade_teor,
    extrair_dados_e_uso,
    montar_parametros_mensagem,
)
from app.ferramentas.crivus.core.lote_manager import gerar_planilha_saida
from app.ferramentas.crivus.db.lotes_crivus import (
    concluir_analise_de_lote,
    listar_analises_do_batch,
    listar_batch_ids_em_andamento,
    listar_pendentes_de_despacho,
    lote_ainda_tem_linha_processando,
    marcar_analise_atrasada,
    marcar_analise_de_lote_com_erro,
    marcar_analise_descartada,
    marcar_batch_id,
    marcar_lote_concluido,
    registrar_custo_triagem,
)
from app.ferramentas.crivus.db.models import AnalisePublicacao
from app.plataforma.db.session import obter_sessao

# Henrique, coordenador, 2026-09-14, confirmado com exemplo (publicado
# 10/09, hoje 12/09 já é atrasado): 2 dias corridos desde a 1ª data da
# planilha (DATA DA PUBLICAÇÃO) já conta como atraso.
LIMITE_DIAS_ATRASO = 2

# Henrique, diretoria, 2026-09-15: camada 1 do filtro de qualidade —
# conservador de propósito (Henrique: "garantindo que não teremos
# prejuízo por remover um teor útil por engano"). Confirmado com dado
# real: o menor teor LEGÍTIMO visto até agora tinha 130+ caracteres; o
# único teor genuinamente truncado/inválido visto tinha 29. 60 fica bem
# no meio, com folga de sobra pros dois lados.
TAMANHO_MINIMO_TEOR = 60

# Quantas pré-análises de triagem (camada 2, IA) rodar por ciclo, no
# máximo — cada uma é uma chamada de rede em tempo real; sem limite, um
# backlog grande seguraria o tick inteiro. Sobra fica pro próximo ciclo
# (60s depois), sem perda nenhuma.
LIMITE_TRIAGEM_POR_CICLO = 50

# Linhas por chamada real de API de Lote — deliberadamente modesto (não
# o limite técnico da Anthropic, que é bem maior): manter a maior parte
# do backlog ainda "na fila de despacho" o máximo de tempo possível é o
# que permite o harness pegar uma linha que envelheceu e ficou atrasada
# antes dela ficar presa dentro de um lote já enviado, sem volta.
TAMANHO_MAXIMO_LOTE_ANTHROPIC = 1000

# Pasta onde a planilha de saída de cada lote concluído é salva — mesmo
# padrão de dados/anexos/. Este arquivo mora em crivus/core/ (1 nível
# abaixo de crivus/), diferente de leitor_individual.py (crivus/web/
# routes/, 2 níveis abaixo) — daí parents[1] aqui, não parents[2].
PASTA_SAIDA_LOTES = Path(__file__).resolve().parents[1] / "dados" / "lotes_saida"


def _obter_cliente():
    import os

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurada no .env. Configure a chave "
            "antes de ligar o Processamento em Lote."
        )
    return anthropic.Anthropic(api_key=api_key)


def eh_atrasado(analise, hoje=None):
    """`hoje` só existe pra facilitar teste (data fixa) — em produção
    nunca é passado, usa a data real. Só considera
    `data_publicacao_original` (1ª data) — a 2ª data da planilha é
    ignorada 100%, por decisão do coordenador (2026-09-14)."""
    if not analise.data_publicacao_original:
        return False  # nunca deveria acontecer pra origem="lote", defensivo
    hoje = hoje or date.today()
    return (hoje - analise.data_publicacao_original).days >= LIMITE_DIAS_ATRASO


def _finalizar_lote_se_completo(lote_id):
    """Chamado depois de qualquer reconciliação (marcação de atrasado ou
    conclusão via lote) que possa ter sido a última linha pendente de um
    lote — gera a planilha de saída no momento exato em que a última
    linha sai de "processando", sem lógica de geração-sob-demanda pra
    testar à parte."""
    if lote_ainda_tem_linha_processando(lote_id):
        return

    with obter_sessao() as sessao:
        todas_as_linhas = sessao.exec(
            select(AnalisePublicacao).where(AnalisePublicacao.lote_id == lote_id)
        ).all()

    caminho_saida = PASTA_SAIDA_LOTES / f"resultado_lote_{lote_id}.xlsx"
    gerar_planilha_saida(todas_as_linhas, caminho_saida)
    marcar_lote_concluido(lote_id, caminho_saida)


def _coletar_resultados(cliente):
    """Pra cada lote físico (batch_id) ainda em voo na Anthropic: se já
    terminou, reconcilia cada resultado (sucesso ou erro) contra a
    AnalisePublicacao correspondente (custom_id == str(analise.id)) — um
    resultado ruim nunca impede os outros de serem processados. Roda
    SEMPRE, mesmo com `lote_ativo` desligado (um batch já enviado pra
    Anthropic continua rodando lá de qualquer jeito)."""
    for batch_id in listar_batch_ids_em_andamento():
        info_lote = cliente.messages.batches.retrieve(batch_id)
        if info_lote.processing_status != "ended":
            continue

        analises_por_custom_id = {str(a.id): a for a in listar_analises_do_batch(batch_id)}
        lotes_afetados = set()

        for resultado in cliente.messages.batches.results(batch_id):
            analise = analises_por_custom_id.get(resultado.custom_id)
            if not analise:
                continue

            lotes_afetados.add(analise.lote_id)

            if resultado.result.type == "succeeded":
                try:
                    dados_ia, uso_ia = extrair_dados_e_uso(resultado.result.message, via_batch=True)
                    concluir_analise_de_lote(analise.id, dados_ia, uso_ia)
                except Exception as erro:
                    marcar_analise_de_lote_com_erro(analise.id, f"Falha ao interpretar resultado: {erro}")
            else:
                mensagem = getattr(resultado.result, "error", None) or (
                    f"Item do lote terminou como '{resultado.result.type}'."
                )
                marcar_analise_de_lote_com_erro(analise.id, str(mensagem))

        for lote_id in lotes_afetados:
            _finalizar_lote_se_completo(lote_id)


def _marcar_atrasados_para_manual():
    """Henrique, coordenador, 2026-09-14: linhas com 2+ dias de atraso
    NUNCA vão pra IA — são excluídas de propósito do processamento
    automático e marcadas pra tratamento manual do time (ver docstring
    do módulo). Sem chamada de IA nenhuma aqui, só marcação local."""
    pendentes = listar_pendentes_de_despacho()
    atrasados = [a for a in pendentes if eh_atrasado(a)]

    lotes_afetados = set()

    for analise in atrasados:
        lotes_afetados.add(analise.lote_id)
        dias = (date.today() - analise.data_publicacao_original).days
        marcar_analise_atrasada(
            analise.id,
            f"Publicado há {dias} dias. Prazo de {LIMITE_DIAS_ATRASO} dias estourado, encaminhado para tratamento manual.",
        )

    for lote_id in lotes_afetados:
        _finalizar_lote_se_completo(lote_id)


def _teor_obviamente_invalido(teor):
    """Camada 1 do filtro de qualidade — grátis, sem IA. Ver
    TAMANHO_MINIMO_TEOR."""
    return len((teor or "").strip()) < TAMANHO_MINIMO_TEOR


def _filtrar_por_qualidade():
    """Henrique, diretoria, 2026-09-15: só processar pela análise
    completa (cara) o que for "nitidamente útil" — 2 camadas, ver
    docstring do módulo. Roda depois de `_marcar_atrasados_para_manual`
    (não faz sentido gastar com triagem numa linha que já vai ser
    marcada atrasada de qualquer jeito) e antes de
    `_submeter_pendentes_por_lote` (só quem sobra daqui é elegível pra
    análise completa).

    `custo_triagem_usd IS NOT NULL` é o sinal de "já passou pela triagem
    e foi aprovada" — sem checar isso aqui, uma linha aprovada num ciclo
    mas ainda não submetida (ex: backlog grande) seria reavaliada de
    novo a cada tick, gastando com IA repetidamente à toa."""
    pendentes = [a for a in listar_pendentes_de_despacho() if a.custo_triagem_usd is None]

    avaliados_nesta_rodada = 0
    lotes_afetados = set()

    for analise in pendentes:
        if _teor_obviamente_invalido(analise.teor_publicacao):
            lotes_afetados.add(analise.lote_id)
            marcar_analise_descartada(analise.id, "Conteúdo muito curto ou inválido para análise.")
            continue

        if avaliados_nesta_rodada >= LIMITE_TRIAGEM_POR_CICLO:
            continue

        avaliados_nesta_rodada += 1
        try:
            confiavel, motivo, uso_triagem = avaliar_confiabilidade_teor(analise.teor_publicacao)
        except Exception:
            # Falha técnica na pré-análise (rede, API) não é a mesma
            # coisa que "teor ruim" — não descarta, deixa pendente pra
            # tentar de novo no próximo ciclo.
            continue

        if confiavel:
            registrar_custo_triagem(analise.id, uso_triagem["custo_estimado_usd"])
        else:
            lotes_afetados.add(analise.lote_id)
            marcar_analise_descartada(
                analise.id,
                motivo or "Teor insuficiente para uma análise confiável.",
                custo_triagem_usd=uso_triagem["custo_estimado_usd"],
            )

    for lote_id in lotes_afetados:
        _finalizar_lote_se_completo(lote_id)


def _submeter_pendentes_por_lote(cliente):
    """O resto (não atrasado, já aprovado na triagem de qualidade) vai
    pela API de Lote de verdade — mais barato. Ordem natural de chegada
    (mais antigo primeiro), já garantida por `listar_pendentes_de_despacho`.

    `custo_triagem_usd IS NOT NULL` exige que a linha já tenha PASSADO
    pela camada 2 do filtro de qualidade com aprovação — sem isso, uma
    linha ainda não avaliada (ou que falhou tecnicamente na pré-análise
    nesse mesmo ciclo) seria submetida direto pra análise completa sem
    nunca ter sido de fato aprovada."""
    pendentes = listar_pendentes_de_despacho()
    elegiveis = [a for a in pendentes if not eh_atrasado(a) and a.custo_triagem_usd is not None]

    grupo = elegiveis[:TAMANHO_MAXIMO_LOTE_ANTHROPIC]
    if not grupo:
        return

    requisicoes = []
    ids_validos = []
    for analise in grupo:
        try:
            parametros = montar_parametros_mensagem(analise.teor_publicacao, anexos=None)
        except Exception as erro:
            marcar_analise_de_lote_com_erro(analise.id, f"Falha ao preparar envio: {erro}")
            continue
        requisicoes.append({"custom_id": str(analise.id), "params": parametros})
        ids_validos.append(analise.id)

    if not requisicoes:
        return

    lote_anthropic = cliente.messages.batches.create(requests=requisicoes)
    marcar_batch_id(ids_validos, lote_anthropic.id)


def rodar_ciclo_lote(config):
    """Um "tick" do vigia do Processamento em Lote. Ordem (Henrique
    aprovou 2026-09-15): (1) sempre coleta resultados de lotes físicos
    já em voo, mesmo com `lote_ativo` desligado (um batch já enviado pra
    Anthropic continua rodando lá de qualquer jeito — mesmo raciocínio
    do robô do Extratus); (2) se ligado, marca atrasados (sem IA
    nenhuma); (3) se ligado, filtra por qualidade (camada 1 grátis +
    camada 2 IA barata); (4) se ligado, submete quem sobrou pela API de
    Lote (cara). Cada etapa só vê quem passou pela anterior. Só pede o
    cliente Anthropic quando há de fato trabalho pra fazer, pra não
    exigir ANTHROPIC_API_KEY num ciclo parado (nada em voo + lote
    desligado)."""
    if listar_batch_ids_em_andamento():
        _coletar_resultados(_obter_cliente())

    if not config.get("lote_ativo"):
        return

    _marcar_atrasados_para_manual()
    _filtrar_por_qualidade()
    _submeter_pendentes_por_lote(_obter_cliente())
