from pathlib import Path


def listar_pdfs(pasta):
    pasta = Path(pasta)

    if not pasta.exists():
        return []

    return list(pasta.glob("*.pdf"))


def aplicar_limite(lista_pdfs, limite):
    if limite is None:
        return lista_pdfs

    if limite <= 0:
        return lista_pdfs

    return lista_pdfs[:limite]