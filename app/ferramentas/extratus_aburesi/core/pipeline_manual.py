import asyncio

from app.ferramentas.extratus_aburesi.core.checagem_lote import analisar_pdf_isolado
from app.ferramentas.extratus_aburesi.core.config_manager import carregar_config
from app.ferramentas.extratus_aburesi.core.pipeline import (
    ajustar_confianca_pos_ia,
    finalizar_processamento,
    tratar_erro,
)
from app.ferramentas.extratus_aburesi.core.app_logger import registrar_log
from app.ferramentas.extratus_aburesi.core.ia_cliente import gerar_relatorio
from app.ferramentas.extratus_aburesi.db import triagem_manual as db_triagem
from app.ferramentas.extratus_aburesi.db.checagem_fila import existe_conflito_de_processo
from app.ferramentas.extratus_aburesi.db.jobs import obter_relatorio_existente_para_processo


async def processar_upload_manual(registro_id):
    """Agendada via `BackgroundTasks` uma vez por arquivo, logo depois do
    upload (web/routes/gerar_relatorio.py) — todas agendadas juntas rodam
    concorrentemente. `asyncio.to_thread` pra não travar o event loop do
    servidor (mesmo padrão dos watchers em core/motor_watcher.py e
    core/checagem_watcher.py)."""
    await asyncio.to_thread(_triar_e_processar, registro_id)


async def retomar_apos_conferencia(registro_id, processo_manual=None):
    """Ação "Aprovar/Prosseguir" do painel de Conferências manual — a
    própria aprovação já é o gatilho pra geração, sem esperar nada (mesma
    filosofia do resto deste fluxo: "a triagem que dá sinal verde",
    Henrique 2026-08-11)."""
    await asyncio.to_thread(_retomar_apos_conferencia_sync, registro_id, processo_manual)


def _triar_e_processar(registro_id):
    """Espelha core/checagem_lote.py::_checar_um_arquivo (mesma lógica de
    duplicidade que a Fila do Motor usa — reaproveitada tal como está,
    já é cross-origin por natureza), com uma diferença: aqui, assim que
    aprova, já segue direto pra geração do relatório na mesma chamada,
    em vez de esperar um próximo ciclo/lote pegar o arquivo depois."""
    registro = db_triagem.obter_registro(registro_id)

    if not registro:
        return

    config = carregar_config()

    try:
        resultado = analisar_pdf_isolado(registro.caminho_pdf)
    except Exception as erro:
        registrar_log(f"Triagem manual: falha ao ler {registro.nome_arquivo}: {erro}")
        db_triagem.atualizar_apos_triagem(
            registro_id, db_triagem.FALHA_LEITURA, None, None, f"Falha ao ler o PDF: {erro}",
        )
        return

    dominante = resultado.get("dominante")
    confianca = resultado.get("confianca") or {}
    nivel = confianca.get("nivel")
    motivo = confianca.get("motivo")

    if not dominante:
        db_triagem.atualizar_apos_triagem(
            registro_id, db_triagem.NAO_ENCONTRADO, None, nivel, motivo,
        )
        return

    processo = dominante["processo"]

    relatorio_existente = obter_relatorio_existente_para_processo(processo)
    if relatorio_existente:
        origem = "motor" if relatorio_existente.usuario_id is None else "manual"
        db_triagem.atualizar_apos_triagem(
            registro_id, db_triagem.DUPLICADO_RELATORIO, processo, nivel,
            "Já existe um relatório gerado para esse número de processo.",
            origem_duplicado=origem,
        )
        return

    if existe_conflito_de_processo(processo, exceto_nome_arquivo=registro.nome_arquivo):
        db_triagem.atualizar_apos_triagem(
            registro_id, db_triagem.DUPLICADO_EM_ANDAMENTO, processo, nivel,
            "Esse número de processo já está sendo processado por outro arquivo.",
        )
        return

    # Sinal verde da triagem — já é o próprio gatilho pra geração, sem
    # passar por um estado "aprovado" à parte (aqui não tem Motor/lote
    # esperando pra pegar depois, então o próximo passo já é processar).
    registro = db_triagem.atualizar_apos_triagem(registro_id, db_triagem.PROCESSANDO, processo, nivel, motivo)
    _gerar_e_finalizar(registro, {"nivel": nivel, "motivo": motivo}, config)


def _retomar_apos_conferencia_sync(registro_id, processo_manual):
    registro = db_triagem.aprovar_manualmente(registro_id, processo_manual)

    if not registro:
        return

    config = carregar_config()
    _gerar_e_finalizar(
        registro,
        {"nivel": registro.confianca_nivel, "motivo": registro.confianca_motivo},
        config,
    )


def _gerar_e_finalizar(registro, confianca, config):
    pasta_saida = config.get("pasta_saida", "relatorios_prontos")
    pasta_processados = config.get("pasta_processados", "processados")
    pasta_erros = config.get("pasta_erros", "erros")
    pasta_revisao = config.get("pasta_revisao", "revisao")
    ia_provider = config.get("ia_provider", "claude")

    try:
        dados_relatorio, uso_ia = gerar_relatorio(registro.caminho_pdf, registro.processo_detectado, ia_provider)
    except Exception as erro:
        tratar_erro(
            registro.caminho_pdf, registro.processo_detectado, "erro_ia", erro,
            pasta_erros, registro.usuario_id,
        )
        db_triagem.marcar_erro(registro.id, "Falha ao gerar o relatório.")
        return

    confianca = ajustar_confianca_pos_ia(confianca, uso_ia)

    resultado = finalizar_processamento(
        registro.caminho_pdf,
        registro.processo_detectado,
        confianca,
        dados_relatorio,
        uso_ia,
        pasta_saida,
        pasta_processados,
        pasta_revisao,
        pasta_erros,
        registro.usuario_id,
    )

    if resultado.get("sucesso"):
        db_triagem.concluir(registro.id, resultado.get("job_id"))
    else:
        db_triagem.marcar_erro(registro.id, resultado.get("erro", "Falha no processamento."))
