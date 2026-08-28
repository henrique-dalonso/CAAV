import os
import uuid
from pathlib import Path

import anthropic

from app.ferramentas.extratus_aburesi.core.app_logger import registrar_log
from app.ferramentas.extratus_aburesi.core.config_manager import carregar_config
from app.ferramentas.extratus_aburesi.core.ia_cliente import (
    extrair_dados_e_uso,
    montar_diagnostico_com_triagem,
    montar_parametros_mensagem,
)
from app.ferramentas.extratus_aburesi.core.pdf_isolado import executar_isolado
from app.ferramentas.extratus_aburesi.core.pdf_manager import listar_pdfs
from app.ferramentas.extratus_aburesi.core.pipeline import (
    finalizar_processamento,
    tratar_erro,
)
from app.ferramentas.extratus_aburesi.core.prompt_manager import carregar_instrucoes_relatorio
from app.ferramentas.extratus_aburesi.core.texto_manager import extrair_paginas_pdf
from app.ferramentas.extratus_aburesi.db.checagem_fila import listar_aprovados_por_nome
from app.ferramentas.extratus_aburesi.db.lotes import (
    criar_lote,
    listar_arquivos_ja_reivindicados,
    listar_itens_do_lote,
    listar_lotes_em_andamento,
    marcar_item_concluido,
    marcar_lote_concluido,
)


def extrair_paginas_isolado(pdf):
    """Ver docstring equivalente em app/ferramentas/extratus/core/
    robo_lote.py (Extratus - Relatórios) — mesmo bug real (GIL do
    pypdf travando o site inteiro), mesma correção; mesma mudança
    2026-08-26 (só a extração bruta é isolada, não mais a
    triagem/resgate inteira, que pode fazer chamada de rede)."""
    return executar_isolado(extrair_paginas_pdf, pdf)


def _obter_cliente():
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurada no .env. Configure a chave "
            "antes de ligar o robô com IA real."
        )

    return anthropic.Anthropic(api_key=api_key)


def _coletar_lotes_pendentes(cliente, config):
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

    for lote in listar_lotes_em_andamento():
        info_lote = cliente.messages.batches.retrieve(lote.batch_id)

        if info_lote.processing_status != "ended":
            algum_ainda_em_andamento = True
            continue

        itens_por_custom_id = {item.custom_id: item for item in listar_itens_do_lote(lote.id)}

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
                    )
                    marcar_item_concluido(item.id, "sucesso")
                except Exception as erro:
                    tratar_erro(
                        caminho_pdf, item.processo_detectado, "erro_ia", erro, pasta_erros,
                        solicitante_id=item.solicitante_id,
                    )
                    marcar_item_concluido(item.id, "erro")
            else:
                # "errored", "expired" ou "canceled" — falha do lado da
                # Anthropic pra esse item específico, não derruba os
                # outros itens do mesmo lote.
                mensagem = getattr(resultado.result, "error", None) or (
                    f"Item do lote terminou como '{resultado.result.type}'."
                )
                tratar_erro(
                    caminho_pdf, item.processo_detectado, "erro_ia", mensagem, pasta_erros,
                    solicitante_id=item.solicitante_id,
                )
                marcar_item_concluido(item.id, "erro")

        marcar_lote_concluido(lote.id)

    return algum_ainda_em_andamento


def _preparar_novo_lote(config, cliente):
    """Ver docstring equivalente em app/ferramentas/extratus/core/
    robo_lote.py (Extratus - Relatórios) — mesma lógica, `cliente` usado
    aqui pra permitir o resgate de páginas problemáticas por transcrição
    ANTES do PDF entrar no lote."""
    pasta_robo = config.get("robo_pasta_entrada")
    pasta_erros = config.get("pasta_erros")

    ja_reivindicados = listar_arquivos_ja_reivindicados()
    aprovados = listar_aprovados_por_nome()
    instrucoes = carregar_instrucoes_relatorio()

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
            # `cliente` também tenta RESGATAR página sem texto confiável
            # por transcrição antes de decidir se o documento "parece
            # digitalizado" — ver docstring de montar_diagnostico_com_
            # triagem. Extração bruta isolada em processo separado
            # (CPU-bound); a triagem/resgate em si (rede) roda aqui.
            paginas, total_paginas = extrair_paginas_isolado(pdf)
            diagnostico, _, paginas_excluidas_triagem, paginas_transcritas, custo_transcricao_usd = (
                montar_diagnostico_com_triagem(
                    pdf, paginas=paginas, total_paginas=total_paginas, cliente=cliente
                )
            )
            parametros = montar_parametros_mensagem(pdf, processo, instrucoes, diagnostico=diagnostico)
        except Exception as erro:
            tratar_erro(pdf, processo, "erro_ia", erro, pasta_erros, solicitante_id=checagem.solicitante_id)
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
            "solicitante_id": checagem.solicitante_id,
        })

    return itens_para_lote


def _submeter_lote(cliente, itens):
    lote_anthropic = cliente.messages.batches.create(
        requests=[
            {"custom_id": item["custom_id"], "params": item["params"]}
            for item in itens
        ]
    )

    lote = criar_lote(lote_anthropic.id, itens)

    registrar_log(
        f"Lote enviado ao Robô: {lote_anthropic.id} ({len(itens)} arquivo(s))."
    )

    return lote


def rodar_ciclo_robo():
    """Um "tick" do vigia do Robô — chamado periodicamente pelo
    `robo_watcher.py`. Fecha lote(s) já enviados pra Anthropic SEMPRE,
    mesmo com `robo_ativo` desligado — um lote, uma vez enviado, continua
    rodando do lado da Anthropic independente do interruptor local; se a
    coleta só acontecesse com o robô ligado, um lote que terminou depois
    de alguém desligar a chave ficava preso pra sempre (nunca virava
    relatório, nunca saía da tela como "em andamento"). Só abrir lote NOVO
    é que respeita `robo_ativo`."""
    config = carregar_config()

    algum_lote_em_andamento = False

    if listar_lotes_em_andamento():
        cliente = _obter_cliente()
        algum_lote_em_andamento = _coletar_lotes_pendentes(cliente, config)

    if not config.get("robo_ativo"):
        return

    if algum_lote_em_andamento:
        return  # só um lote em voo por vez

    cliente = _obter_cliente()
    itens = _preparar_novo_lote(config, cliente)

    if itens:
        _submeter_lote(cliente, itens)
