from pathlib import Path
import shutil


def garantir_pasta(caminho):
    Path(caminho).mkdir(
        parents=True,
        exist_ok=True
    )


def gerar_caminho_unico(caminho_destino):
    caminho_destino = Path(caminho_destino)

    if not caminho_destino.exists():
        return caminho_destino

    pasta = caminho_destino.parent
    nome_base = caminho_destino.stem
    extensao = caminho_destino.suffix

    contador = 1

    while True:
        novo_caminho = pasta / f"{nome_base}_{contador}{extensao}"

        if not novo_caminho.exists():
            return novo_caminho

        contador += 1


def mover_arquivo(origem, destino):
    origem = Path(origem)
    destino = Path(destino)

    destino.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    destino_final = gerar_caminho_unico(destino)

    shutil.move(
        str(origem),
        str(destino_final)
    )

    return destino_final


def mover_para_processados(caminho_pdf, pasta_processados):
    caminho_pdf = Path(caminho_pdf)
    pasta_processados = Path(pasta_processados)

    destino = pasta_processados / caminho_pdf.name

    return mover_arquivo(
        caminho_pdf,
        destino
    )


def mover_para_revisao(caminho_pdf, pasta_revisao):
    caminho_pdf = Path(caminho_pdf)
    pasta_revisao = Path(pasta_revisao)

    destino = pasta_revisao / caminho_pdf.name

    return mover_arquivo(
        caminho_pdf,
        destino
    )


def mover_para_erros(caminho_pdf, pasta_erros):
    caminho_pdf = Path(caminho_pdf)
    pasta_erros = Path(pasta_erros)

    destino = pasta_erros / caminho_pdf.name

    return mover_arquivo(
        caminho_pdf,
        destino
    )


def mover_por_confianca(
    caminho_pdf,
    confianca,
    pasta_processados,
    pasta_revisao
):
    """Move o PDF conforme o nível de confiança da detecção do processo.

    Só confiança "alta" vai direto pra processados. Qualquer outro nível
    ("media", "revisao", ou algo inesperado) vai pra revisão humana — a
    pasta de erros fica reservada pra falhas reais de processamento
    (ver app/core/pipeline.py), não pra incerteza na detecção.
    """
    confianca = str(confianca).strip().lower()

    if confianca == "alta":
        return mover_para_processados(
            caminho_pdf,
            pasta_processados
        )

    return mover_para_revisao(
        caminho_pdf,
        pasta_revisao
    )