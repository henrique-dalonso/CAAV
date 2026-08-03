import base64
import os
from datetime import datetime
from pathlib import Path

from app.ferramentas.extratus_aburesi.core.prompt_manager import carregar_instrucoes_relatorio
from app.ferramentas.extratus_aburesi.core.texto_manager import extrair_texto_pdf_com_diagnostico


MODELO_PADRAO = "claude-sonnet-5"

# --- Limites de segurança para a análise via texto extraído localmente ---
# (ver memória de redução de custo — validados com testes reais em 2026-07-29)
#
# Se mais que essa proporção das páginas vier sem texto de verdade, tratamos
# o PDF como digitalizado (escaneado) — nesse caso a extração de texto não
# serve, e caímos de volta pro envio do PDF nativo (visão), que ao menos
# consegue "ler" a imagem.
LIMITE_PROPORCAO_PAGINAS_SEM_TEXTO = 0.15

# Estimativa de tokens por caractere do texto extraído, calibrada com dois
# testes reais pagos (0,53 e 0,58 tokens/caractere) — usamos 0,6 pra ter
# margem de segurança pra cima, já que subestimar aqui é o que pode causar
# um erro de "excedeu a janela de contexto" no meio do processamento.
TOKENS_POR_CARACTERE_ESTIMADO = 0.6

# Deixamos uma folga generosa da janela de 200 mil tokens do modelo, porque
# ainda entram o prompt do Max, o schema da ferramenta e a resposta.
LIMITE_TOKENS_TEXTO_EXTRAIDO = 150_000

# A Anthropic rejeita (HTTP 413) requisições acima de 32MB. Um PDF em
# base64 fica ~1,33x maior que o arquivo original — por isso o teto aqui
# é mais conservador que 32MB. Confirmado com teste real em 2026-07-29:
# um PDF de 34,2MB (979 páginas) foi rejeitado de fato com esse erro.
LIMITE_MB_ARQUIVO_PARA_PDF_NATIVO = 24

# Preço promocional por milhão de tokens, válido até 31/08/2026 (depois
# disso sobe pra $3/$15 — lembrar de atualizar). Isso é só uma ESTIMATIVA
# pra acompanhar gasto dentro do sistema — a fatura real da Anthropic é
# que vale de verdade. Testado em 25/07/2026: o cálculo aqui deu US$ 0,64
# pra uma chamada que a fatura real cobrou US$ 0,85 — ainda não sabemos
# a causa exata da diferença (possível custo extra de processar PDF/imagem
# não refletido em usage.input_tokens). Tratar este número como piso, não teto.
PRECO_ENTRADA_POR_MILHAO_USD = 2.00
PRECO_SAIDA_POR_MILHAO_USD = 10.00

# Cache de prompt: escrita (primeira vez) custa 1,25x o preço normal de
# entrada; leitura (reaproveitando o que já foi escrito, dentro de ~5min)
# custa só 10% do preço normal. Só a instrução do Max entra em cache — o
# PDF de cada processo é sempre diferente, não tem o que reaproveitar ali.
PRECO_CACHE_ESCRITA_POR_MILHAO_USD = PRECO_ENTRADA_POR_MILHAO_USD * 1.25
PRECO_CACHE_LEITURA_POR_MILHAO_USD = PRECO_ENTRADA_POR_MILHAO_USD * 0.10

# Batch API (usado só pelo Motor, ver motor_lote.py): 50% de desconto em
# cima de TODOS os preços acima — entrada, saída e cache. Confirmado com
# teste real em 2026-07-29.
DESCONTO_BATCH_API = 0.5


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


def parece_digitalizado(total_paginas, paginas_sem_texto):
    """True quando a proporção de páginas sem texto real sugere que o PDF
    é escaneado/digitalizado (sem camada de texto), não um PDF nativo do
    sistema do tribunal."""
    if total_paginas <= 0:
        return True

    return (paginas_sem_texto / total_paginas) > LIMITE_PROPORCAO_PAGINAS_SEM_TEXTO


def estimar_tokens_texto(texto):
    return int(len(texto) * TOKENS_POR_CARACTERE_ESTIMADO)


