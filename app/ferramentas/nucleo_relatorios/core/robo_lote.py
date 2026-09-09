import os
import uuid
from pathlib import Path

import anthropic

from app.ferramentas.nucleo_relatorios.core.app_logger import registrar_log
from app.ferramentas.nucleo_relatorios.core.ia_cliente import (
    extrair_dados_e_uso,
    montar_diagnostico_com_triagem,
    montar_parametros_mensagem,
)
from app.ferramentas.nucleo_relatorios.core.pdf_isolado import executar_isolado
from app.ferramentas.nucleo_relatorios.core.pdf_manager import listar_pdfs
from app.ferramentas.nucleo_relatorios.core.pipeline import (
    finalizar_processamento,
    tratar_erro,
)
from app.ferramentas.nucleo_relatorios.core.prompt_manager import carregar_instrucoes_relatorio
from app.ferramentas.nucleo_relatorios.core.texto_manager import extrair_paginas_pdf
from app.ferramentas.nucleo_relatorios.db.checagem_fila import listar_aprovados_por_nome
from app.ferramentas.nucleo_relatorios.db.lotes import (
    criar_lote,
    listar_arquivos_ja_reivindicados,
    listar_itens_do_lote,
    listar_lotes_em_andamento,
    marcar_item_concluido,
    marcar_lote_concluido,
)
from app.ferramentas.nucleo_relatorios.db.models import FERRAMENTA_SLUG_PADRAO


def extrair_paginas_isolado(pdf):
    """Roda `extrair_paginas_pdf` (leitura bruta do PDF, `pypdf`) num
    processo separado — mesmo bug real do GIL já corrigido antes na
    checagem (ver checagem_lote.analisar_pdf_isolado, e o motivo completo
    em pdf_isolado.executar_isolado). Reaparecida aqui em 2026-08-11: essa
    leitura de PDF rodava dentro do loop do Robô (asyncio.to_thread, ver
    robo_watcher.py), sem isolamento — lia PDF grande e travava o site
    inteiro pelo tempo da leitura, não só o Robô.

    Henrique, diretoria, 2026-08-26: ANTES, esta função isolava
    `montar_diagnostico_com_triagem` inteira — mas essa função passou a
    também poder fazer uma chamada de REDE (resgate de página problemática
    por transcrição, quando `cliente` é passado). Chamada de rede não
    trava o GIL (motivo original do isolamento) e um cliente `anthropic`
    não é serializável entre processos — por isso agora só a extração
    bruta (de fato CPU-bound) é isolada; a triagem/resgate roda direto em
    `_preparar_novo_lote`, na mesma thread de fundo do ciclo do Robô
    (`asyncio.to_thread(rodar_ciclo_robo)`, já fora do processo principal
    do site)."""
    return executar_isolado(extrair_paginas_pdf, pdf)


def _obter_cliente():
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurada no .env. Configure a chave "
            "antes de ligar o robô com IA real."
        )

    return anthropic.Anthropic(api_key=api_key)


def _coletar_lotes_pendentes(cliente, config, tipo=None, ferramenta_slug=FERRAMENTA_SLUG_PADRAO):
    """Confere todo lote com status "enviado": se já terminou na Anthropic,
    processa cada resultado (sucesso ou erro) e fecha o lote. Devolve True
    se sobrar algum lote ainda em andamento depois disso (nesse caso não
    vale a pena tentar enviar um lote novo nesse ciclo — só um por vez)."""
    pasta_saida = config.get("pasta_saida")
    pasta_processados = config.get("pasta_processados")
    pasta_revisao = config.get("pasta_revisao")
    pasta_erros = config.get("pasta_erros")
    pasta_robo = Path(config.get("robo_pasta_entrada"))

    algum_ainda_em_andamento = False

    for lote in listar_lotes_em_andamento(ferramenta_slug=ferramenta_slug):
        info_lote = cliente.messages.batches.retrieve(lote.batch_id)

        if info_lote.processing_status != "ended":
            algum_ainda_em_andamento = True
            continue

        itens_por_custom_id = {
            item.custom_id: item for item in listar_itens_do_lote(lote.id, ferramenta_slug=ferramenta_slug)
        }

        for resultado in cliente.messages.batches.results(lote.batch_id):
            item = itens_por_custom_id.get(resultado.custom_id)

            if not item:
                registrar_log(
                    f"Resultado do lote {lote.batch_id} com custom_id "
                    f"desconhecido: {resultado.custom_id}"
                )
                continue

            caminho_pdf = pasta_robo / item.arquivo_pdf
            confianca = {"nivel": item.confianca_nivel, "motivo": item.confianca_motivo}

            if resultado.result.type == "succeeded":
                try:
                    dados_relatorio, uso_ia = extrair_dados_e_uso(resultado.result.message, via_batch=True)

                    if item.custo_transcricao_usd:
                        # Custo do resgate por transcrição foi pago ANTES do
                        # lote ser submetido (ver _preparar_novo_lote) — soma
                        # aqui pra não ficar invisível no Histórico/Custos.
                        uso_ia["custo_estimado_usd"] = round(
                            uso_ia["custo_estimado_usd"] + item.custo_transcricao_usd, 4
                        )
                        uso_ia["custo_transcricao_usd"] = item.custo_transcricao_usd

                    finalizar_processamento(
                        caminho_pdf,
                        item.processo_detectado,
                        confianca,
                        dados_relatorio,
                        uso_ia,
                        pasta_saida,
                        pasta_processados,
                        pasta_revisao,
                        pasta_erros,
                        usuario_id=None,
                        solicitante_id=item.solicitante_id,
                        tipo=tipo,
                        ferramenta_slug=ferramenta_slug,
                    )
                    marcar_item_concluido(item.id, "sucesso", ferramenta_slug=ferramenta_slug)
                except Exception as erro:
                    tratar_erro(
                        caminho_pdf, item.processo_detectado, "erro_ia", erro, pasta_erros,
                        solicitante_id=item.solicitante_id, ferramenta_slug=ferramenta_slug,
                    )
                    marcar_item_concluido(item.id, "erro", ferramenta_slug=ferramenta_slug)
            else:
                # "errored", "expired" ou "canceled" — falha do lado da
                # Anthropic pra esse item específico, não derruba os
                # outros itens do mesmo lote.
                mensagem = getattr(resultado.result, "error", None) or (
                    f"Item do lote terminou como '{resultado.result.type}'."
                )
                tratar_erro(
                    caminho_pdf, item.processo_detectado, "erro_ia", mensagem, pasta_erros,
                    solicitante_id=item.solicitante_id, ferramenta_slug=ferramenta_slug,
                )
                marcar_item_concluido(item.id, "erro", ferramenta_slug=ferramenta_slug)

        marcar_lote_concluido(lote.id, ferramenta_slug=ferramenta_slug)

    return algum_ainda_em_andamento


