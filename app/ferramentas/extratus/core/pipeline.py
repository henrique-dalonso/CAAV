from pathlib import Path

from app.ferramentas.extratus.core.app_logger import registrar_log
from app.ferramentas.extratus.core.processo_detector import analisar_pdf
from app.ferramentas.extratus.core.ia_cliente import gerar_relatorio
from app.ferramentas.extratus.core.relatorio_manager import salvar_relatorio_docx
from app.ferramentas.extratus.core.output_manager import (
    gerar_caminho_unico,
    mover_para_erros,
    mover_por_confianca
)
from app.ferramentas.extratus.core.nomeador_relatorio import gerar_nome_relatorio
from app.ferramentas.extratus.db.jobs import registrar_processado, registrar_erro


def obter_dados_deteccao(caminho_pdf):
    caminho_pdf = Path(caminho_pdf)

    resultado = analisar_pdf(caminho_pdf)

    dominante = resultado.get("dominante")
    confianca = resultado.get("confianca") or {
        "nivel": "revisao",
        "motivo": "Falha desconhecida ao avaliar a confiança da detecção.",
    }

    processo = dominante.get("processo") if dominante else caminho_pdf.stem

    return processo, confianca


def tratar_erro(pdf, processo, tipo_erro, erro, pasta_erros, usuario_id=None):
    """Registra uma falha de processamento (PDF, IA, docx ou movimentação)
    e move o PDF pra pasta de erros. Reaproveitada tanto pelo fluxo
    síncrono (`processar_pdf`) quanto pelo Motor (itens de um lote do
    Batch API que falharam, ou arquivos rejeitados antes mesmo de entrar
    num lote — ver `motor_lote.py`)."""
    registrar_log(f"Erro ({tipo_erro}) ao processar {Path(pdf).name}: {erro}")

    destino_pdf = None

    try:
        destino_pdf = mover_para_erros(pdf, pasta_erros)
        registrar_log(f"PDF movido para erros: {destino_pdf}")
    except Exception as erro_movimentacao:
        registrar_log(f"Erro ao mover PDF para erros: {erro_movimentacao}")

    registrar_erro(
        arquivo_pdf=Path(pdf).name,
        processo=processo,
        tipo_erro=tipo_erro,
        erro_mensagem=erro,
        destino_pdf=destino_pdf,
        usuario_id=usuario_id,
    )

    return {
        "sucesso": False,
        "processo": processo,
        "tipo_erro": tipo_erro,
        "erro": str(erro)
    }


def finalizar_processamento(
    pdf,
    processo,
    confianca,
    dados_relatorio,
    uso_ia,
    pasta_saida,
    pasta_processados,
    pasta_revisao,
    pasta_erros,
    usuario_id=None,
):
    """Etapa final, depois que os dados do relatório já existem (vieram de
    uma chamada em tempo real ou de um resultado de lote coletado depois):
    gera o .docx, move o PDF conforme a confiança da detecção, e registra
    o Job. Reaproveitada por `processar_pdf` (fluxo síncrono) e pela
    coleta de resultados do Motor (`motor_lote.py`), pra não haver dois
    lugares divergentes fazendo a mesma coisa."""
    try:
        nome_relatorio = gerar_nome_relatorio(processo)
        caminho_saida_base = Path(pasta_saida) / nome_relatorio
        caminho_saida = gerar_caminho_unico(caminho_saida_base)

        salvar_relatorio_docx(dados_relatorio, caminho_saida)
    except Exception as erro:
        return tratar_erro(pdf, processo, "erro_docx", erro, pasta_erros, usuario_id)

    try:
        destino_pdf = mover_por_confianca(
            pdf,
            confianca.get("nivel"),
            pasta_processados,
            pasta_revisao
        )
    except Exception as erro:
        return tratar_erro(pdf, processo, "erro_movimentacao", erro, pasta_erros, usuario_id)

    registrar_log(
        f"Relatório gerado (confiança {confianca.get('nivel')}): {caminho_saida}"
    )
    registrar_log(f"PDF movido para: {destino_pdf}")

    job = registrar_processado(
        arquivo_pdf=Path(pdf).name,
        processo=processo,
        relatorio_path=caminho_saida,
        destino_pdf=destino_pdf,
        confianca=confianca.get("nivel"),
        motivo_confianca=confianca.get("motivo"),
        uso_ia=uso_ia,
        usuario_id=usuario_id,
    )

    return {
        "sucesso": True,
        "status": job.status,
        "processo": processo,
        "confianca": confianca.get("nivel"),
        "relatorio": str(caminho_saida),
        "pdf_destino": str(destino_pdf)
    }


def processar_pdf(
    pdf,
    pasta_saida,
    pasta_processados,
    pasta_erros,
    pasta_revisao,
    ia_provider="simulado",
    usuario_id=None,
):
    """Processa um único PDF: detecta o processo, gera o relatório, move o
    arquivo conforme a confiança da detecção e registra o resultado.

    Usado tanto pelo modo linha de comando (app/main.py) quanto pela
    camada web (app/web) — a lógica de processar um PDF existe em um
    único lugar, para não haver dois caminhos que possam divergir.

    Confiança "alta" -> processados, status "sucesso".
    Qualquer outra confiança -> revisão humana, status "revisao"
    (o relatório ainda é gerado, só fica marcado pra conferência).
    Falhas de verdade (não conseguiu ler o PDF, gerar o relatório, etc.)
    -> pasta de erros, com o tipo de erro identificado por etapa.
    """
    try:
        processo, confianca = obter_dados_deteccao(pdf)
    except Exception as erro:
        return tratar_erro(pdf, None, "erro_pdf", erro, pasta_erros, usuario_id)

    try:
        dados_relatorio, uso_ia = gerar_relatorio(pdf, processo, ia_provider)
    except Exception as erro:
        return tratar_erro(pdf, processo, "erro_ia", erro, pasta_erros, usuario_id)

    return finalizar_processamento(
        pdf,
        processo,
        confianca,
        dados_relatorio,
        uso_ia,
        pasta_saida,
        pasta_processados,
        pasta_revisao,
        pasta_erros,
        usuario_id,
    )
