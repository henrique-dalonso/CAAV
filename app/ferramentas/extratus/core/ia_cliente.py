import base64
import os
from datetime import datetime
from pathlib import Path

from app.ferramentas.extratus.core.prompt_manager import carregar_instrucoes_relatorio


MODELO_PADRAO = "claude-sonnet-5"

# Preço aproximado por milhão de tokens (jul/2026) — é só uma estimativa
# pra acompanhar gasto, não uma fatura oficial. Ajustar se o preço mudar.
PRECO_ENTRADA_POR_MILHAO_USD = 3.00
PRECO_SAIDA_POR_MILHAO_USD = 15.00


FERRAMENTA_RELATORIO = {
    "name": "preencher_relatorio",
    "description": (
        "Preenche os campos do relatório processual com base na análise "
        "do processo judicial anexado."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tipo_acao": {"type": "string", "description": "Ex: Busca e Apreensão, Execução"},
            "numero_processo": {"type": "string"},
            "incidente": {"type": "string", "description": "Número do incidente, se houver. Vazio se não houver."},
            "valor_causa": {"type": "string"},
            "valor_divida": {"type": "string"},
            "autor": {"type": "string"},
            "reu": {"type": "string"},
            "bem": {"type": "string", "description": "Descrição do bem (marca, modelo, ano, placa, chassi), se houver."},
            "contrato": {"type": "string", "description": "Número do contrato, parcelas, taxa."},
            "comarca": {"type": "string", "description": "Vara, comarca, estado/tribunal."},
            "cronologia": {
                "type": "array",
                "description": "Eventos jurídicos relevantes, em ordem cronológica.",
                "items": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "string", "description": "Formato DD/MM/AAAA"},
                        "ator": {"type": "string", "description": "Quem praticou o ato"},
                        "descricao": {"type": "string", "description": "Máximo 3 linhas"},
                    },
                    "required": ["data", "ator", "descricao"],
                },
            },
            "parecer": {
                "type": "string",
                "description": (
                    "3 a 6 parágrafos: síntese da situação atual, análise de risco "
                    "jurídico, recomendação de ação imediata (recurso/prazo/diligência), "
                    "e análise de incidentes separados, se houver."
                ),
            },
            "data_publicacao": {"type": "string"},
            "prazo_fatal_ed": {"type": "string"},
            "prazo_fatal": {"type": "string"},
            "status_atual": {"type": "string", "description": "Resumo em 1 linha."},
        },
        "required": [
            "tipo_acao", "numero_processo", "valor_causa", "valor_divida",
            "autor", "reu", "comarca", "cronologia", "parecer", "status_atual",
        ],
    },
}


def gerar_relatorio_simulado(caminho_pdf, processo_detectado):
    """Devolve dados de exemplo no mesmo formato que a IA real devolve.

    Isso garante que o resto do pipeline (geração do .docx a partir do
    template) funciona igual, seja o conteúdo simulado ou real.
    """
    carregar_instrucoes_relatorio()

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    dados = {
        "tipo_acao": "(exemplo — IA ainda não ativada)",
        "numero_processo": processo_detectado or "não localizado nos autos",
        "incidente": "",
        "valor_causa": "não localizado nos autos",
        "valor_divida": "não localizado nos autos",
        "autor": "não localizado nos autos",
        "reu": "não localizado nos autos",
        "bem": "não localizado nos autos",
        "contrato": "não localizado nos autos",
        "comarca": "não localizado nos autos",
        "cronologia": [
            {
                "data": agora,
                "ator": "Extratus",
                "descricao": (
                    f"Relatório simulado gerado a partir de {Path(caminho_pdf).name}. "
                    "A integração real com IA ainda não está ativada."
                ),
            },
        ],
        "parecer": (
            "Este é um relatório simulado. Quando a integração real com IA "
            "estiver ativada, este texto será substituído pela análise real "
            "do processo, seguindo as instruções carregadas do escritório."
        ),
        "data_publicacao": "",
        "prazo_fatal_ed": "",
        "prazo_fatal": "",
        "status_atual": "Simulado — aguardando integração real de IA.",
    }

    return dados, {}


def gerar_relatorio_claude(caminho_pdf, processo_detectado):
    """Envia o PDF pra Claude e devolve os dados do relatório já
    estruturados nos mesmos campos que o template Word espera.

    Usa "tool use" da API (não texto livre) — o modelo é obrigado a
    preencher exatamente os campos do schema, sem a gente precisar
    adivinhar onde cada informação começa/termina numa resposta solta.
    """
    import anthropic

    caminho_pdf = Path(caminho_pdf)
    instrucoes = carregar_instrucoes_relatorio()

    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurada no .env. Configure a chave "
            "antes de usar ia_provider = \"claude\"."
        )

    cliente = anthropic.Anthropic(api_key=api_key)

    pdf_base64 = base64.standard_b64encode(caminho_pdf.read_bytes()).decode("utf-8")

    instrucao_formato = (
        "\n\nIMPORTANTE SOBRE O FORMATO DE RESPOSTA: você não vai gerar um "
        "arquivo Word diretamente nem responder em texto livre — preencha a "
        "ferramenta \"preencher_relatorio\" com o conteúdo do relatório, "
        "seguindo a PARTE 1 do prompt acima. A formatação visual do "
        "documento final (fonte, margens, negrito) é responsabilidade de "
        "outro sistema, não sua — ignore a PARTE 2. A PARTE 3 (controle de "
        "qualidade) continua valendo integralmente."
    )

    resposta = cliente.messages.create(
        model=MODELO_PADRAO,
        max_tokens=4096,
        system=instrucoes + instrucao_formato,
        tools=[FERRAMENTA_RELATORIO],
        tool_choice={"type": "tool", "name": "preencher_relatorio"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Analise este processo (número detectado no nome "
                            f"do arquivo: {processo_detectado or 'não identificado'}) "
                            "e preencha o relatório."
                        ),
                    },
                ],
            }
        ],
    )

    bloco_ferramenta = next(
        (bloco for bloco in resposta.content if bloco.type == "tool_use"),
        None,
    )

    if not bloco_ferramenta:
        raise RuntimeError("Claude não devolveu os dados estruturados esperados.")

    dados = dict(bloco_ferramenta.input)

    tokens_entrada = resposta.usage.input_tokens
    tokens_saida = resposta.usage.output_tokens
    custo_estimado = (
        tokens_entrada / 1_000_000 * PRECO_ENTRADA_POR_MILHAO_USD
        + tokens_saida / 1_000_000 * PRECO_SAIDA_POR_MILHAO_USD
    )

    uso_ia = {
        "modelo": MODELO_PADRAO,
        "tokens_entrada": tokens_entrada,
        "tokens_saida": tokens_saida,
        "custo_estimado_usd": round(custo_estimado, 4),
    }

    return dados, uso_ia


def gerar_relatorio(caminho_pdf, processo_detectado, ia_provider):
    """Ponto único de entrada — escolhe simulado ou real conforme o
    config.json (`ia_provider`). Sempre devolve (dados, uso_ia).
    """
    if str(ia_provider).strip().lower() == "claude":
        return gerar_relatorio_claude(caminho_pdf, processo_detectado)

    return gerar_relatorio_simulado(caminho_pdf, processo_detectado)
