from pathlib import Path

from app.ferramentas.extratus_aburesi.core.processo_detector import (
    ajustar_confianca_por_digitalizacao,
    analisar_texto_pdf,
)


# --- Mescla com "parece digitalizado" (Henrique, 2026-08-13) ---
# Espelho de tests/ferramentas/extratus/test_processo_detector.py — mesma
# regra, mesmo código (infraestrutura de detecção, não geração de
# relatório, cai na exceção do escopo combinado).

def test_ajustar_confianca_rebaixa_alta_para_media_quando_digitalizado():
    confianca_alta = {"nivel": "alta", "motivo": "Número encontrado no nome do arquivo."}
    resultado = ajustar_confianca_por_digitalizacao(confianca_alta, total_paginas=10, paginas_sem_texto=9)

    assert resultado["nivel"] == "media"
    assert "Número encontrado no nome do arquivo." in resultado["motivo"]
    assert "rebaixada de alta para média" in resultado["motivo"]
    assert "digitalizado" in resultado["motivo"]


def test_ajustar_confianca_mantem_alta_quando_nao_digitalizado():
    confianca_alta = {"nivel": "alta", "motivo": "Número encontrado no nome do arquivo."}
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
    texto = "1506649-24.2019.8.26.0071 " * 3
    diagnostico = {"texto": texto, "total_paginas": 10, "paginas_sem_texto": 9, "caracteres": len(texto)}

    resultado = analisar_texto_pdf(
        Path("relatorio_1506649-24.2019.8.26.0071.pdf"),
        diagnostico,
    )

    assert resultado["confianca"]["nivel"] == "media"
    assert "digitalizado" in resultado["confianca"]["motivo"]
    assert resultado["caracteres_extraidos"] == len(texto)
