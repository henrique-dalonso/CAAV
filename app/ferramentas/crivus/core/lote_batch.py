"""O "harness" de roteamento por urgência do Processamento em Lote +
submissão/coleta da API de Lote de verdade da Anthropic. Mesma
arquitetura de `nucleo_relatorios/core/robo_lote.py` (cliente, preparar,
submeter, coletar resultados), reescrita contra AnalisePublicacao/
LoteCrivus — não é literalmente compartilhada, é um model/fluxo
diferente.

Henrique, 2026-09-14: em vez de mandar toda a planilha pela API de Lote
(mais barata, mas pode levar de minutos a até 24h), cada linha é avaliada
pela URGÊNCIA a cada ciclo, com base nas datas reais da publicação:
- "urgente" (2 dias corridos desde a DATA DA PUBLICAÇÃO): vai pelo
  caminho síncrono/na hora, mesma função do Leitor Individual.
- "adiantado" (a 2ª data, quando o teor ficou disponível, vem 1 dia
  ANTES da 1ª — um caso raro mas real): continua elegível pro caminho de
  lote (tem margem de verdade), mas entra na FRENTE da fila de
  submissão — não é sobre CAMINHO, é sobre ORDEM (Henrique: "é um boost
  de moral pro escritório", não pode ficar perdido no meio de milhares
  de linhas).
- o resto: caminho de lote, ordem normal (mais antigo primeiro).

Uma linha só é avaliada ENQUANTO ainda está esperando despacho
(`batch_id IS NULL`) — depois de submetida pra API de Lote, não dá pra
"puxar de volta" se ela envelhecer e virar urgente no meio do caminho."""

from datetime import date
from pathlib import Path

from sqlmodel import select

from app.ferramentas.crivus.core.ia_cliente import analisar_publicacao, extrair_dados_e_uso, montar_parametros_mensagem
from app.ferramentas.crivus.core.lote_manager import gerar_planilha_saida
from app.ferramentas.crivus.db.lotes_crivus import (
    concluir_analise_de_lote,
    listar_analises_do_batch,
    listar_batch_ids_em_andamento,
    listar_pendentes_de_despacho,
    lote_ainda_tem_linha_processando,
    marcar_analise_de_lote_com_erro,
    marcar_batch_id,
    marcar_lote_concluido,
)
from app.ferramentas.crivus.db.models import AnalisePublicacao
from app.plataforma.db.session import obter_sessao

# Henrique, 2026-09-14, confirmado com exemplo (publicado 10/09, hoje
# 12/09 já é urgente): 2 dias corridos desde a 1ª data da planilha
# (DATA DA PUBLICAÇÃO) já é urgência. A 2ª data NUNCA entra nessa conta.
LIMITE_DIAS_URGENCIA = 2

# Linhas por chamada real de API de Lote — deliberadamente modesto (não
# o limite técnico da Anthropic, que é bem maior): manter a maior parte
# do backlog ainda "na fila de despacho" o máximo de tempo possível é o
# que permite o harness pegar uma linha que envelheceu pra urgente antes
# dela ficar presa dentro de um lote já enviado, sem volta.
TAMANHO_MAXIMO_LOTE_ANTHROPIC = 1000

# Quantas linhas urgentes processar por tick do robô, no máximo — evita
# um ciclo gigante travando (ex: primeira limpeza de uma base já bem
# atrasada) e evita estourar limite de taxa da API.
LIMITE_URGENTES_POR_CICLO = 20

# Pasta onde a planilha de saída de cada lote concluído é salva — mesmo
# padrão de dados/anexos/.
PASTA_SAIDA_LOTES = Path(__file__).resolve().parents[2] / "dados" / "lotes_saida"


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


def eh_urgente(analise, hoje=None):
    """`hoje` só existe pra facilitar teste (data fixa) — em produção
    nunca é passado, usa a data real."""
    if not analise.data_publicacao_original:
        return False  # nunca deveria acontecer pra origem="lote", defensivo
    hoje = hoje or date.today()
    return (hoje - analise.data_publicacao_original).days >= LIMITE_DIAS_URGENCIA


def eh_adiantado(analise):
    """2ª data (quando o teor ficou disponível) vindo 1 dia ANTES da 1ª
    (quando a publicação "subiu") — caso raro mas real, "boost de moral
    pro escritório". NÃO muda o caminho (continua elegível pro lote, tem
    margem de verdade) — só a ordem de submissão."""
    if not analise.data_importacao_original or not analise.data_publicacao_original:
        return False
    return analise.data_importacao_original < analise.data_publicacao_original


def _finalizar_lote_se_completo(lote_id):
    """Chamado depois de qualquer reconciliação (urgente ou via lote) que
    possa ter sido a última linha pendente de um lote — gera a planilha
    de saída no momento exato em que a última linha sai de
    "processando", sem lógica de geração-sob-demanda pra testar à parte."""
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


def _despachar_urgentes():
    """Linhas urgentes (2+ dias desde a publicação) vão pelo MESMO
    caminho síncrono do Leitor Individual — sem anexos (lote nunca tem
    anexo, decisão já tomada)."""
    pendentes = listar_pendentes_de_despacho()
    urgentes = [a for a in pendentes if eh_urgente(a)][:LIMITE_URGENTES_POR_CICLO]

    lotes_afetados = set()

    for analise in urgentes:
        lotes_afetados.add(analise.lote_id)
        try:
            dados_ia, uso_ia = analisar_publicacao(analise.teor_publicacao, anexos=None)
            concluir_analise_de_lote(analise.id, dados_ia, uso_ia)
        except Exception as erro:
            marcar_analise_de_lote_com_erro(analise.id, f"Falha ao analisar: {erro}")

    for lote_id in lotes_afetados:
        _finalizar_lote_se_completo(lote_id)


def _submeter_pendentes_por_lote(cliente):
    """O resto (não-urgente) vai pela API de Lote de verdade — mais
    barato. "Adiantados" entram primeiro na fila de submissão (mesma
    ordem relativa entre si preservada, já que listar_pendentes_de_despacho
    devolve do mais antigo pro mais novo); os demais mantêm ordem de
    chegada."""
    pendentes = listar_pendentes_de_despacho()
    nao_urgentes = [a for a in pendentes if not eh_urgente(a)]
    ordenados = sorted(nao_urgentes, key=lambda a: (not eh_adiantado(a),))

    grupo = ordenados[:TAMANHO_MAXIMO_LOTE_ANTHROPIC]
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
    """Um "tick" do vigia do Processamento em Lote. Ordem: (1) sempre
    coleta resultados de lotes físicos já em voo, mesmo com `lote_ativo`
    desligado (um batch já enviado pra Anthropic continua rodando lá de
    qualquer jeito — mesmo raciocínio do robô do Extratus); (2) se
    ligado, despacha urgentes na hora; (3) se ligado, submete o resto
    pela API de Lote. Só pede o cliente Anthropic quando há de fato
    trabalho pra fazer, pra não exigir ANTHROPIC_API_KEY num ciclo
    parado (nada em voo + lote desligado)."""
    if listar_batch_ids_em_andamento():
        _coletar_resultados(_obter_cliente())

    if not config.get("lote_ativo"):
        return

    _despachar_urgentes()
    _submeter_pendentes_por_lote(_obter_cliente())
