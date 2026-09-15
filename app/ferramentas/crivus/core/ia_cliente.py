import base64
import os
from pathlib import Path

from app.ferramentas.crivus.config.taxonomia import (
    NAO_IDENTIFICADO,
    TIPOS_ACOMPANHAMENTO,
    TIPOS_AGENDAMENTO,
)
from app.ferramentas.crivus.core.prompt_manager import carregar_instrucoes_publicacoes


MODELO_PADRAO = "claude-sonnet-5"

# Henrique, diretoria, 2026-09-15: a "pré-triagem futura do modo em
# lote" cogitada em 2026-09-03 (ver comentário antigo) virou real —
# Processamento em Lote só manda pra análise completa (MODELO_PADRAO,
# cara) o que passar por uma pré-análise barata com esse modelo (ver
# avaliar_confiabilidade_teor). Preço confirmado em platform.claude.com/
# docs/en/about-claude/pricing (2026-09-15): Haiku é 2x mais barato que
# o Sonnet na entrada e 2x mais barato na saída.
MODELO_TRIAGEM = "claude-haiku-4-5-20251001"

# Henrique, 2026-09-03: a tarefa de leitura jurídica de publicação é
# considerada "julgamento que importa" (tem consequência financeira/
# jurídica real se errar), não uma etapa mecânica — só o modelo forte
# faz a análise completa.
PRECOS_POR_MILHAO_USD = {
    MODELO_PADRAO: (2.00, 10.00),
    MODELO_TRIAGEM: (1.00, 5.00),
}

TIPOS_MIME_SUPORTADOS = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

FERRAMENTA_ANALISE_PUBLICACAO = {
    "name": "registrar_analise_publicacao",
    "description": (
        "Registra a leitura da publicação e o(s) ACOMPANHAMENTO(S) e "
        "AGENDAMENTO(S) necessários, seguindo o prompt mestre e o manual "
        "operacional de publicações fornecidos nas instruções."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "processo": {
                "type": "string",
                "description": "Número do processo identificado (formato CNJ), se houver. Vazio se não identificado.",
            },
            "carteira": {"type": "string", "enum": ["ITAÚ", "VOLKSWAGEN", "OUTRA"]},
            # Henrique, 2026-09-04: a leitura (seção 1 do prompt mestre) sai
            # em campos separados, não texto livre — a tela renderiza cada
            # um em sua própria linha, formatação sempre consistente
            # (rótulo em maiúsculas + ";"), sem depender da IA "lembrar" de
            # formatar direito toda vez.
            "orgao_julgador": {
                "type": "string",
                "description": "Vara/comarca/tribunal identificado, se houver (ex: \"5ª Vara Cível de Bauru\"). Vazio se não identificado.",
            },
            "carteira_detalhe": {
                "type": "string",
                "description": "Explicação/justificativa da classificação de carteira acima — por que ITAÚ, VOLKSWAGEN ou OUTRA.",
            },
            "fase_processual": {"type": "string"},
            "posicao_parte": {
                "type": "string",
                "description": "Posição do banco/parte patrocinada no processo (autor, réu, exequente, executado, agravante etc.) e quem são as partes.",
            },
            "natureza_ato": {"type": "string"},
            "quem_foi_intimado": {"type": "string"},
            "resumo_objetivo": {"type": "string"},
            "comando_judicial": {
                "type": "string",
                "description": "O que o juízo determinou exatamente — preferencialmente citando o trecho literal da decisão.",
            },
            "resultado_parte": {
                "type": "string",
                "description": "Resultado para o banco/parte intimada: favorável, desfavorável, parcialmente desfavorável ou neutro, com a justificativa.",
            },
            "conclusao_operacional": {
                "type": "string",
                "description": (
                    "Seção 8 do formato obrigatório: instrução imperativa e "
                    "objetiva do que lançar e agendar, com a justificativa."
                ),
            },
            "nivel_confianca": {"type": "string", "enum": ["ALTO", "MÉDIO", "BAIXO"]},
            "motivo_confianca": {
                "type": "string",
                "description": "Obrigatório quando nivel_confianca for MÉDIO ou BAIXO: o que exatamente precisa ser validado por um humano.",
            },
            "tem_alerta_critico": {
                "type": "boolean",
                "description": (
                    "true quando houver pagamento de condenação, art. 523, "
                    "cumprimento de sentença contra o banco ou impugnação ao "
                    "cumprimento — ver ALERTA CRÍTICO nas instruções."
                ),
            },
            "texto_alerta_critico": {
                "type": "string",
                "description": "Obrigatório quando tem_alerta_critico=true: providência, prazo, valor (se houver) e risco financeiro/processual.",
            },
            "acompanhamentos": {
                "type": "array",
                "description": "Um ou mais ACOMPANHAMENTOS — o que aconteceu no processo.",
                "items": {
                    "type": "object",
                    "properties": {
                        "tipo": {"type": "string", "enum": TIPOS_ACOMPANHAMENTO + [NAO_IDENTIFICADO]},
                    },
                    "required": ["tipo"],
                },
            },
            "agendamentos": {
                "type": "array",
                "description": (
                    "Zero ou mais AGENDAMENTOS — o que o escritório deve "
                    "fazer. Vazio quando a publicação não exige nenhuma "
                    "providência (ex: liminar deferida sem impedimento)."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "tipo": {"type": "string", "enum": TIPOS_AGENDAMENTO + [NAO_IDENTIFICADO]},
                        "dias_inicio": {
                            "type": "integer",
                            "description": "Dias corridos a partir de HOJE para a DATA INÍCIO do SLA interno desse agendamento (ver tabela de SLA nas instruções).",
                        },
                        "dias_fim": {
                            "type": "integer",
                            "description": "Dias corridos a partir de HOJE para a DATA FIM do SLA interno desse agendamento.",
                        },
                    },
                    "required": ["tipo", "dias_inicio", "dias_fim"],
                },
            },
        },
        "required": [
            "carteira_detalhe", "fase_processual", "posicao_parte", "natureza_ato",
            "quem_foi_intimado", "resumo_objetivo", "comando_judicial", "resultado_parte",
            "conclusao_operacional", "nivel_confianca", "tem_alerta_critico",
            "acompanhamentos", "agendamentos",
        ],
    },
}


