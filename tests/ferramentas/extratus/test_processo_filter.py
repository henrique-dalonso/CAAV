from pathlib import Path

from app.ferramentas.extratus.core.processo_filter import filtrar_fila, filtrar_por_nome, normalizar_processo


def test_normalizar_processo_remove_espacos():
    assert normalizar_processo("  1506649-24.2019.8.26.0071  ") == "1506649-24.2019.8.26.0071"


def test_normalizar_processo_vazio():
    assert normalizar_processo("") == ""
    assert normalizar_processo(None) == ""


def test_filtrar_por_nome():
    pdfs = [Path("caso_A.pdf"), Path("caso_B.pdf")]
    assert filtrar_por_nome(pdfs, "caso_A") == [Path("caso_A.pdf")]


def test_filtrar_fila_sem_processo_especifico_aplica_limite():
    pdfs = [Path(f"caso_{i}.pdf") for i in range(5)]
    assert filtrar_fila(pdfs, limite=2) == pdfs[:2]


def test_filtrar_fila_limite_zero_ou_none_devolve_tudo():
    pdfs = [Path(f"caso_{i}.pdf") for i in range(3)]
    assert filtrar_fila(pdfs, limite=0) == pdfs
    assert filtrar_fila(pdfs, limite=None) == pdfs


def test_filtrar_fila_por_processo_especifico_no_nome():
    pdfs = [Path("caso_A.pdf"), Path("caso_B.pdf")]
    assert filtrar_fila(pdfs, processo_especifico="caso_A") == [Path("caso_A.pdf")]
