import asyncio

from app.ferramentas.nucleo_relatorios.core.checagem_lote import analisar_pdf_isolado
from app.ferramentas.nucleo_relatorios.core.pipeline import (
    ajustar_confianca_pos_ia,
    finalizar_processamento,
    tratar_erro,
)
from app.ferramentas.nucleo_relatorios.core.app_logger import registrar_log
from app.ferramentas.nucleo_relatorios.core.ia_cliente import gerar_relatorio_claude
from app.ferramentas.nucleo_relatorios.db import triagem_manual as db_triagem
from app.ferramentas.nucleo_relatorios.db.checagem_fila import existe_conflito_de_processo
from app.ferramentas.nucleo_relatorios.db.jobs import obter_relatorio_existente_para_processo
from app.ferramentas.nucleo_relatorios.db.models import FERRAMENTA_SLUG_PADRAO


async def processar_upload_manual(registro_id, config, tipo=None, ferramenta_slug=FERRAMENTA_SLUG_PADRAO):
    """Agendada via `BackgroundTasks` uma vez por arquivo, logo depois do
    upload (web/routes/gerar_relatorio.py) — todas agendadas juntas rodam
    concorrentemente. `asyncio.to_thread` pra não travar o event loop do
    servidor (mesmo padrão dos watchers em core/robo_watcher.py e
    core/checagem_watcher.py).

    `config` vem já carregado pela rota (config_manager DAQUELA TELA) —
    achado real, 2026-09-09: até esta correção, o processamento manual
    sempre carregava a config do Extratus-Relatórios por dentro, então
    um upload manual em Aburesi ou Emenda tinha o PDF salvo na pasta
    certa (isso a própria rota já fazia certo) mas processado/movido
    (revisão, erro, processados) nas pastas do Extratus-Relatórios."""
    await asyncio.to_thread(_triar_e_processar, registro_id, config, tipo, ferramenta_slug)


async def retomar_apos_conferencia(registro_id, config, processo_manual=None, tipo=None, ferramenta_slug=FERRAMENTA_SLUG_PADRAO):
    """Ação "Aprovar/Prosseguir" do painel de Conferências manual — a
    própria aprovação já é o gatilho pra geração, sem esperar nada (mesma
    filosofia do resto deste fluxo: "a triagem que dá sinal verde",
    Henrique 2026-08-11). `config` — ver docstring de
    `processar_upload_manual` acima."""
    await asyncio.to_thread(_retomar_apos_conferencia_sync, registro_id, config, processo_manual, tipo, ferramenta_slug)