def _preparar_novo_lote(config, cliente, tipo=None, ferramenta_slug=FERRAMENTA_SLUG_PADRAO):
    """Olha os PDFs em robo_pasta_entrada ainda não reivindicados por
    nenhum lote (passado ou presente) e monta os itens elegíveis pra um
    lote novo. Arquivos que já estourarem os limites de segurança
    (digitalizado e grande demais, ou processo grande demais pro contexto)
    são tratados como erro na hora, sem entrar no lote.

    Só considera arquivo com checagem "aprovada" (checagem_lote.py, que
    roda muito mais rápido que o robô, em segundo plano) — nome
    duplicado, processo já processado noutro lugar, ou processo não
    encontrado ficam de fora até o painel de Conferências resolver.
    Reaproveita o processo/confiança já detectados na checagem em vez
    de detectar tudo de novo aqui.

    `cliente` é usado aqui (não só depois, na submissão do lote) porque
    `montar_diagnostico_com_triagem` pode precisar dele pra resgatar
    páginas problemáticas por transcrição ANTES do PDF entrar no lote —
    ver docstring de `extrair_paginas_isolado`."""
    pasta_robo = config.get("robo_pasta_entrada")
    pasta_erros = config.get("pasta_erros")

    ja_reivindicados = listar_arquivos_ja_reivindicados(ferramenta_slug=ferramenta_slug)
    aprovados = listar_aprovados_por_nome(ferramenta_slug=ferramenta_slug)
    instrucoes = carregar_instrucoes_relatorio(tipo=tipo)

    itens_para_lote = []

    for pdf in listar_pdfs(pasta_robo):
        if pdf.name in ja_reivindicados:
            continue

        checagem = aprovados.get(pdf.name)

        if checagem is None:
            # Ainda não passou pela checagem, ou passou e não foi
            # aprovado — não é elegível ainda. Nada se perde: a checagem
            # roda a cada poucos segundos, então na prática já deve
            # estar aprovado bem antes do robô sequer tentar de novo.
            continue

        processo = checagem.processo_detectado
        confianca = {"nivel": checagem.confianca_nivel, "motivo": checagem.confianca_motivo}

        try:
            # Triagem de anexos de listagem de terceiros (ver
            # ia_cliente.montar_diagnostico_com_triagem) roda pro Robô
            # também — reduz custo e evita erro de "processo grande
            # demais" quando o anexo irrelevante é a causa. Se alguma
            # página foi removida, a confiança cai pra "revisão" na hora
            # (mesmo princípio do fluxo manual em pipeline.py) — nunca
            # cai em "alta confiança" sozinho depois de uma triagem.
            #
            # `cliente` passado aqui também tenta RESGATAR página sem
            # texto confiável por transcrição antes de decidir se o
            # documento "parece digitalizado" — ver docstring de
            # montar_diagnostico_com_triagem. Extração bruta isolada em
            # processo separado (CPU-bound); a triagem/resgate em si (que
            # pode fazer uma chamada de rede) roda aqui mesmo, na thread
            # de fundo do ciclo do Robô.
            paginas, total_paginas = extrair_paginas_isolado(pdf)
            diagnostico, _, paginas_excluidas_triagem, paginas_transcritas, custo_transcricao_usd = (
                montar_diagnostico_com_triagem(
                    pdf, paginas=paginas, total_paginas=total_paginas, cliente=cliente
                )
            )
            parametros = montar_parametros_mensagem(pdf, processo, instrucoes, cliente, diagnostico=diagnostico, tipo=tipo)
        except Exception as erro:
            tratar_erro(
                pdf, processo, "erro_ia", erro, pasta_erros,
                solicitante_id=checagem.solicitante_id, ferramenta_slug=ferramenta_slug,
            )
            continue

        if paginas_excluidas_triagem or paginas_transcritas:
            motivos = []
            if paginas_excluidas_triagem:
                motivos.append(
                    f"{len(paginas_excluidas_triagem)} página(s) removida(s) automaticamente da análise "
                    "(anexo de listagem de terceiros e/ou falha na extração de texto de página)"
                )
            if paginas_transcritas:
                motivos.append(
                    f"{len(paginas_transcritas)} página(s) sem texto confiável tiveram o conteúdo "
                    "resgatado por transcrição de IA (caminho novo, ainda em validação)"
                )
            confianca = {"nivel": "revisao", "motivo": "; ".join(motivos) + "."}

        itens_para_lote.append({
            "custom_id": uuid.uuid4().hex,
            "arquivo_pdf": pdf.name,
            "processo_detectado": processo,
            "confianca_nivel": confianca.get("nivel"),
            "confianca_motivo": confianca.get("motivo"),
            "params": parametros,
            "custo_transcricao_usd": custo_transcricao_usd,
            # Ver docstring de Job.solicitante_id — carregado desde
            # ChecagemFila (preenchido no upload, ver checagem_fila.
            # registrar_pendente), repassado adiante pro Job final.
            "solicitante_id": checagem.solicitante_id,
        })

    return itens_para_lote


