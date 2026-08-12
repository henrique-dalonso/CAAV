import base64
import os
import re
from pathlib import Path

from app.ferramentas.extratus_aburesi.core.prompt_manager import carregar_instrucoes_relatorio
from app.ferramentas.extratus_aburesi.core.texto_manager import (
    extrair_paginas_pdf,
    extrair_texto_pdf_com_diagnostico,
)


MODELO_PADRAO = "claude-sonnet-5"

# Modelo mais barato usado só na etapa de "pedaço" de um processo dividido
# (ver TOKENS_POR_PEDACO_DIVISAO e `_montar_parametros_pedaco`). Essa etapa
# só faz extração literal do trecho (datas, atos, documentos vistos), sem
# nenhum julgamento jurídico — um modelo mais simples dá conta igual e
# custa metade do preço (ver PRECOS_POR_MILHAO_USD). A etapa que de fato
# escreve o parecer (redução final, `_montar_parametros_reducao`) continua
# no modelo padrão. Henrique, 2026-08-12: "queremos baratear o máximo
# possível" — adotado como parte da rodada de eficiência de custo (mesma
# mudança em app/ferramentas/extratus, é infraestrutura de custo, não
# lógica de geração de relatório).
MODELO_PEDACO = "claude-haiku-4-5"

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

# Deixamos uma folga generosa da janela real de 1 milhão de tokens do
# modelo (Sonnet 5) — ~200 mil de sobra pro prompt, o schema da ferramenta
# e a resposta. Corrigido em 2026-08-12: o valor antigo (150 mil) partia de
# uma suposição desatualizada de janela de 200 mil tokens (gerações antigas
# do Sonnet) — documentos grandes estavam sendo divididos em pedaços à toa,
# pagando várias chamadas de saída (mais cara) em vez de uma só, e caindo
# em "revisão" automaticamente mesmo sem precisar.
LIMITE_TOKENS_TEXTO_EXTRAIDO = 800_000

# A Anthropic rejeita (HTTP 413) requisições acima de 32MB. Um PDF em
# base64 fica ~1,33x maior que o arquivo original — por isso o teto aqui
# é mais conservador que 32MB. Confirmado com teste real em 2026-07-29:
# um PDF de 34,2MB (979 páginas) foi rejeitado de fato com esse erro.
LIMITE_MB_ARQUIVO_PARA_PDF_NATIVO = 24

# Preço promocional por milhão de tokens (entrada, saída), válido até
# 31/08/2026 (depois disso o padrão sobe pra $3/$15 — lembrar de atualizar).
# Isso é só uma ESTIMATIVA pra acompanhar gasto dentro do sistema — a fatura
# real da Anthropic é que vale de verdade. Testado em 25/07/2026: o cálculo
# aqui deu US$ 0,64 pra uma chamada que a fatura real cobrou US$ 0,85 —
# ainda não sabemos a causa exata da diferença (possível custo extra de
# processar PDF/imagem não refletido em usage.input_tokens). Tratar estes
# números como piso, não teto.
#
# Indexado por modelo (não só um preço fixo) desde que MODELO_PEDACO existe:
# `extrair_dados_e_uso` olha QUAL modelo respondeu de verdade
# (`resposta.model`) pra cobrar certo — sem isso, a etapa de pedaço (que
# roda no modelo mais barato) apareceria no Histórico com o preço do modelo
# padrão, inflando o custo mostrado sem inflar o custo real.
PRECOS_POR_MILHAO_USD = {
    MODELO_PADRAO: (2.00, 10.00),
    MODELO_PEDACO: (1.00, 5.00),
}

# Batch API (usado só pelo Motor, ver motor_lote.py): 50% de desconto em
# cima de TODOS os preços acima — entrada, saída e cache. Confirmado com
# teste real em 2026-07-29.
DESCONTO_BATCH_API = 0.5