def cabe_no_limite_pdf_nativo(caminho_pdf):
    tamanho_mb = Path(caminho_pdf).stat().st_size / 1_000_000
    return tamanho_mb <= LIMITE_MB_ARQUIVO_PARA_PDF_NATIVO


def _instrucao_formato():
    return (
        "\n\nIMPORTANTE SOBRE O FORMATO DE RESPOSTA: você não vai gerar um "
        "arquivo Word diretamente nem responder em texto livre — preencha a "
        "ferramenta \"preencher_relatorio\" com o conteúdo do relatório, "
        "seguindo a PARTE 1 do prompt acima. A formatação visual do "
        "documento final (fonte, margens, negrito) é responsabilidade de "
        "outro sistema, não sua — ignore a PARTE 2. A PARTE 3 (controle de "
        "qualidade) continua valendo integralmente."
    )


def extrair_dados_e_uso(resposta, via_batch=False):
    """`via_batch=True` quando `resposta` veio de um resultado do Batch API
    (Motor) — aplica os 50% de desconto da Anthropic nesse caso; chamadas
    em tempo real (fila manual) usam o preço cheio normalmente."""
    bloco_ferramenta = next(
        (bloco for bloco in resposta.content if bloco.type == "tool_use"),
        None,
    )

    if not bloco_ferramenta:
        raise RuntimeError("Claude não devolveu os dados estruturados esperados.")

    dados = dict(bloco_ferramenta.input)

    tokens_entrada = resposta.usage.input_tokens
    tokens_saida = resposta.usage.output_tokens
    tokens_cache_escrita = getattr(resposta.usage, "cache_creation_input_tokens", 0) or 0
    tokens_cache_leitura = getattr(resposta.usage, "cache_read_input_tokens", 0) or 0

    multiplicador = (1 - DESCONTO_BATCH_API) if via_batch else 1

    custo_estimado = multiplicador * (
        tokens_entrada / 1_000_000 * PRECO_ENTRADA_POR_MILHAO_USD
        + tokens_saida / 1_000_000 * PRECO_SAIDA_POR_MILHAO_USD
        + tokens_cache_escrita / 1_000_000 * PRECO_CACHE_ESCRITA_POR_MILHAO_USD
        + tokens_cache_leitura / 1_000_000 * PRECO_CACHE_LEITURA_POR_MILHAO_USD
    )

    uso_ia = {
        "modelo": MODELO_PADRAO,
        # tokens_entrada aqui soma tudo (normal + cache), pra manter a
        # coluna do histórico simples de ler — o detalhe do cache fica
        # só no log, pra quem quiser conferir se está funcionando.
        "tokens_entrada": tokens_entrada + tokens_cache_escrita + tokens_cache_leitura,
        "tokens_saida": tokens_saida,
        "custo_estimado_usd": round(custo_estimado, 4),
    }

    if tokens_cache_leitura:
        economia_estimada = (
            tokens_cache_leitura / 1_000_000
            * (PRECO_ENTRADA_POR_MILHAO_USD - PRECO_CACHE_LEITURA_POR_MILHAO_USD)
        )
        print(
            f"[cache] {tokens_cache_leitura} tokens vieram do cache "
            f"(economia estimada de US$ {economia_estimada:.4f} nesta chamada)."
        )

    return dados, uso_ia


