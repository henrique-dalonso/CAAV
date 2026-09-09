from pathlib import Path


def listar_pdfs(pasta):
    pasta = Path(pasta)

    if not pasta.exists():
        return []

    return list(pasta.glob("*.pdf"))