# Tamanho de cada pedaço quando um processo é grande demais pra uma
# chamada só (ver `_dividir_paginas_em_pedacos` / `gerar_relatorio_claude_dividido`).
# Bem abaixo do limite de uma chamada única (800k) de propósito: cada
# pedaço ainda carrega o prompt inteiro (cacheado) e precisa sobrar espaço
# pra resposta — prioriza nunca estourar contexto sobre economizar uma
# chamada a mais. Subido de 80k pra 200k em 2026-08-12 junto com
# LIMITE_TOKENS_TEXTO_EXTRAIDO: como a divisão em pedaços passou a ser bem
# mais rara, quando ainda assim for necessária (documentos realmente
# enormes), pedaços maiores significam menos chamadas pagas por documento.
# Só usado no fluxo síncrono (fila manual) por enquanto — o Motor/Batch API
# não suporta uma sequência de chamadas dependentes dentro de um único item
# de lote, então processos grandes no Motor continuam caindo em erro claro,
# como hoje.
TOKENS_POR_PEDACO_DIVISAO = 200_000

# --- Triagem de anexos de listagem de terceiros (ex: cessão de carteira
# de crédito entre instituições financeiras) ---
#
# Descoberto em 2026-08-03: os 2 documentos reais mais caros/pesados da
# amostra de teste tinham a maior parte do tamanho vindo de um anexo
# desse tipo — uma lista enorme de CLIENTES DE TERCEIROS (nomes, CPFs,
# contratos), sem nenhuma relação com o processo em si, só provando que
# a dívida foi transferida em lote entre instituições. Confirmado
# manualmente por Henrique olhando os PDFs reais antes de aprovar isso.
#
# Detecção por 2 sinais estruturais verificáveis (não é adivinhação de
# conteúdo) — uma página só é considerada suspeita quando os DOIS
# aparecem juntos, de propósito conservador:
#   1. Muitos CPF/CNPJ DIFERENTES na mesma página — uma página normal
#      do processo cita no máximo 1-2 (as partes do caso).
#   2. A página tem sua própria numeração interna ("Página X de Y") —
#      sinal de que é um documento anexado à parte, não o corpo do
#      processo em si.
# Validado empiricamente contra os 2 documentos reais: os dois sinais
# batem quase exatamente com o bloco que uma leitura humana confirmou
# ser a lista de terceiros, nos dois casos.
PADRAO_CPF_CNPJ = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
PADRAO_NUMERACAO_PROPRIA = re.compile(r"P[áa]gina \d+ de \d+")
MINIMO_CPFS_PARA_SUSPEITA = 10


def _pagina_parece_lista_de_terceiros(texto_pagina):
    cpfs_diferentes = set(PADRAO_CPF_CNPJ.findall(texto_pagina))
    tem_numeracao_propria = bool(PADRAO_NUMERACAO_PROPRIA.search(texto_pagina))
    return len(cpfs_diferentes) >= MINIMO_CPFS_PARA_SUSPEITA and tem_numeracao_propria


def filtrar_paginas_lista_de_terceiros(paginas):
    """Separa páginas que parecem ser um anexo de listagem de terceiros
    das páginas relevantes do processo. NUNCA descarta escondido: sempre
    devolve também a lista de números de página excluídos, pra quem
    chamar registrar isso (log, aviso pra IA, forçar revisão humana —
    ver `montar_diagnostico_com_triagem`, `pipeline.processar_pdf` e
    `motor_lote._preparar_novo_lote`)."""
    relevantes = []
    excluidas = []

    for pagina in paginas:
        if _pagina_parece_lista_de_terceiros(pagina["texto_bruto"]):
            excluidas.append(pagina["numero"])
        else:
            relevantes.append(pagina)

    return relevantes, excluidas


