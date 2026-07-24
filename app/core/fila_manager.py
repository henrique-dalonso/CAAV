from app.core.pdf_manager import listar_pdfs
from app.core.processo_filter import filtrar_fila


def montar_fila(
    pasta_entrada,
    limite=0,
    processo_especifico=""
):
    pdfs = listar_pdfs(pasta_entrada)

    fila = filtrar_fila(
        pdfs,
        processo_especifico=processo_especifico,
        limite=limite
    )

    return {
        "total_pdfs": len(pdfs),
        "total_fila": len(fila),
        "pdfs": fila
    }