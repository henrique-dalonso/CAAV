from pathlib import Path

from app.ferramentas.extratus.core.processo_detector import (
    ajustar_confianca_por_digitalizacao,
    analisar_texto_pdf,
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


# --- Mescla com "parece digitalizado" (Henrique, 2026-08-13) ---
# Regra: só "alta" pode ser rebaixada (pra "média") quando o PDF parece
# escaneado — "média" e "revisão" já caem no mesmo tratamento (revisão
# humana) hoje, então não tem "mais baixo" pra proteger nem "mais alto"
# pra evitar.

def test_ajustar_confianca_rebaixa_alta_para_media_quando_digitalizado():
    confianca_alta = {"nivel": "alta", "motivo": "Número encontrado no nome do arquivo."}
    # 90% das páginas sem texto -> parece digitalizado (limite é 15%).
    resultado = ajustar_confianca_por_digitalizacao(confianca_alta, total_paginas=10, paginas_sem_texto=9)

    assert resultado["nivel"] == "media"
    assert "Número encontrado no nome do arquivo." in resultado["motivo"]
    assert "rebaixada de alta para média" in resultado["motivo"]
    assert "digitalizado" in resultado["motivo"]


def test_ajustar_confianca_mantem_alta_quando_nao_digitalizado():
    confianca_alta = {"nivel": "alta", "motivo": "Número encontrado no nome do arquivo."}
    # Só 1 de 10 páginas sem texto (10%) -> abaixo do limite, não é digitalizado.
    resultado = ajustar_confianca_por_digitalizacao(confianca_alta, total_paginas=10, paginas_sem_texto=1)

    assert resultado == confianca_alta


def test_ajustar_confianca_media_nao_cai_mesmo_digitalizado():
    confianca_media = {"nivel": "media", "motivo": "Número encontrado múltiplas vezes, mas sem dominância suficiente."}
    resultado = ajustar_confianca_por_digitalizacao(confianca_media, total_paginas=10, paginas_sem_texto=9)

    assert resultado == confianca_media


def test_ajustar_confianca_revisao_nao_muda_mesmo_digitalizado():
    confianca_revisao = {"nivel": "revisao", "motivo": "Nenhum número de processo encontrado no conteúdo do PDF."}
    resultado = ajustar_confianca_por_digitalizacao(confianca_revisao, total_paginas=10, paginas_sem_texto=9)

    assert resultado == confianca_revisao


def test_analisar_texto_pdf_aplica_rebaixa_por_digitalizacao_de_ponta_a_ponta():
    # Processo repetido no nome+conteúdo dá "alta" (ver calcular_confianca)
    # — combinado com um diagnóstico "digitalizado" (9 de 10 páginas sem
    # texto), o resultado final tem que já vir como "media".
    texto = "1506649-24.2019.8.26.0071 " * 3
    diagnostico = {"texto": texto, "total_paginas": 10, "paginas_sem_texto": 9, "caracteres": len(texto)}

    resultado = analisar_texto_pdf(
        Path("relatorio_1506649-24.2019.8.26.0071.pdf"),
        diagnostico,
    )

    assert resultado["confianca"]["nivel"] == "media"
    assert "digitalizado" in resultado["confianca"]["motivo"]
    assert resultado["caracteres_extraidos"] == len(texto)