def montar_diagnostico_com_triagem(caminho_pdf):
    """Extrai o diagnóstico do PDF e, se não for um PDF digitalizado,
    aplica o filtro de anexos de listagem de terceiros antes de decidir
    o que fazer com o processo. A checagem de "parece digitalizado"
    sempre olha TODAS as páginas (antes do filtro) — filtrar primeiro
    poderia distorcer essa proporção à toa, já que a triagem só faz
    sentido pro caminho de texto extraído.

    Devolve (diagnostico, paginas_relevantes_ou_None, paginas_excluidas).
    `paginas_relevantes` só vem preenchido quando o filtro rodou (não é
    PDF digitalizado) — evita quem chamar precisar reextrair/refiltrar
    de novo se for pro caminho de divisão em pedaços."""
    caminho_pdf = Path(caminho_pdf)
    diagnostico_original = extrair_texto_pdf_com_diagnostico(caminho_pdf)

    if parece_digitalizado(diagnostico_original["total_paginas"], diagnostico_original["paginas_sem_texto"]):
        return diagnostico_original, None, []

    paginas, _ = extrair_paginas_pdf(caminho_pdf)
    paginas_relevantes, paginas_excluidas = filtrar_paginas_lista_de_terceiros(paginas)

    if not paginas_excluidas:
        return diagnostico_original, paginas, []

    texto_filtrado = "\n\n".join(p["texto_marcado"] for p in paginas_relevantes)
    aviso = (
        f"(Aviso: {len(paginas_excluidas)} página(s) deste processo foram identificadas "
        "como um anexo de listagem de terceiros não relacionados ao caso (ex: cessão de "
        "carteira de crédito entre instituições financeiras) e foram removidas desta "
        "análise para reduzir custo. Se isso for um engano, considere que informações "
        "relevantes podem estar ausentes.)\n\n"
    )

    diagnostico_filtrado = {
        "texto": aviso + texto_filtrado,
        "total_paginas": diagnostico_original["total_paginas"],
        "paginas_sem_texto": diagnostico_original["paginas_sem_texto"],
        "caracteres": len(texto_filtrado),
    }

    return diagnostico_filtrado, paginas_relevantes, paginas_excluidas


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