# Henrique, diretoria, 2026-09-15: Processamento em Lote só deve mandar
# pra análise completa (cara) o que for "nitidamente útil" — essa
# ferramenta/instruções são de uma tarefa BEM mais simples que a análise
# completa (registrar_analise_publicacao acima): não lê o mérito
# jurídico, só decide se o teor SOZINHO (sem nenhum outro documento)
# sustenta uma leitura confiável. Prompt próprio, curto, não reaproveita
# o prompt mestre/manual operacional (carregar_instrucoes_publicacoes) —
# aquele é pra ensinar a IA a fazer a análise em si, não pra essa
# triagem.
FERRAMENTA_TRIAGEM_TEOR = {
    "name": "avaliar_teor",
    "description": (
        "Avalia se o teor de uma publicação jurídica, sozinho e sem "
        "nenhum outro documento de apoio, contém informação substantiva "
        "o suficiente para uma leitura jurídica confiável."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "confiavel": {
                "type": "boolean",
                "description": (
                    "true se o teor descreve claramente um ato/decisão/"
                    "evento processual reconhecível, o suficiente para "
                    "uma leitura jurídica confiável. false se o teor é "
                    "vago, incompleto, cortado, ou não permite entender "
                    "o que de fato aconteceu no processo."
                ),
            },
            "motivo": {
                "type": "string",
                "description": "Motivo curto e objetivo da decisão. Nunca use travessão.",
            },
        },
        "required": ["confiavel", "motivo"],
    },
}

INSTRUCOES_TRIAGEM = (
    "Você recebe o teor de uma publicação jurídica extraída de um "
    "sistema de acompanhamento processual. Sua única tarefa é avaliar "
    "se esse teor, SOZINHO, sem nenhum outro documento ou contexto, "
    "contém informação substantiva o suficiente para uma análise "
    "jurídica confiável (identificar o que aconteceu no processo e o "
    "que precisa ser feito a respeito). Publicações vagas, cortadas, "
    "genéricas demais ou que não descrevem claramente um ato processual "
    "reconhecível devem ser marcadas como não confiáveis. Ao escrever o "
    "motivo, nunca use travessão."
)