def _submeter_lote(cliente, itens, ferramenta_slug=FERRAMENTA_SLUG_PADRAO):
    lote_anthropic = cliente.messages.batches.create(
        requests=[
            {"custom_id": item["custom_id"], "params": item["params"]}
            for item in itens
        ]
    )

    lote = criar_lote(lote_anthropic.id, itens, ferramenta_slug=ferramenta_slug)

    registrar_log(
        f"Lote enviado ao Robô: {lote_anthropic.id} ({len(itens)} arquivo(s))."
    )

    return lote


def rodar_ciclo_robo(config, tipo=None, ferramenta_slug=FERRAMENTA_SLUG_PADRAO):
    """Um "tick" do vigia do Robô — chamado periodicamente pelo
    `robo_watcher.py`, que passa `config` já carregado do
    `config_manager` DAQUELA TELA (nunca carregado aqui dentro) — achado
    real, 2026-09-09: até esta correção, esta função sempre importava e
    chamava `config_manager.carregar_config()` do módulo `extratus`
    diretamente, então TODA tela que usa o motor compartilhado (Aburesi
    desde a migração da manhã, Emenda desde a tela nova à noite) estava
    lendo/gravando nas pastas do Extratus-Relatórios por engano — nunca
    nas próprias. Corrigido derrubando esse import fixo e recebendo
    `config` de fora, já carregado pela config_manager certa.

    Fecha lote(s) já enviados pra Anthropic SEMPRE,
    mesmo com `robo_ativo` desligado — um lote, uma vez enviado, continua
    rodando do lado da Anthropic independente do interruptor local; se a
    coleta só acontecesse com o robô ligado, um lote que terminou depois
    de alguém desligar a chave ficava preso pra sempre (nunca virava
    relatório, nunca saía da tela como "em andamento"). Só abrir lote NOVO
    é que respeita `robo_ativo`.

    Vários lotes podem ficar em voo ao mesmo tempo, de propósito — até
    2026-09-09 o robô só deixava existir um lote "enviado" por vez, então
    um único caso isolado abrindo um lote pequeno segurava dezenas de
    casos novos esperando ele fechar (Henrique, 2026-09-09: "isso está
    acarretando em congestionamento e demora excessiva"). Nada aqui
    depende de "o" lote: `_coletar_lotes_pendentes` já percorre todos os
    lotes em andamento, e `_preparar_novo_lote` já exclui (via
    `listar_arquivos_ja_reivindicados`) qualquer arquivo já reivindicado
    por QUALQUER lote ainda "enviado" — então abrir um lote novo a cada
    ciclo, mesmo com outros ainda em voo, nunca duplica processamento.
    Volume real do escritório está muito longe do limite da Anthropic
    pra requisições de batch em fila (200 mil a 500 mil, dependendo do
    tier, por organização inteira — não é um limite por lote)."""
    if listar_lotes_em_andamento(ferramenta_slug=ferramenta_slug):
        cliente = _obter_cliente()
        _coletar_lotes_pendentes(cliente, config, tipo=tipo, ferramenta_slug=ferramenta_slug)

    if not config.get("robo_ativo"):
        return

    cliente = _obter_cliente()
    itens = _preparar_novo_lote(config, cliente, tipo=tipo, ferramenta_slug=ferramenta_slug)

    if itens:
        _submeter_lote(cliente, itens, ferramenta_slug=ferramenta_slug)
