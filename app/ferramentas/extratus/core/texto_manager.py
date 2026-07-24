from pathlib import Path

from pypdf import PdfReader


def extrair_texto_pdf(caminho_pdf):
    caminho_pdf = Path(caminho_pdf)

    leitor = PdfReader(str(caminho_pdf))

    texto = []

    for pagina in leitor.pages:
        conteudo = pagina.extract_text()

        if conteudo:
            texto.append(conteudo)

    return "\n".join(texto)