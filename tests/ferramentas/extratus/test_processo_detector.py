from pathlib import Path

from app.ferramentas.extratus.core.processo_detector import (
    calcular_confianca,
    contar_ocorrencias_processos,
    encontrar_processos_no_nome,
    encontrar_processos_no_texto,
    obter_processo_dominante,
)


def test_encontrar_processos_no_texto_acha_padrao_cnj():
    texto = "Processo 1506649-24.2019.8.26.0071 distribuído. Ver 1506649-24.2019.8.26.0071 novamente."
    resultado = encontrar_processos_no_texto(texto)

    assert resultado == [
        "1506649-24.2019.8.26.0071",
        "1506649-24.2019.8.26.0071",
    ]


def test_encontrar_processos_no_texto_sem_match():
    assert encontrar_processos_no_texto("nenhum número de processo aqui") == []


def test_encontrar_processos_no_nome():
    caminho = Path("relatorio_1506649-24.2019.8.26.0071_23-07-2026.pdf")
    assert encontrar_processos_no_nome(caminho) == ["1506649-24.2019.8.26.0071"]


def test_obter_processo_dominante_escolhe_mais_frequente():
    ocorrencias = contar_ocorrencias_processos(
        ["A-1", "A-1", "A-1", "B-2"]
    )
    dominante = obter_processo_dominante(ocorrencias)

    assert dominante["processo"] == "A-1"
    assert dominante["ocorrencias"] == 3
    assert dominante["segundo_processo"] == "B-2"
    assert dominante["segundo_ocorrencias"] == 1


def test_obter_processo_dominante_lista_vazia():
    assert obter_processo_dominante({}) is None


def test_confianca_revisao_quando_nao_ha_dominante():
    resultado = calcular_confianca(None, [])
    assert resultado["nivel"] == "revisao"


def test_confianca_revisao_quando_diverge_do_nome_do_arquivo():
    dominante = {"processo": "A-1", "ocorrencias": 5, "segundo_processo": None, "segundo_ocorrencias": 0}
    resultado = calcular_confianca(dominante, ["B-2"])
    assert resultado["nivel"] == "revisao"


def test_confianca_alta_quando_encontrado_no_nome_e_repetido():
    dominante = {"processo": "A-1", "ocorrencias": 2, "segundo_processo": None, "segundo_ocorrencias": 0}
    resultado = calcular_confianca(dominante, ["A-1"])
    assert resultado["nivel"] == "alta"


def test_confianca_alta_quando_muitas_ocorrencias_sem_rival():
    dominante = {"processo": "A-1", "ocorrencias": 6, "segundo_processo": None, "segundo_ocorrencias": 0}
    resultado = calcular_confianca(dominante, [])
    assert resultado["nivel"] == "alta"


def test_confianca_alta_quando_domina_o_segundo_colocado():
    dominante = {"processo": "A-1", "ocorrencias": 10, "segundo_processo": "B-2", "segundo_ocorrencias": 2}
    resultado = calcular_confianca(dominante, [])
    assert resultado["nivel"] == "alta"


def test_confianca_media_quando_repetido_mas_sem_dominancia():
    dominante = {"processo": "A-1", "ocorrencias": 3, "segundo_processo": "B-2", "segundo_ocorrencias": 2}
    resultado = calcular_confianca(dominante, [])
    assert resultado["nivel"] == "media"


def test_confianca_revisao_quando_aparece_uma_unica_vez():
    dominante = {"processo": "A-1", "ocorrencias": 1, "segundo_processo": None, "segundo_ocorrencias": 0}
    resultado = calcular_confianca(dominante, [])
    assert resultado["nivel"] == "revisao"
