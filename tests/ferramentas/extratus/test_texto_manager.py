from unittest.mock import patch

from app.ferramentas.extratus.core.texto_manager import (
    MINIMO_CARACTERES_PAGINA_COM_TEXTO,
    _texto_real_da_pagina,
    extrair_texto_pdf_com_diagnostico,
)


def test_texto_real_da_pagina_remove_carimbo_eproc():
    carimbo = "Processo 5004744-44.2018.8.21.0039, Evento 3, PROCJUDIC1, Página 47"
    assert _texto_real_da_pagina(carimbo) == ""


def test_texto_real_da_pagina_so_carimbo_fica_abaixo_do_minimo():
    carimbo = "Processo 5004744-44.2018.8.21.0039, Evento 3, PROCJUDIC1, Página 47"
    assert len(_texto_real_da_pagina(carimbo)) < MINIMO_CARACTERES_PAGINA_COM_TEXTO


def test_texto_real_da_pagina_preserva_conteudo_real_junto_do_carimbo():
    texto = (
        "Processo 5004744-44.2018.8.21.0039, Evento 33, ANEXO2, Página 29\n"
        "Vistos. Defiro o pedido de busca e apreensão do veículo Fiat Siena."
    )
    real = _texto_real_da_pagina(texto)
    assert "Vistos" in real
    assert "Processo 5004744" not in real


def test_texto_real_da_pagina_sem_carimbo_fica_igual():
    texto = "Vistos. Defiro o pedido de busca e apreensão."
    assert _texto_real_da_pagina(texto) == texto


def _pagina_fake(numero, texto_bruto):
    return {
        "numero": numero,
        "texto_bruto": texto_bruto,
        "texto_marcado": f"--- Página {numero} ---\n{texto_bruto}",
    }


def test_diagnostico_conta_pagina_so_com_carimbo_como_sem_texto():
    """Regressão do bug real (Henrique, 2026-08-21): processo de 274
    páginas onde 217 eram só o carimbo do eproc — a régua de caracteres
    sozinha achava que todas tinham texto, porque o carimbo passa dos 30
    caracteres mínimos."""
    paginas_fake = [
        _pagina_fake(1, "Processo 5004744-44.2018.8.21.0039, Evento 3, PROCJUDIC1, Página 1"),
        _pagina_fake(2, "Processo 5004744-44.2018.8.21.0039, Evento 3, PROCJUDIC1, Página 2"),
        _pagina_fake(3, "Vistos. Defiro o pedido de busca e apreensão do veículo Fiat Siena."),
    ]

    with patch(
        "app.ferramentas.extratus.core.texto_manager.extrair_paginas_pdf",
        return_value=(paginas_fake, 3),
    ):
        diagnostico = extrair_texto_pdf_com_diagnostico("qualquer.pdf")

    assert diagnostico["paginas_sem_texto"] == 2
    assert diagnostico["total_paginas"] == 3
