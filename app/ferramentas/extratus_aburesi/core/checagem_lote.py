from pathlib import Path

from app.ferramentas.extratus_aburesi.core.app_logger import registrar_log
from app.ferramentas.extratus_aburesi.core.config_manager import carregar_config
from app.ferramentas.extratus_aburesi.core.pdf_isolado import executar_isolado
from app.ferramentas.extratus_aburesi.core.pdf_manager import listar_pdfs
from app.ferramentas.extratus_aburesi.core.pipeline import tratar_erro
from app.ferramentas.extratus_aburesi.core.processo_detector import analisar_pdf
from app.ferramentas.extratus_aburesi.db.checagem_fila import (
    APROVADO,
    DUPLICADO_EM_ANDAMENTO,
    DUPLICADO_RELATORIO,
    NAO_ENCONTRADO,
    atualizar_apos_checagem,
    existe_conflito_de_processo,
    sincronizar_registros,
)
from app.ferramentas.extratus_aburesi.db.jobs import existe_relatorio_gerado_para_processo
from app.ferramentas.extratus_aburesi.db.lotes import listar_arquivos_ja_reivindicados


def analisar_pdf_isolado(caminho):
    """Ver docstring equivalente em app/ferramentas/extratus/core/
    checagem_lote.py (Extratus - Relatórios) — mesma lógica, mesmo bug
    real (site lento durante a checagem), mesma correção."""
    return executar_isolado(analisar_pdf, caminho)


def rodar_ciclo_checagem():
    """Um "tick" da checagem da Fila do Motor — a "triagem" de
    duplicidade que Henrique pediu (2026-08-06). Roda muito mais rápido
    que o Motor (ver checagem_watcher.py, poucos segundos vs. 5 minutos)
    porque é 100% local (ler PDF, comparar texto, consultar o banco) —
    zero custo de API, então não tem motivo pra esperar o ritmo do Motor.

    NÃO confundir com `ia_cliente.montar_diagnostico_com_triagem` (outra
    função, filtro de anexo de terceiros) nem com `motor_lote.py` (que
    continua cuidando só de enviar/coletar lotes do Batch API)."""
    config = carregar_config()
    pasta = Path(config.get("motor_pasta_entrada", "motor_entrada_pdfs"))
    pasta_erros = config.get("pasta_erros")

    nomes_no_disco = {pdf.name for pdf in listar_pdfs(pasta)}
    ja_reivindicados = listar_arquivos_ja_reivindicados()

    # Um arquivo já reivindicado por um lote não precisa mais de
    # checagem nenhuma (é tarde demais pra travar ele, e o próprio
    # motor_lote.py só o considerou porque já estava aprovado) — não
    # entra no sincronizar_registros, então a linha dele em ChecagemFila
    # (se existir) é apagada, mantendo a tabela sempre só com quem ainda
    # está "esperando" nalgum sentido.
    candidatos = nomes_no_disco - ja_reivindicados

    pendentes = sincronizar_registros(candidatos)

    for registro in pendentes:
        _checar_um_arquivo(registro, pasta, pasta_erros)


def _checar_um_arquivo(registro, pasta, pasta_erros):
    caminho = pasta / registro.nome_arquivo

    try:
        resultado = analisar_pdf_isolado(caminho)
    except FileNotFoundError:
        # Race real, não um PDF ruim: `nomes_no_disco` (rodar_ciclo_checagem)
        # é uma foto tirada no INÍCIO do ciclo — se alguém remover o
        # arquivo (manual ou "Remover todos") enquanto o ciclo ainda está
        # processando outros arquivos da mesma leva, o arquivo pode já não
        # existir mais quando chega a vez dele aqui. Isso NÃO é uma falha
        # de processamento (não é "erro" nem deveria virar notificação) —
        # é só a fila mudando por baixo dos nossos pés. Ignora e segue: a
        # linha em ChecagemFila se limpa sozinha no próximo ciclo, já que
        # o arquivo não vai mais aparecer em nomes_no_disco. Bug real
        # visto ao vivo (2026-08-06/07): sem esse tratamento, cada arquivo
        # pego nessa race virava um Job "erro" permanente (usuario_id
        # None) — inundando o sininho de notificações com "erros" que
        # nunca existiram de verdade.
        registrar_log(f"Checagem: {registro.nome_arquivo} sumiu da fila durante o ciclo (ignorado).")
        return
    except Exception as erro:
        # PDF corrompido/ilegível de verdade — como motor_lote.py agora
        # só considera arquivo já aprovado aqui (nunca mais chama a
        # detecção sozinho), esse erro precisa ser tratado JÁ, na
        # checagem, senão o arquivo ficaria parado pra sempre sem nunca
        # aparecer como erro em lugar nenhum. Mesma função/mesmo destino
        # (pasta_erros, Job status "erro") que já era usado antes daqui
        # existir. A linha em ChecagemFila se limpa sozinha no próximo
        # ciclo (o arquivo já não está mais em motor_pasta_entrada).
        tratar_erro(caminho, None, "erro_pdf", erro, pasta_erros)
        registrar_log(f"Checagem: falha ao ler {registro.nome_arquivo}: {erro}")
        return

    dominante = resultado.get("dominante")
    confianca = resultado.get("confianca") or {}
    nivel = confianca.get("nivel")
    motivo = confianca.get("motivo")

    if not dominante:
        atualizar_apos_checagem(registro.id, NAO_ENCONTRADO, None, nivel, motivo)
        return

    processo = dominante["processo"]

    if existe_relatorio_gerado_para_processo(processo):
        atualizar_apos_checagem(
            registro.id, DUPLICADO_RELATORIO, processo, nivel,
            "Já existe um relatório gerado para esse número de processo.",
        )
        return

    if existe_conflito_de_processo(processo, exceto_nome_arquivo=registro.nome_arquivo):
        atualizar_apos_checagem(
            registro.id, DUPLICADO_EM_ANDAMENTO, processo, nivel,
            "Esse número de processo já está sendo processado por outro arquivo na fila.",
        )
        return

    atualizar_apos_checagem(registro.id, APROVADO, processo, nivel, motivo)
