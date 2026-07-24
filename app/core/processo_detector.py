import re
from pathlib import Path
from collections import Counter

from app.core.texto_manager import extrair_texto_pdf


PADRAO_CNJ = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"


def encontrar_processos_no_texto(texto):
    return re.findall(PADRAO_CNJ, texto)


def encontrar_processos_no_nome(caminho_pdf):
    caminho_pdf = Path(caminho_pdf)
    return re.findall(PADRAO_CNJ, caminho_pdf.name)


def contar_ocorrencias_processos(lista_processos):
    contador = Counter(lista_processos)
    return dict(contador)


def obter_processo_dominante(ocorrencias):
    if not ocorrencias:
        return None

    ordenados = sorted(
        ocorrencias.items(),
        key=lambda item: item[1],
        reverse=True
    )

    processo_principal, quantidade_principal = ordenados[0]

    segundo_processo = None
    quantidade_segundo = 0

    if len(ordenados) > 1:
        segundo_processo, quantidade_segundo = ordenados[1]

    return {
        "processo": processo_principal,
        "ocorrencias": quantidade_principal,
        "segundo_processo": segundo_processo,
        "segundo_ocorrencias": quantidade_segundo
    }


def calcular_confianca(dominante, processos_nome):
    if not dominante:
        return {
            "nivel": "revisao",
            "motivo": "Nenhum número de processo encontrado no conteúdo do PDF."
        }

    processo = dominante["processo"]
    ocorrencias = dominante["ocorrencias"]
    segundo_ocorrencias = dominante["segundo_ocorrencias"]

    encontrado_no_nome = processo in processos_nome

    if processos_nome and not encontrado_no_nome:
        return {
            "nivel": "revisao",
            "motivo": "Número dominante do PDF diverge do número encontrado no nome do arquivo."
        }

    if encontrado_no_nome and ocorrencias >= 2:
        return {
            "nivel": "alta",
            "motivo": "Número encontrado no nome do arquivo e confirmado múltiplas vezes no conteúdo."
        }

    if ocorrencias >= 5 and segundo_ocorrencias == 0:
        return {
            "nivel": "alta",
            "motivo": "Número encontrado várias vezes no conteúdo, sem concorrentes."
        }

    if segundo_ocorrencias > 0 and ocorrencias >= segundo_ocorrencias * 5:
        return {
            "nivel": "alta",
            "motivo": "Número dominante aparece pelo menos 5 vezes mais que o segundo colocado."
        }

    if ocorrencias >= 2:
        return {
            "nivel": "media",
            "motivo": "Número encontrado múltiplas vezes, mas sem dominância suficiente."
        }

    return {
        "nivel": "revisao",
        "motivo": "Número encontrado apenas uma vez no conteúdo do PDF."
    }


def analisar_texto_pdf(caminho_pdf, texto):
    caminho_pdf = Path(caminho_pdf)

    processos_nome = encontrar_processos_no_nome(caminho_pdf)

    processos_texto = encontrar_processos_no_texto(texto)
    ocorrencias = contar_ocorrencias_processos(processos_texto)
    dominante = obter_processo_dominante(ocorrencias)
    confianca = calcular_confianca(dominante, processos_nome)

    return {
        "arquivo": caminho_pdf.name,
        "processos_nome": processos_nome,
        "ocorrencias": ocorrencias,
        "dominante": dominante,
        "confianca": confianca,
        "caracteres_extraidos": len(texto)
    }


def analisar_pdf(caminho_pdf):
    texto = extrair_texto_pdf(caminho_pdf)

    return analisar_texto_pdf(
        caminho_pdf,
        texto
    )