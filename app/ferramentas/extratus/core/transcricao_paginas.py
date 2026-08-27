import base64

import fitz

from app.ferramentas.extratus.core.app_logger import registrar_log
from app.ferramentas.extratus.core.ia_cliente import MODELO_PEDACO, extrair_dados_e_uso


# Henrique, diretoria, 2026-08-26: processo real (321 páginas, 29.4MB)
# falhou porque tinha páginas sem texto confiável (escaneadas OU com
# fonte embaralhada — ver texto_manager.py) demais pra caber no caminho
# de texto, e o arquivo era grande demais pro caminho de PDF nativo
# (imagem inteira). Não existia um terceiro caminho.
#
# Este módulo é esse terceiro caminho: em vez de mandar o PDF inteiro
# como imagem (caro, e ainda esbarra no limite de 32MB da Anthropic),
# manda SÓ as páginas problemáticas, em lotes pequenos, pro modelo mais
# barato (Haiku) — pedindo só transcrição literal, não interpretação.
# O texto que volta é usado no lugar do texto ruim daquela página, e o
# processo inteiro segue pelo caminho de texto normal (barato,
# reaproveita a divisão em pedaços já existente pra processo grande).
#
# Henrique descartou OCR tradicional de propósito ("OCR porcaria") —
# fontes/digitalizações de documento jurídico variam muito (carimbo,
# assinatura, tabela densa) e um motor de OCR clássico erra bastante
# nesse tipo de conteúdo. Usar a própria IA de visão (mesmo passo, bem
# mais barato que o modelo padrão) tende a ler melhor, e nunca esbarra
# no limite de tamanho porque manda só um punhado de páginas por vez,
# nunca o PDF inteiro.
MODELO_TRANSCRICAO = MODELO_PEDACO

# Páginas por chamada — pequeno de propósito: cada imagem de página
# consome uma quantidade real de tokens de entrada, e um lote grande
# demais aumentaria o risco de a resposta (uma transcrição por página)
# estourar o teto de tokens de saída de uma única chamada.
#
# Henrique, diretoria, 2026-08-26: validado com teste real pago contra o
# processo de 301 páginas do achado original. Com 8 páginas/lote e
# max_tokens=4096 (valores antigos), TODOS os lotes de 8 páginas reais
# (texto jurídico denso) bateram no teto de saída (`stop_reason ==
# "max_tokens"`) ANTES de terminar de transcrever — só o último lote (4
# páginas) coube no orçamento e funcionou. Baixado pra 4 páginas/lote e
# subido max_tokens (ver `_montar_parametros_transcricao`) — dá ~4x mais
# orçamento de saída por página do que antes.
PAGINAS_POR_LOTE_TRANSCRICAO = 4

# 150 DPI: legível o suficiente pra transcrição de texto de documento
# (a Anthropic recomenda a imagem não passar de ~1568px no lado maior
# pra melhor relação custo/qualidade — uma página A4/Ofício a 150 DPI
# fica perto disso) sem gerar uma imagem grande demais à toa.
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
        # Ver nota em PAGINAS_POR_LOTE_TRANSCRICAO — 4096 (valor antigo)
        # já foi visto batendo no teto real com um lote de 8 páginas
        # densas, cortando a transcrição no meio sem gerar nenhuma
        # entrada válida.
        "max_tokens": 8192,
        "tools": [FERRAMENTA_TRANSCRICAO],
        "tool_choice": {"type": "tool", "name": "registrar_transcricoes"},
        "messages": [{"role": "user", "content": conteudo}],
    }


def transcrever_paginas(caminho_pdf, numeros_paginas, cliente, tamanho_lote=PAGINAS_POR_LOTE_TRANSCRICAO):
    """Transcreve as páginas indicadas (números 1-based) como imagem, em
    lotes de `tamanho_lote`, usando o modelo barato. Devolve
    (texto_por_pagina, usos) — texto_por_pagina é um dict {numero: texto},
    só com as páginas que a IA de fato devolveu (nunca falha silenciosa:
    se uma página não voltar na resposta, ela simplesmente não aparece no
    dict, e quem chama decide o que fazer). `usos` é a lista de
    dicionários de uso/custo (mesmo formato de extrair_dados_e_uso), um
    por lote — quem chama soma isso no custo total do processamento.

    `numeros_paginas` vazio devolve ({}, []) sem abrir o PDF nem gastar
    nada — caminho comum (a maioria dos processos não tem página
    problemática nenhuma)."""
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
                # Achado real (Henrique, 2026-08-26): quando isso acontece, a
                # resposta cortada no meio normalmente não rende NENHUMA
                # transcrição válida (o JSON da ferramenta não fecha) — as
                # páginas deste grupo simplesmente não entram em
                # texto_por_pagina (nunca falha silenciosa: ver docstring
                # desta função) e continuam com o texto ruim original. Loga
                # pra ficar visível que o orçamento de saída pode precisar
                # subir de novo se isso voltar a acontecer.
                registrar_log(
                    f"Transcrição de páginas {grupo} cortada no limite de tokens "
                    "de saída — pode não ter resgatado nenhuma delas."
                )

            dados, uso = extrair_dados_e_uso(resposta)
            usos.append(uso)

            for item in (dados.get("transcricoes") or []):
                # Achado real (Henrique, 2026-08-26): apesar do schema da
                # ferramenta exigir objeto, uma resposta real já devolveu um
                # item que não era dict (string solta) num dos lotes — nunca
                # confiar cegamente na aderência ao schema.
                if not isinstance(item, dict):
                    continue

                posicao = item.get("pagina")
                texto = item.get("texto") or ""

                if isinstance(posicao, int) and 1 <= posicao <= len(grupo):
                    texto_por_pagina[grupo[posicao - 1]] = texto

        return texto_por_pagina, usos
    finally:
        documento.close()
