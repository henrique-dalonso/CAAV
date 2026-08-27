from unittest.mock import MagicMock

import fitz
import pytest

from app.ferramentas.extratus.core.transcricao_paginas import (
    PAGINAS_POR_LOTE_TRANSCRICAO,
    transcrever_paginas,
)


@pytest.fixture
def pdf_de_5_paginas(tmp_path):
    """PDF descartável de verdade (não mock) — transcrever_paginas usa
    PyMuPDF pra RENDERIZAR cada página como imagem, precisa de um
    arquivo real pra abrir."""
    documento = fitz.open()
    for numero in range(1, 6):
        pagina = documento.new_page()
        pagina.insert_text((72, 72), f"Conteudo da pagina {numero}")

    caminho = tmp_path / "teste_transcricao.pdf"
    documento.save(str(caminho))
    documento.close()
    return caminho


def _resposta_fake(transcricoes, stop_reason="end_turn"):
    bloco_ferramenta = MagicMock()
    bloco_ferramenta.type = "tool_use"
    bloco_ferramenta.input = {"transcricoes": transcricoes}

    resposta = MagicMock()
    resposta.content = [bloco_ferramenta]
    resposta.model = "claude-haiku-4-5"
    resposta.stop_reason = stop_reason
    resposta.usage.input_tokens = 1000
    resposta.usage.output_tokens = 200
    resposta.usage.cache_creation_input_tokens = 0
    resposta.usage.cache_read_input_tokens = 0
    return resposta


def test_transcrever_paginas_vazio_nao_abre_pdf_nem_chama_cliente(pdf_de_5_paginas):
    cliente = MagicMock()

    texto_por_pagina, usos = transcrever_paginas(pdf_de_5_paginas, [], cliente)

    assert texto_por_pagina == {}
    assert usos == []
    cliente.messages.create.assert_not_called()


def test_transcrever_paginas_mapeia_texto_para_numero_real_da_pagina(pdf_de_5_paginas):
    cliente = MagicMock()
    cliente.messages.create.return_value = _resposta_fake([
        {"pagina": 1, "texto": "transcricao da pagina 2"},
        {"pagina": 2, "texto": "transcricao da pagina 4"},
    ])

    texto_por_pagina, usos = transcrever_paginas(pdf_de_5_paginas, [2, 4], cliente)

    assert texto_por_pagina == {
        2: "transcricao da pagina 2",
        4: "transcricao da pagina 4",
    }
    assert len(usos) == 1
    assert usos[0]["modelo"] == "claude-haiku-4-5"
    cliente.messages.create.assert_called_once()


def test_transcrever_paginas_divide_em_lotes(pdf_de_5_paginas):
    """PAGINAS_POR_LOTE_TRANSCRICAO páginas por chamada — pedindo mais
    que isso precisa de mais de 1 chamada."""
    cliente = MagicMock()
    cliente.messages.create.return_value = _resposta_fake([
        {"pagina": i + 1, "texto": f"texto {i + 1}"} for i in range(PAGINAS_POR_LOTE_TRANSCRICAO)
    ])

    numeros = list(range(1, PAGINAS_POR_LOTE_TRANSCRICAO + 3))  # força 2 lotes

    # PDF real só tem 5 páginas — reaproveita as mesmas via módulo,
    # abrindo um PDF maior pra esse teste específico não faz sentido, só
    # queremos confirmar a divisão em lotes/número de chamadas.
    import fitz as _fitz
    documento = _fitz.open()
    for _ in range(len(numeros)):
        documento.new_page()
    caminho = pdf_de_5_paginas.parent / "teste_transcricao_grande.pdf"
    documento.save(str(caminho))
    documento.close()

    transcrever_paginas(caminho, numeros, cliente)

    assert cliente.messages.create.call_count == 2


def test_transcrever_paginas_ignora_item_com_indice_invalido(pdf_de_5_paginas):
    cliente = MagicMock()
    cliente.messages.create.return_value = _resposta_fake([
        {"pagina": 1, "texto": "boa"},
        {"pagina": 99, "texto": "indice fora do lote, deve ser ignorado"},
        {"pagina": "abc", "texto": "indice nao numerico, deve ser ignorado"},
    ])

    texto_por_pagina, _ = transcrever_paginas(pdf_de_5_paginas, [3], cliente)

    assert texto_por_pagina == {3: "boa"}


def test_transcrever_paginas_ignora_item_que_nao_e_dict(pdf_de_5_paginas):
    """Achado real (Henrique, 2026-08-26): num teste real pago, um dos
    lotes devolveu um item solto (string) dentro de "transcricoes", apesar
    do schema da ferramenta exigir objeto — não pode derrubar a função
    inteira."""
    cliente = MagicMock()
    cliente.messages.create.return_value = _resposta_fake([
        "isso nao deveria estar aqui",
        {"pagina": 1, "texto": "boa"},
    ])

    texto_por_pagina, _ = transcrever_paginas(pdf_de_5_paginas, [3], cliente)

    assert texto_por_pagina == {3: "boa"}


def test_transcrever_paginas_loga_quando_lote_corta_no_limite_de_tokens(pdf_de_5_paginas, monkeypatch):
    """Achado real (Henrique, 2026-08-26): lote de páginas densas cortado
    no teto de tokens de saída normalmente não rende nenhuma transcrição
    válida — precisa ficar visível no log, não silencioso."""
    mensagens_logadas = []
    monkeypatch.setattr(
        "app.ferramentas.extratus.core.transcricao_paginas.registrar_log",
        mensagens_logadas.append,
    )

    cliente = MagicMock()
    cliente.messages.create.return_value = _resposta_fake([], stop_reason="max_tokens")

    transcrever_paginas(pdf_de_5_paginas, [1], cliente)

    assert len(mensagens_logadas) == 1
    assert "cortada" in mensagens_logadas[0]
