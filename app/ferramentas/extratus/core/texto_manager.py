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


# Abaixo disso, consideramos que a página "não tem texto de verdade" —
# só um cabeçalho/carimbo solto, não o conteúdo real da página.
MINIMO_CARACTERES_PAGINA_COM_TEXTO = 30


def extrair_paginas_pdf(caminho_pdf):
    """Extrai o texto de cada página do PDF separadamente (sem juntar tudo
    numa string só) — usado tanto pelo diagnóstico normal quanto pela
    divisão em pedaços de processos grandes demais pra uma chamada só
    (ver `ia_cliente._dividir_paginas_em_pedacos`). Cada página já vem
    com seu marcador (`--- Página N de M ---`), pra IA poder referenciar
    de onde tirou cada informação mesmo quando o texto é lido em pedaços."""
    caminho_pdf = Path(caminho_pdf)
    leitor = PdfReader(str(caminho_pdf))

    total_paginas = len(leitor.pages)
    paginas = []

    for indice, pagina in enumerate(leitor.pages, start=1):
        conteudo = pagina.extract_text() or ""
        paginas.append({
            "numero": indice,
            "texto_bruto": conteudo,
            "texto_marcado": f"--- Página {indice} de {total_paginas} ---\n{conteudo}",
        })

    return paginas, total_paginas


def extrair_texto_pdf_com_diagnostico(caminho_pdf):
    """Extrai o texto de cada página do PDF (com marcador de página, pra IA
    poder referenciar de onde tirou cada informação) e devolve também um
    diagnóstico: quantas páginas vieram sem texto real. Uma proporção alta
    de páginas vazias é o sinal de que o PDF é digitalizado (escaneado,
    sem camada de texto) — precisa ser tratado diferente do PDF nativo.
    """
    paginas, total_paginas = extrair_paginas_pdf(caminho_pdf)

    paginas_sem_texto = sum(
        1 for pagina in paginas
        if len(pagina["texto_bruto"].strip()) < MINIMO_CARACTERES_PAGINA_COM_TEXTO
    )
    texto_completo = "\n\n".join(pagina["texto_marcado"] for pagina in paginas)

    return {
        "texto": texto_completo,
        "total_paginas": total_paginas,
        "paginas_sem_texto": paginas_sem_texto,
        "caracteres": len(texto_completo),
    }