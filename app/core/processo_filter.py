from app.core.processo_detector import analisar_pdf


def normalizar_processo(processo):
    if not processo:
        return ""

    return processo.strip()


def filtrar_por_nome(pdfs, processo_especifico):
    return [
        pdf for pdf in pdfs
        if processo_especifico in pdf.name
    ]


def filtrar_por_conteudo(pdfs, processo_especifico):
    encontrados = []

    for pdf in pdfs:
        resultado = analisar_pdf(pdf)
        dominante = resultado.get("dominante")

        if dominante and dominante.get("processo") == processo_especifico:
            encontrados.append(pdf)

    return encontrados


def filtrar_fila(pdfs, processo_especifico="", limite=None):
    processo_especifico = normalizar_processo(processo_especifico)

    if processo_especifico:
        encontrados_nome = filtrar_por_nome(
            pdfs,
            processo_especifico
        )

        if encontrados_nome:
            return encontrados_nome

        return filtrar_por_conteudo(
            pdfs,
            processo_especifico
        )

    if limite is None:
        return pdfs

    if limite <= 0:
        return pdfs

    return pdfs[:limite]