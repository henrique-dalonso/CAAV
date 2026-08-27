import base64

import fitz

from app.ferramentas.extratus_aburesi.core.app_logger import registrar_log
from app.ferramentas.extratus_aburesi.core.ia_cliente import MODELO_PEDACO, extrair_dados_e_uso


# Ver docstring equivalente em app/ferramentas/extratus/core/
# transcricao_paginas.py (Extratus - Relatórios) — mesma lógica, mesma
# calibração (validada com teste real pago em 2026-08-26).
MODELO_TRANSCRICAO = MODELO_PEDACO

PAGINAS_POR_LOTE_TRANSCRICAO = 4

DPI_RENDERIZACAO_PAGINA = 150


FERRAMENTA_TRANSCRICAO = {
    "name": "registrar_transcricoes",
    "description": (
        "Registra a transcrição literal do texto visível em cada página "
        "de imagem enviada nesta mensagem, na ordem em que foram enviadas."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "transcricoes": {
                "type": "array",
                "description": "Uma entrada por imagem enviada, na mesma ordem.",
                "items": {
                    "type": "object",
                    "properties": {
                        "pagina": {
                            "type": "integer",
                            "description": "Posição da imagem na mensagem (1 = primeira imagem enviada, 2 = segunda, ...).",
                        },
                        "texto": {
                            "type": "string",
                            "description": "Transcrição literal do texto visível na página. Texto vazio (\"\") se a página estiver realmente em branco ou for ilegível.",
                        },
                    },
                    "required": ["pagina", "texto"],
                },
            },
        },
        "required": ["transcricoes"],
    },
}


def _renderizar_pagina_como_imagem_base64(documento, indice_zero_based, dpi=DPI_RENDERIZACAO_PAGINA):
    pagina = documento[indice_zero_based]
    matriz = fitz.Matrix(dpi / 72, dpi / 72)
    pixmap = pagina.get_pixmap(matrix=matriz)
    return base64.standard_b64encode(pixmap.tobytes("png")).decode("utf-8")


def _montar_parametros_transcricao(imagens_base64):
    conteudo = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": imagem},
        }
        for imagem in imagens_base64
    ]

    conteudo.append({
        "type": "text",
        "text": (
            f"Transcreva o texto visível em cada uma das {len(imagens_base64)} páginas de "
            "imagem acima, na ordem em que foram enviadas (a 1ª imagem é a página 1, a 2ª é "
            "a página 2, e assim por diante). Transcreva literalmente o que está escrito — "
            "não corrija erros de digitação, não resuma, não interprete, não pule nenhuma "
            "página. Se uma página estiver realmente em branco ou for ilegível, registre "
            "texto vazio (\"\") pra ela, mas ainda assim inclua uma entrada pra ela."
        ),
    })

    return {
        "model": MODELO_TRANSCRICAO,
        "max_tokens": 8192,
        "tools": [FERRAMENTA_TRANSCRICAO],
        "tool_choice": {"type": "tool", "name": "registrar_transcricoes"},
        "messages": [{"role": "user", "content": conteudo}],
    }


def transcrever_paginas(caminho_pdf, numeros_paginas, cliente, tamanho_lote=PAGINAS_POR_LOTE_TRANSCRICAO):
    """Ver docstring equivalente em app/ferramentas/extratus/core/
    transcricao_paginas.py (Extratus - Relatórios) — mesma lógica."""
    if not numeros_paginas:
        return {}, []

    documento = fitz.open(str(caminho_pdf))
    try:
        numeros_ordenados = sorted(set(numeros_paginas))
        texto_por_pagina = {}
        usos = []

        for inicio in range(0, len(numeros_ordenados), tamanho_lote):
            grupo = numeros_ordenados[inicio:inicio + tamanho_lote]
            imagens = [_renderizar_pagina_como_imagem_base64(documento, numero - 1) for numero in grupo]

            parametros = _montar_parametros_transcricao(imagens)
            resposta = cliente.messages.create(**parametros)

            if resposta.stop_reason == "max_tokens":
                # Ver docstring equivalente em app/ferramentas/extratus/core/
                # transcricao_paginas.py.
                registrar_log(
                    f"Transcrição de páginas {grupo} cortada no limite de tokens "
                    "de saída — pode não ter resgatado nenhuma delas."
                )

            dados, uso = extrair_dados_e_uso(resposta)
            usos.append(uso)

            for item in (dados.get("transcricoes") or []):
                # Ver docstring equivalente em app/ferramentas/extratus/core/
                # transcricao_paginas.py.
                if not isinstance(item, dict):
                    continue

                posicao = item.get("pagina")
                texto = item.get("texto") or ""

                if isinstance(posicao, int) and 1 <= posicao <= len(grupo):
                    texto_por_pagina[grupo[posicao - 1]] = texto

        return texto_por_pagina, usos
    finally:
        documento.close()