def montar_parametros_mensagem(caminho_pdf, processo_detectado, instrucoes):
    """Monta o dict de parâmetros pra uma chamada `messages.create` (sem
    disparar a chamada) — usado tanto pelo fluxo em tempo real (fila
    manual) quanto pelo Batch API (Motor), que só diferem em COMO essa
    chamada é despachada (na hora vs. dentro de um lote).

    Extrai o texto do PDF localmente (de graça) e manda só o texto — muito
    mais barato que mandar o PDF inteiro (que a Anthropic processa como se
    fosse foto de cada página). Dois casos de segurança, validados com
    testes reais em 2026-07-29:
    - Se o PDF parecer digitalizado (sem texto de verdade), cai de volta
      pro envio do PDF nativo — só quando o arquivo couber no limite de
      tamanho da API (32MB); senão, erro claro pedindo revisão manual.
    - Se o texto extraído for grande demais pra caber numa única chamada
      (processos muito extensos), erro claro pedindo revisão manual — em
      vez de tentar e estourar a janela de contexto do modelo no meio do
      processamento.
    """
    caminho_pdf = Path(caminho_pdf)
    diagnostico = extrair_texto_pdf_com_diagnostico(caminho_pdf)

    pedido_analise = (
        "Analise este processo (número detectado no nome do arquivo: "
        f"{processo_detectado or 'não identificado'}) e preencha o relatório."
    )

    if parece_digitalizado(diagnostico["total_paginas"], diagnostico["paginas_sem_texto"]):
        if not cabe_no_limite_pdf_nativo(caminho_pdf):
            tamanho_mb = caminho_pdf.stat().st_size / 1_000_000
            raise RuntimeError(
                f"'{caminho_pdf.name}' parece ser um PDF digitalizado (sem "
                f"camada de texto legível — {diagnostico['paginas_sem_texto']} de "
                f"{diagnostico['total_paginas']} páginas sem texto) e também é "
                f"grande demais ({tamanho_mb:.1f}MB) para ser enviado à IA como "
                "imagem (limite da Anthropic é 32MB). Precisa de revisão manual."
            )

        pdf_base64 = base64.standard_b64encode(caminho_pdf.read_bytes()).decode("utf-8")
        conteudo_usuario = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf_base64,
                },
            },
            {"type": "text", "text": pedido_analise},
        ]
    else:
        tokens_estimados = estimar_tokens_texto(diagnostico["texto"])

        if tokens_estimados > LIMITE_TOKENS_TEXTO_EXTRAIDO:
            raise RuntimeError(
                f"'{caminho_pdf.name}' tem {diagnostico['total_paginas']} páginas "
                f"(~{tokens_estimados} tokens estimados) — processo grande demais "
                "para ser analisado em uma única chamada de IA hoje. Precisa da "
                "funcionalidade de divisão em partes (ainda não implementada) ou "
                "de revisão manual."
            )

        conteudo_usuario = [
            {
                "type": "text",
                "text": (
                    "Segue o texto integral do processo judicial, extraído "
                    "automaticamente do PDF original (com marcadores de "
                    f"página):\n\n{diagnostico['texto']}"
                ),
            },
            {"type": "text", "text": pedido_analise},
        ]

    return {
        "model": MODELO_PADRAO,
        # 4096 já foi visto batendo no teto em processo real (risco de
        # resposta cortada no meio) — 8192 dá folga, e o custo de saída é
        # uma fração pequena do custo total mesmo assim.
        "max_tokens": 8192,
        "system": [
            {
                "type": "text",
                "text": instrucoes + _instrucao_formato(),
                # Marca esse bloco pra cache — é o mesmo texto em toda
                # chamada, independente de qual processo está sendo lido.
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "tools": [FERRAMENTA_RELATORIO],
        "tool_choice": {"type": "tool", "name": "preencher_relatorio"},
        "messages": [{"role": "user", "content": conteudo_usuario}],
    }


def gerar_relatorio_claude(caminho_pdf, processo_detectado):
    """Envia o processo pra Claude em tempo real (fluxo manual) e devolve
    os dados do relatório já estruturados nos mesmos campos que o template
    Word espera.

    Usa "tool use" da API (não texto livre) — o modelo é obrigado a
    preencher exatamente os campos do schema, sem a gente precisar
    adivinhar onde cada informação começa/termina numa resposta solta.
    """
    import anthropic

    instrucoes = carregar_instrucoes_relatorio()

    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurada no .env. Configure a chave "
            "antes de usar ia_provider = \"claude\"."
        )

    cliente = anthropic.Anthropic(api_key=api_key)

    parametros = montar_parametros_mensagem(caminho_pdf, processo_detectado, instrucoes)
    resposta = cliente.messages.create(**parametros)

    return extrair_dados_e_uso(resposta)


def gerar_relatorio(caminho_pdf, processo_detectado, ia_provider):
    """Ponto único de entrada — escolhe simulado ou real conforme o
    config.json (`ia_provider`). Sempre devolve (dados, uso_ia).
    """
    if str(ia_provider).strip().lower() == "claude":
        return gerar_relatorio_claude(caminho_pdf, processo_detectado)

    return gerar_relatorio_simulado(caminho_pdf, processo_detectado)