def _triar_e_processar(registro_id, config, tipo=None, ferramenta_slug=FERRAMENTA_SLUG_PADRAO):
    """Espelha core/checagem_lote.py::_checar_um_arquivo (mesma lógica de
    duplicidade que a Fila do Robô usa — reaproveitada tal como está,
    já é cross-origin por natureza), com uma diferença: aqui, assim que
    aprova, já segue direto pra geração do relatório na mesma chamada,
    em vez de esperar um próximo ciclo/lote pegar o arquivo depois."""
    registro = db_triagem.obter_registro(registro_id, ferramenta_slug=ferramenta_slug)

    if not registro:
        return

    try:
        resultado = analisar_pdf_isolado(registro.caminho_pdf)
    except Exception as erro:
        # Henrique, 2026-08-12: falha ao LER o PDF (arquivo corrompido/
        # ilegível) não pode virar erro definitivo na hora — trava em
        # Pendentes (bolinha vermelha) igual às outras inconsistências,
        # até alguém decidir em Conferências (Aprovar informando o
        # processo na mão, ou Descartar). Só registra Job "erro" se, mais
        # tarde, uma tentativa de geração de fato falhar (_gerar_e_finalizar).
        registrar_log(f"Triagem manual: falha ao ler {registro.nome_arquivo}: {erro}")
        db_triagem.atualizar_apos_triagem(
            registro_id, db_triagem.FALHA_LEITURA, None, None, f"Falha ao ler o PDF: {erro}",
            ferramenta_slug=ferramenta_slug,
        )
        return

    dominante = resultado.get("dominante")
    confianca = resultado.get("confianca") or {}
    nivel = confianca.get("nivel")
    motivo = confianca.get("motivo")

    if not dominante:
        db_triagem.atualizar_apos_triagem(
            registro_id, db_triagem.NAO_ENCONTRADO, None, nivel, motivo,
            ferramenta_slug=ferramenta_slug,
        )
        return

    processo = dominante["processo"]

    relatorio_existente = obter_relatorio_existente_para_processo(processo, ferramenta_slug=ferramenta_slug)
    if relatorio_existente:
        origem = "robô" if relatorio_existente.usuario_id is None else "manual"
        db_triagem.atualizar_apos_triagem(
            registro_id, db_triagem.DUPLICADO_RELATORIO, processo, nivel,
            "Já existe um relatório gerado para esse número de processo.",
            origem_duplicado=origem,
            ferramenta_slug=ferramenta_slug,
        )
        return

    if existe_conflito_de_processo(processo, exceto_nome_arquivo=registro.nome_arquivo, ferramenta_slug=ferramenta_slug):
        db_triagem.atualizar_apos_triagem(
            registro_id, db_triagem.DUPLICADO_EM_ANDAMENTO, processo, nivel,
            "Esse número de processo já está sendo processado por outro arquivo.",
            ferramenta_slug=ferramenta_slug,
        )
        return

    # Sinal verde da triagem — já é o próprio gatilho pra geração, sem
    # passar por um estado "aprovado" à parte (aqui não tem Robô/lote
    # esperando pra pegar depois, então o próximo passo já é processar).
    registro = db_triagem.atualizar_apos_triagem(
        registro_id, db_triagem.PROCESSANDO, processo, nivel, motivo, ferramenta_slug=ferramenta_slug
    )
    _gerar_e_finalizar(registro, {"nivel": nivel, "motivo": motivo}, config, tipo, ferramenta_slug)


def _retomar_apos_conferencia_sync(registro_id, config, processo_manual, tipo=None, ferramenta_slug=FERRAMENTA_SLUG_PADRAO):
    registro = db_triagem.aprovar_manualmente(registro_id, processo_manual, ferramenta_slug=ferramenta_slug)

    if not registro:
        return

    _gerar_e_finalizar(
        registro,
        {"nivel": registro.confianca_nivel, "motivo": registro.confianca_motivo},
        config,
        tipo,
        ferramenta_slug,
    )


def _gerar_e_finalizar(registro, confianca, config, tipo=None, ferramenta_slug=FERRAMENTA_SLUG_PADRAO):
    pasta_saida = config.get("pasta_saida", "relatorios_prontos")
    pasta_processados = config.get("pasta_processados", "processados")
    pasta_erros = config.get("pasta_erros", "erros")
    pasta_revisao = config.get("pasta_revisao", "revisao")

    try:
        dados_relatorio, uso_ia = gerar_relatorio_claude(registro.caminho_pdf, registro.processo_detectado, tipo=tipo)
    except Exception as erro:
        tratar_erro(
            registro.caminho_pdf, registro.processo_detectado, "erro_ia", erro,
            pasta_erros, registro.usuario_id, ferramenta_slug=ferramenta_slug,
        )
        db_triagem.marcar_erro(registro.id, "Falha ao gerar o relatório.", ferramenta_slug=ferramenta_slug)
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
        tipo=tipo,
        ferramenta_slug=ferramenta_slug,
    )

    if resultado.get("sucesso"):
        db_triagem.concluir(registro.id, resultado.get("job_id"), ferramenta_slug=ferramenta_slug)
    else:
        db_triagem.marcar_erro(
            registro.id, resultado.get("erro", "Falha no processamento."), ferramenta_slug=ferramenta_slug
        )