def montar_parametros_triagem(teor_publicacao):
    return {
        "model": MODELO_TRIAGEM,
        "max_tokens": 512,
        "system": [
            {
                "type": "text",
                "text": INSTRUCOES_TRIAGEM,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ],
        "tools": [FERRAMENTA_TRIAGEM_TEOR],
        "tool_choice": {"type": "tool", "name": "avaliar_teor"},
        "messages": [{"role": "user", "content": f"TEOR DA PUBLICAÇÃO:\n\n{teor_publicacao}"}],
    }


def _montar_conteudo_anexo(caminho, tipo_mime):
    caminho = Path(caminho)
    dados_base64 = base64.standard_b64encode(caminho.read_bytes()).decode("utf-8")

    if tipo_mime == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": tipo_mime, "data": dados_base64}}

    if tipo_mime in ("image/png", "image/jpeg"):
        return {"type": "image", "source": {"type": "base64", "media_type": tipo_mime, "data": dados_base64}}

    if tipo_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        # A Anthropic só entende PDF nativo/imagem como "document"/"image"
        # de verdade — um .docx anexado vira texto extraído localmente
        # (mesmo espírito do Extratus mandando texto de PDF em vez do
        # arquivo inteiro: mais barato, e funciona igual).
        import docx as _docx

        texto = "\n".join(p.text for p in _docx.Document(caminho).paragraphs)
        return {"type": "text", "text": f"[Documento anexado: {caminho.name}]\n{texto}"}

    raise ValueError(f"Tipo de arquivo não suportado como anexo: {tipo_mime}")


def montar_parametros_mensagem(teor_publicacao, anexos=None):
    instrucoes = carregar_instrucoes_publicacoes()
    anexos = anexos or []

    conteudo_usuario = [
        {"type": "text", "text": f"TEOR DA PUBLICAÇÃO:\n\n{teor_publicacao}"},
    ]
    for anexo in anexos:
        conteudo_usuario.append(_montar_conteudo_anexo(anexo["caminho"], anexo["tipo_mime"]))

    conteudo_usuario.append({
        "type": "text",
        "text": (
            "Analise esta publicação (e os documentos de apoio anexados, se "
            "houver) e registre a leitura, o(s) acompanhamento(s) e o(s) "
            "agendamento(s) necessários."
        ),
    })

    return {
        "model": MODELO_PADRAO,
        "max_tokens": 8192,
        "system": [
            {
                # Cache: o texto das instruções é o mesmo em toda chamada,
                # independente da publicação — mesmo padrão do Extratus.
                # TTL de 1h (não o padrão de 5min) — Henrique, 2026-09-06:
                # diferente do Robô do Extratus (chamadas em sequência), o
                # uso do Crivus é uma pessoa lendo publicação por publicação
                # da fila do NPJUR, com intervalo real entre cada uma; 5min
                # expiraria o cache com frequência, pagando escrita (mais
                # caro) em vez de leitura (mais barato) na maioria das
                # chamadas seguintes.
                "type": "text",
                "text": instrucoes,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ],
        "tools": [FERRAMENTA_ANALISE_PUBLICACAO],
        "tool_choice": {"type": "tool", "name": "registrar_analise_publicacao"},
        "messages": [{"role": "user", "content": conteudo_usuario}],
    }


DESCONTO_BATCH_API = 0.5  # mesmo desconto real da Anthropic pra Batch API, ver nucleo_relatorios/core/ia_cliente.py


def _achar_bloco_tool_use(resposta):
    bloco = next((bloco for bloco in resposta.content if bloco.type == "tool_use"), None)

    if not bloco:
        raise RuntimeError("Claude não devolveu os dados estruturados esperados.")

    return bloco


def _calcular_uso(resposta, via_batch=False):
    """Custo pelo preço do MODELO que respondeu (`PRECOS_POR_MILHAO_USD`
    já cobre tanto MODELO_PADRAO quanto MODELO_TRIAGEM) — compartilhado
    entre a análise completa e a pré-análise de triagem, únicas duas
    diferenças entre elas são o modelo/prompt/ferramenta, o cálculo de
    custo é o mesmo."""
    modelo = getattr(resposta, "model", None) or MODELO_PADRAO
    preco_entrada, preco_saida = PRECOS_POR_MILHAO_USD.get(modelo, PRECOS_POR_MILHAO_USD[MODELO_PADRAO])
    # Escrita de cache custa diferente conforme o TTL — 1h (usado aqui,
    # ver montar_parametros_mensagem) é 2x o preço normal de entrada;
    # 5min (o padrão da API, mantido só como fallback abaixo pra resposta
    # sem o detalhamento por TTL) é 1,25x. Leitura custa 10% em qualquer
    # TTL. Henrique, 2026-09-06.
    preco_cache_escrita_1h = preco_entrada * 2.00
    preco_cache_escrita_5m = preco_entrada * 1.25
    preco_cache_leitura = preco_entrada * 0.10

    tokens_entrada = resposta.usage.input_tokens
    tokens_saida = resposta.usage.output_tokens
    tokens_cache_leitura = getattr(resposta.usage, "cache_read_input_tokens", 0) or 0

    cache_creation = getattr(resposta.usage, "cache_creation", None)
    if cache_creation:
        tokens_cache_escrita_1h = cache_creation.ephemeral_1h_input_tokens or 0
        tokens_cache_escrita_5m = cache_creation.ephemeral_5m_input_tokens or 0
    else:
        tokens_cache_escrita_1h = 0
        tokens_cache_escrita_5m = getattr(resposta.usage, "cache_creation_input_tokens", 0) or 0

    tokens_cache_escrita = tokens_cache_escrita_1h + tokens_cache_escrita_5m

    multiplicador = (1 - DESCONTO_BATCH_API) if via_batch else 1

    custo_estimado = multiplicador * (
        tokens_entrada / 1_000_000 * preco_entrada
        + tokens_saida / 1_000_000 * preco_saida
        + tokens_cache_escrita_1h / 1_000_000 * preco_cache_escrita_1h
        + tokens_cache_escrita_5m / 1_000_000 * preco_cache_escrita_5m
        + tokens_cache_leitura / 1_000_000 * preco_cache_leitura
    )

    uso_ia = {
        "modelo": modelo,
        "tokens_entrada": tokens_entrada + tokens_cache_escrita + tokens_cache_leitura,
        "tokens_saida": tokens_saida,
        "custo_estimado_usd": round(custo_estimado, 4),
    }

    return uso_ia


def extrair_dados_e_uso(resposta, via_batch=False):
    """`via_batch=True` quando `resposta` veio de um resultado da API de
    Lote (Processamento em Lote) — aplica os 50% de desconto da
    Anthropic nesse caso; chamadas em tempo real (Leitor Individual) usam
    o preço cheio normalmente."""
    bloco_ferramenta = _achar_bloco_tool_use(resposta)
    dados = dict(bloco_ferramenta.input)
    uso_ia = _calcular_uso(resposta, via_batch=via_batch)
    return dados, uso_ia


def avaliar_confiabilidade_teor(teor_publicacao):
    """Pré-análise de triagem (MODELO_TRIAGEM, bem mais barato) — só
    decide se o teor SOZINHO sustenta uma análise confiável, nunca faz a
    leitura jurídica em si. Sempre em tempo real (nunca via Batch API):
    Henrique, diretoria, 2026-09-15, precisa de resposta rápida por
    linha pra decidir se ela segue pra análise completa no mesmo ciclo,
    não faz sentido esperar um lote físico inteiro só pra essa decisão
    barata. Devolve (confiavel: bool, motivo: str, uso_ia: dict) — quem
    chama decide o que fazer com o custo/resultado."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurada no .env. Configure a chave "
            "antes de usar o Crivus."
        )

    cliente = anthropic.Anthropic(api_key=api_key)
    parametros = montar_parametros_triagem(teor_publicacao)
    resposta = cliente.messages.create(**parametros)

    bloco_ferramenta = _achar_bloco_tool_use(resposta)
    resultado = dict(bloco_ferramenta.input)
    uso_ia = _calcular_uso(resposta, via_batch=False)

    return resultado["confiavel"], resultado.get("motivo"), uso_ia


def analisar_publicacao(teor_publicacao, anexos=None):
    """Chama a Claude em tempo real com o teor colado (+ anexos, se
    houver) e devolve (dados_estruturados, uso_ia) — usado pelo fluxo
    individual do Leitor de Publicação."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurada no .env. Configure a chave "
            "antes de usar o Crivus."
        )

    cliente = anthropic.Anthropic(api_key=api_key)
    parametros = montar_parametros_mensagem(teor_publicacao, anexos=anexos)
    resposta = cliente.messages.create(**parametros)

    return extrair_dados_e_uso(resposta)