# Schema "mapa" — usado só nos pedaços de um processo dividido, nunca no
# relatório final. Deliberadamente menor que FERRAMENTA_RELATORIO: um
# trecho não tem visão do processo inteiro, então não faz sentido pedir
# parecer/status_atual/prazos ali — isso só é escrito na chamada de
# redução, depois de juntar o que todos os trechos trouxerem.
FERRAMENTA_PEDACO = {
    "name": "registrar_trecho",
    "description": (
        "Registra o que foi identificado NESTE TRECHO de um processo "
        "grande, dividido em partes — não é o relatório final, só o "
        "material bruto desse pedaço."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cronologia": {
                "type": "array",
                "description": "Eventos jurídicos relevantes encontrados NESTE TRECHO, em ordem cronológica.",
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
            "documentos_identificados": {
                "type": "array",
                "description": (
                    "Lista curta dos documentos/petições/decisões que aparecem "
                    "neste trecho (ex: \"petição inicial\", \"decisão liminar\", "
                    "\"contestação\", \"laudo de avaliação\") — usada depois pra "
                    "conferir se algum documento parece faltar no processo todo."
                ),
                "items": {"type": "string"},
            },
            "campos_processo": {
                "type": "object",
                "description": (
                    "Preencha SÓ os campos que você encontrar de fato neste "
                    "trecho. Não invente nem repita um palpite — deixe de fora "
                    "o que não aparecer aqui, outro trecho pode ter essa "
                    "informação."
                ),
                "properties": {
                    "tipo_acao": {"type": "string"},
                    "incidente": {"type": "string"},
                    "valor_causa": {"type": "string"},
                    "valor_divida": {"type": "string"},
                    "autor": {"type": "string"},
                    "reu": {"type": "string"},
                    "bem": {"type": "string"},
                    "contrato": {"type": "string"},
                    "comarca": {"type": "string"},
                },
            },
        },
        "required": ["cronologia", "documentos_identificados"],
    },
}


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
    em tempo real (fila manual) usam o preço cheio normalmente.

    O preço usado é sempre o do modelo que respondeu de verdade
    (`resposta.model`), não um preço fixo — necessário desde que
    MODELO_PEDACO existe (a etapa de pedaço roda mais barato que a
    padrão). `resposta.model` ausente (só acontece em resposta fake de
    teste) cai no preço do modelo padrão."""
    bloco_ferramenta = next(
        (bloco for bloco in resposta.content if bloco.type == "tool_use"),
        None,
    )

    if not bloco_ferramenta:
        raise RuntimeError("Claude não devolveu os dados estruturados esperados.")

    dados = dict(bloco_ferramenta.input)

    modelo = getattr(resposta, "model", None) or MODELO_PADRAO
    preco_entrada, preco_saida = PRECOS_POR_MILHAO_USD.get(modelo, PRECOS_POR_MILHAO_USD[MODELO_PADRAO])
    # Cache de prompt: escrita (primeira vez) custa 1,25x o preço normal de
    # entrada; leitura (reaproveitando o que já foi escrito, dentro de
    # ~5min) custa só 10% do preço normal — mesma proporção em qualquer
    # modelo, só muda o preço-base de entrada.
    preco_cache_escrita = preco_entrada * 1.25
    preco_cache_leitura = preco_entrada * 0.10

    tokens_entrada = resposta.usage.input_tokens
    tokens_saida = resposta.usage.output_tokens
    tokens_cache_escrita = getattr(resposta.usage, "cache_creation_input_tokens", 0) or 0
    tokens_cache_leitura = getattr(resposta.usage, "cache_read_input_tokens", 0) or 0

    multiplicador = (1 - DESCONTO_BATCH_API) if via_batch else 1

    custo_estimado = multiplicador * (
        tokens_entrada / 1_000_000 * preco_entrada
        + tokens_saida / 1_000_000 * preco_saida
        + tokens_cache_escrita / 1_000_000 * preco_cache_escrita
        + tokens_cache_leitura / 1_000_000 * preco_cache_leitura
    )

    uso_ia = {
        "modelo": modelo,
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
            * (preco_entrada - preco_cache_leitura)
        )
        print(
            f"[cache] {tokens_cache_leitura} tokens vieram do cache "
            f"(economia estimada de US$ {economia_estimada:.4f} nesta chamada)."
        )

    return dados, uso_ia


def _dividir_paginas_em_pedacos(paginas, limite_tokens_por_pedaco=TOKENS_POR_PEDACO_DIVISAO):
    """Agrupa páginas (na ordem original) em pedaços, cada um ficando
    abaixo do limite de tokens estimado — nunca corta uma página ao
    meio. Sempre devolve pelo menos 1 página por pedaço, mesmo que uma
    página sozinha já exceda o limite (caso raríssimo, mas não pode
    travar em loop nem descartar conteúdo)."""
    pedacos = []
    pedaco_atual = []
    tokens_pedaco_atual = 0

    for pagina in paginas:
        tokens_pagina = estimar_tokens_texto(pagina["texto_marcado"])

        if pedaco_atual and (tokens_pedaco_atual + tokens_pagina) > limite_tokens_por_pedaco:
            pedacos.append(pedaco_atual)
            pedaco_atual = []
            tokens_pedaco_atual = 0

        pedaco_atual.append(pagina)
        tokens_pedaco_atual += tokens_pagina

    if pedaco_atual:
        pedacos.append(pedaco_atual)

    return ["\n\n".join(p["texto_marcado"] for p in pedaco) for pedaco in pedacos]


def _montar_parametros_pedaco(texto_pedaco, indice, total, processo_detectado, instrucoes):
    pedido = (
        f"Este é o TRECHO {indice} de {total} de um processo judicial grande "
        "demais para ser lido de uma vez só (número detectado no nome do "
        f"arquivo: {processo_detectado or 'não identificado'}). Leia SÓ este "
        "trecho e registre o que encontrar nele — a síntese final do "
        "processo inteiro será feita depois, juntando o que cada trecho "
        "trouxer. Não tente adivinhar o que está nos outros trechos."
    )

    return {
        "model": MODELO_PEDACO,
        "max_tokens": 4096,
        "system": [
            {
                "type": "text",
                "text": instrucoes,
                # Mesmo texto (prompt) em toda chamada de pedaço E na de
                # redução — cacheado uma vez, lido barato (10% do preço)
                # em todas as chamadas seguintes do mesmo processo. Cache é
                # por modelo, então o pedaço (Haiku) e a redução (Sonnet)
                # escrevem/leem caches separados entre si — cada um ainda
                # aproveita cache dos outros pedaços do MESMO processo.
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "tools": [FERRAMENTA_PEDACO],
        "tool_choice": {"type": "tool", "name": "registrar_trecho"},
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": f"{pedido}\n\n{texto_pedaco}"}]}
        ],
    }


def _agregar_pedacos(resultados_pedacos):
    """Junta o que cada pedaço encontrou numa estrutura só, pronta pra
    virar o texto de entrada da chamada de redução. Não decide qual
    valor é "o certo" quando pedaços divergem num campo — passa todos os
    candidatos adiante pra chamada final decidir, já com o processo
    inteiro em vista (a mesma lógica de um humano juntando anotações de
    vários revisores antes de escrever a versão final)."""
    cronologia_completa = []
    documentos_por_pedaco = []
    campos_candidatos = {}

    for indice, resultado in enumerate(resultados_pedacos, start=1):
        cronologia_completa.extend(resultado.get("cronologia") or [])
        documentos_por_pedaco.append((indice, resultado.get("documentos_identificados") or []))

        for campo, valor in (resultado.get("campos_processo") or {}).items():
            if not valor:
                continue
            candidatos = campos_candidatos.setdefault(campo, [])
            if valor not in candidatos:
                candidatos.append(valor)

    return cronologia_completa, documentos_por_pedaco, campos_candidatos


def _formatar_resumo_para_reducao(cronologia_completa, documentos_por_pedaco, campos_candidatos, total_pedacos):
    linhas = [
        f"Este processo foi dividido em {total_pedacos} trechos pra leitura "
        "(era grande demais pra uma chamada só). Abaixo está o que foi "
        "identificado em cada trecho, já reunido — use isso pra montar o "
        "relatório final, incluindo a conferência de completude do "
        "checklist de qualidade (algum documento parece faltar, por exemplo).",
        "",
        "=== Linha do tempo encontrada (todos os trechos, junte/ordene por data) ===",
    ]

    for evento in cronologia_completa:
        linhas.append(f"- {evento.get('data', '?')} | {evento.get('ator', '?')} | {evento.get('descricao', '')}")

    linhas.append("")
    linhas.append("=== Documentos identificados, por trecho ===")
    for indice, documentos in documentos_por_pedaco:
        if documentos:
            linhas.append(f"Trecho {indice}: " + "; ".join(documentos))
        else:
            linhas.append(f"Trecho {indice}: (nenhum documento específico identificado)")

    linhas.append("")
    linhas.append(
        "=== Campos do processo encontrados (mais de um valor = trechos "
        "divergiram, escolha o mais provável/completo) ==="
    )
    for campo, valores in campos_candidatos.items():
        linhas.append(f"{campo}: {' | '.join(valores)}")

    return "\n".join(linhas)


def _montar_parametros_reducao(resumo_texto, processo_detectado, instrucoes):
    pedido_analise = (
        "Este é o RESUMO CONSOLIDADO de um processo judicial grande, já "
        "dividido e pré-analisado em trechos (número detectado no nome do "
        f"arquivo: {processo_detectado or 'não identificado'}). Preencha o "
        "relatório final com base neste resumo — não é o PDF original, é "
        "a reunião do que cada trecho trouxe."
    )

    return {
        "model": MODELO_PADRAO,
        "max_tokens": 8192,
        "system": [
            {
                "type": "text",
                "text": instrucoes + _instrucao_formato(),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "tools": [FERRAMENTA_RELATORIO],
        "tool_choice": {"type": "tool", "name": "preencher_relatorio"},
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": f"{pedido_analise}\n\n{resumo_texto}"}]}
        ],
    }


def gerar_relatorio_claude_dividido(caminho_pdf, processo_detectado, cliente, instrucoes, paginas=None):
    """Processo grande demais pra uma chamada só: divide em pedaços por
    página, manda cada um pra IA extrair só o que está naquele trecho
    (mapa), depois junta tudo numa chamada final que monta o relatório
    completo (redução). Só usada pelo fluxo síncrono (fila manual) — ver
    nota em TOKENS_POR_PEDACO_DIVISAO sobre o Motor/Batch API.

    `paginas`, se vier preenchido, já passou pela triagem de anexos de
    listagem de terceiros (`montar_diagnostico_com_triagem`) — evita
    reextrair/refiltrar o PDF de novo. Se vier None, extrai sem filtro
    nenhum (uso direto/teste).

    Sempre marca `dividido: True` no uso retornado — `pipeline.processar_pdf`
    usa essa marca pra forçar confiança "revisão" nesse caso, já que é um
    caminho mais novo e mais complexo que o de chamada única."""
    caminho_pdf = Path(caminho_pdf)
    if paginas is None:
        paginas, _ = extrair_paginas_pdf(caminho_pdf)
    pedacos_texto = _dividir_paginas_em_pedacos(paginas)
    total_pedacos = len(pedacos_texto)

    resultados_pedacos = []
    usos_pedacos = []

    for indice, texto_pedaco in enumerate(pedacos_texto, start=1):
        parametros = _montar_parametros_pedaco(
            texto_pedaco, indice, total_pedacos, processo_detectado, instrucoes
        )
        resposta = cliente.messages.create(**parametros)
        dados_pedaco, uso_pedaco = extrair_dados_e_uso(resposta)
        resultados_pedacos.append(dados_pedaco)
        usos_pedacos.append(uso_pedaco)

    cronologia_completa, documentos_por_pedaco, campos_candidatos = _agregar_pedacos(resultados_pedacos)
    resumo_texto = _formatar_resumo_para_reducao(
        cronologia_completa, documentos_por_pedaco, campos_candidatos, total_pedacos
    )

    parametros_reducao = _montar_parametros_reducao(resumo_texto, processo_detectado, instrucoes)
    resposta_reducao = cliente.messages.create(**parametros_reducao)
    dados_finais, uso_reducao = extrair_dados_e_uso(resposta_reducao)

    uso_total = {
        "modelo": MODELO_PADRAO,
        "tokens_entrada": sum(u["tokens_entrada"] for u in usos_pedacos) + uso_reducao["tokens_entrada"],
        "tokens_saida": sum(u["tokens_saida"] for u in usos_pedacos) + uso_reducao["tokens_saida"],
        "custo_estimado_usd": round(
            sum(u["custo_estimado_usd"] for u in usos_pedacos) + uso_reducao["custo_estimado_usd"], 4
        ),
        "dividido": True,
        "total_pedacos": total_pedacos,
    }

    return dados_finais, uso_total


def montar_parametros_mensagem(caminho_pdf, processo_detectado, instrucoes, diagnostico=None):
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
    if diagnostico is None:
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

    caminho_pdf = Path(caminho_pdf)
    diagnostico, paginas_relevantes, paginas_excluidas_triagem = montar_diagnostico_com_triagem(caminho_pdf)

    precisa_dividir = (
        not parece_digitalizado(diagnostico["total_paginas"], diagnostico["paginas_sem_texto"])
        and estimar_tokens_texto(diagnostico["texto"]) > LIMITE_TOKENS_TEXTO_EXTRAIDO
    )

    if precisa_dividir:
        dados, uso = gerar_relatorio_claude_dividido(
            caminho_pdf, processo_detectado, cliente, instrucoes, paginas=paginas_relevantes
        )
    else:
        parametros = montar_parametros_mensagem(caminho_pdf, processo_detectado, instrucoes, diagnostico=diagnostico)
        resposta = cliente.messages.create(**parametros)
        dados, uso = extrair_dados_e_uso(resposta)

    if paginas_excluidas_triagem:
        uso["paginas_excluidas_triagem"] = paginas_excluidas_triagem

    return dados, uso


def gerar_relatorio(caminho_pdf, processo_detectado, ia_provider):
    """Ver docstring equivalente em app/ferramentas/extratus/core/
    ia_cliente.py (Extratus - Relatórios) — mesma lógica, "modo
    simulado" removido junto (Henrique, 2026-08-11)."""
    if str(ia_provider).strip().lower() == "claude":
        return gerar_relatorio_claude(caminho_pdf, processo_detectado)

    raise ValueError(f"Provedor de IA não suportado: {ia_provider!r}")
