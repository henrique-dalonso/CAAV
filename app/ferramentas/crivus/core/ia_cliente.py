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

# Henrique, 2026-09-03: a tarefa de leitura jurídica de publicação é
# considerada "julgamento que importa" (tem consequência financeira/
# jurídica real se errar), não uma etapa mecânica — igual o Extratus já
# resolveu com MODELO_PADRAO/MODELO_PEDACO (ver core/ia_cliente.py de
# lá), aqui fica só no modelo forte por enquanto. Um modelo mais barato
# (Haiku ou de outro provider) fica reservado pra uma pré-triagem futura
# do modo em lote — tarefa bem mais simples (lixo-ou-não), não pra essa
# análise principal.
PRECOS_POR_MILHAO_USD = {
    MODELO_PADRAO: (2.00, 10.00),
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
                "type": "text",
                "text": instrucoes,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "tools": [FERRAMENTA_ANALISE_PUBLICACAO],
        "tool_choice": {"type": "tool", "name": "registrar_analise_publicacao"},
        "messages": [{"role": "user", "content": conteudo_usuario}],
    }


def extrair_dados_e_uso(resposta):
    bloco_ferramenta = next((bloco for bloco in resposta.content if bloco.type == "tool_use"), None)

    if not bloco_ferramenta:
        raise RuntimeError("Claude não devolveu os dados estruturados esperados.")

    dados = dict(bloco_ferramenta.input)

    modelo = getattr(resposta, "model", None) or MODELO_PADRAO
    preco_entrada, preco_saida = PRECOS_POR_MILHAO_USD.get(modelo, PRECOS_POR_MILHAO_USD[MODELO_PADRAO])
    preco_cache_escrita = preco_entrada * 1.25
    preco_cache_leitura = preco_entrada * 0.10

    tokens_entrada = resposta.usage.input_tokens
    tokens_saida = resposta.usage.output_tokens
    tokens_cache_escrita = getattr(resposta.usage, "cache_creation_input_tokens", 0) or 0
    tokens_cache_leitura = getattr(resposta.usage, "cache_read_input_tokens", 0) or 0

    custo_estimado = (
        tokens_entrada / 1_000_000 * preco_entrada
        + tokens_saida / 1_000_000 * preco_saida
        + tokens_cache_escrita / 1_000_000 * preco_cache_escrita
        + tokens_cache_leitura / 1_000_000 * preco_cache_leitura
    )

    uso_ia = {
        "modelo": modelo,
        "tokens_entrada": tokens_entrada + tokens_cache_escrita + tokens_cache_leitura,
        "tokens_saida": tokens_saida,
        "custo_estimado_usd": round(custo_estimado, 4),
    }

    return dados, uso_ia


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
