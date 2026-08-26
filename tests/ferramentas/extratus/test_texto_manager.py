from unittest.mock import patch

from app.ferramentas.extratus.core.texto_manager import (
    MINIMO_CARACTERES_PAGINA_COM_TEXTO,
    _parece_texto_embaralhado,
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


# --- Texto embaralhado por fonte quebrada (Henrique, 2026-08-26) ---
#
# Achado num processo real de 321 páginas: algumas fontes embutidas no
# PDF têm o ToUnicode CMap trocado — o texto extraído sai ilegível
# ("coı pedido liıiĲaŘ" em vez de "com pedido liminar") mesmo tendo
# caracteres suficientes pra passar na régua de MINIMO_CARACTERES.
# Confirmado com pypdf E PyMuPDF (mesmo resultado nas duas bibliotecas)
# — é a fonte do PDF, não bug de biblioteca. Amostra real abaixo (texto
# de verdade extraído da petição inicial desse processo).
TEXTO_EMBARALHADO_REAL = (
    "coı pedido liıiĲaŘ eı ċace de ELMAR CAINELLI, Estado Civil descoĲhecido, "
    "PŘoissão descoĲhecido, eĲdeŘeço eletŘôĲico DESCONHECIDO, iĲscŘito Ĳo CPF "
    "sob Ĳº ͑͗͏.͖͐͘.͒͏͏-͕͗, coı eĲdeŘeço Ĳa TRAV LUCINDO OZELAME, ͏͑, N SRA DO "
    "CARMO, extŘaídas dos autos do pŘocesso ŗue, coıo é ŘeČŘa, é público, "
    "oċeŘeceı-lhe pŘoposta de ŗuitação do coĲtŘato poŘ valoŘ siČĲiicativaıeĲte "
    "ıeĲoŘ do ŗue o devido, tudo coı a pŘoıessa de Ĳão apŘeeĲdeŘ o veículo."
)

# Texto real limpo do mesmo processo (página de capa/cabeçalho) — não
# pode disparar o alarme, mesmo com acentuação portuguesa normal.
TEXTO_LIMPO_REAL = (
    "Processos relacionados: Nº do processo 5017368-86.2025.8.21.0005 "
    "Classe da ação: BUSCA E APREENSÃO EM ALIENAÇÃO FIDUCIÁRIA Competência "
    "Cível - Geral Data de autuação: 01/12/2025 11:50:28 Situação MOVIMENTO "
    "Órgão Julgador: Juízo da 1ª Vara Cível de Bento Gonçalves, foi distribuído "
    "com urgência e pedido de liminar em face do requerido, com pedido de "
    "produção de todos os meios de prova em direito admitidos pela legislação."
)


def test_parece_texto_embaralhado_detecta_amostra_real():
    assert _parece_texto_embaralhado(TEXTO_EMBARALHADO_REAL) is True


def test_parece_texto_embaralhado_nao_dispara_em_texto_limpo_com_acentuacao():
    assert _parece_texto_embaralhado(TEXTO_LIMPO_REAL) is False


def test_parece_texto_embaralhado_ignora_pagina_curta_demais():
    # Já cai na régua de "sem texto" comum — não precisa (nem deveria)
    # passar pela checagem de embaralhamento.
    assert _parece_texto_embaralhado("Ř Ĳ ı") is False


def test_diagnostico_conta_pagina_embaralhada_como_sem_texto_e_reporta_separado():
    paginas_fake = [
        _pagina_fake(1, TEXTO_LIMPO_REAL),
        _pagina_fake(2, TEXTO_EMBARALHADO_REAL),
        _pagina_fake(3, "Processo 5004744-44.2018.8.21.0039, Evento 3, PROCJUDIC1, Página 3"),
    ]

    with patch(
        "app.ferramentas.extratus.core.texto_manager.extrair_paginas_pdf",
        return_value=(paginas_fake, 3),
    ):
        diagnostico = extrair_texto_pdf_com_diagnostico("qualquer.pdf")

    # pagina 2 (embaralhada) + pagina 3 (vazia, só carimbo) = 2 "sem texto"
    assert diagnostico["paginas_sem_texto"] == 2
    assert diagnostico["paginas_embaralhadas"] == 1
