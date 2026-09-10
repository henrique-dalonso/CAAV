"""Gancho de pós-processamento do tipo "condenacao" (ver
nucleo_relatorios/tipos.py::TipoRelatorio.pos_processar), chamado por
core/pipeline.py::finalizar_processamento logo depois da IA responder.

Responsabilidade única: transformar os fatos brutos que a IA extraiu (por
item: descrição, data-base, valor singelo, juros compensatórios, e uma
ESTIMATIVA de fallback de valor atualizado/juros moratórios) num cálculo
de verdade. Pra cada item, se o índice informado é um dos nacionais
automatizáveis (ver calculadores/correcao_monetaria.py), busca a taxa
oficial ao vivo no Banco Central e recalcula — a estimativa da IA só
sobrevive pro relatório final quando isso não é possível (índice de
tabela de tribunal local, sem fonte automática conhecida, ou uma falha
pontual na chamada à API). Toda a aritmética de agregação daqui pra frente
(total de linha, TOTAIS, subtotais, multa/honorários do art. 523, TOTAL
GERAL) é sempre conta pura em código, nunca pedida à IA — ver comentário
em FERRAMENTA_CONDENACAO (ia_cliente.py) sobre por quê.

Simplificação deliberada nesta primeira versão: `honorarios_incide_sobre_
multa` (extraído da IA) é passado pro relatório apenas como informação —
não altera a base de cálculo dos honorários automaticamente, porque a
regra exata de como isso afeta a conta (se o percentual de honorários
recai sobre a multa do art. 523 também, ou só sobre o subtotal anterior)
não estava clara o bastante nos parâmetros pra codificar sem risco de
acertar errado. Fica sinalizado no relatório pra conferência humana —
revisitar se isso gerar divergência real em uso."""

import re

from app.ferramentas.nucleo_relatorios.calculadores.correcao_monetaria import (
    INDICES_NACIONAIS_RECONHECIDOS,
    atualizar_por_indice,
    calcular_juros_moratorios_simples,
)


PERCENTUAL_MULTA_523 = 10.0
PERCENTUAL_HONORARIOS_523 = 10.0

# Extrai só o primeiro número (aceita vírgula decimal) de dentro do texto,
# ignorando qualquer coisa em volta — achado real testando contra a API:
# a IA respondeu "1% ao mês" (não "1%" puro) pra taxa_juros_moratorios, e
# um `float()` direto quebrava nisso silenciosamente (capturado pelo
# try/except, virando 0.0 sem erro nenhum aparecer — juros moratórios
# saíam sempre zerados). Nunca trocar por `float()` direto de novo.
_PADRAO_NUMERO = re.compile(r"(\d+(?:[.,]\d+)?)")


def _extrair_percentual(texto_percentual):
    """"10%" -> 10.0, "10% ao mês" -> 10.0, "" / None -> 0.0. Tolerante a
    texto ao redor do número e a vírgula decimal, já que vem de texto
    livre extraído pela IA (ver comentário acima do regex)."""
    if not texto_percentual:
        return 0.0
    correspondencia = _PADRAO_NUMERO.search(str(texto_percentual).replace(",", "."))
    if not correspondencia:
        return 0.0
    try:
        return float(correspondencia.group(1))
    except ValueError:
        return 0.0


def _calcular_item(item, indice_correcao, taxa_juros_moratorios):
    valor_singelo = item.get("valor_singelo") or 0.0
    juros_compensatorios = item.get("juros_compensatorios") or 0.0
    data_base = item.get("data")

    indice_automatizavel = indice_correcao in INDICES_NACIONAIS_RECONHECIDOS
    calculado_automaticamente = False
    meses_sem_indice_publicado = []

    if indice_automatizavel and data_base:
        try:
            resultado = atualizar_por_indice(indice_correcao, data_base=data_base, valor_singelo=valor_singelo)
            valor_atualizado = resultado["valor_atualizado"]
            meses_sem_indice_publicado = resultado["meses_sem_indice_publicado"]

            if indice_correcao == "SELIC":
                # SELIC já embute juros — ver docstring de
                # correcao_monetaria.atualizar_por_indice, nunca soma juros
                # de mora por cima aqui.
                juros_moratorios = 0.0
            else:
                juros_moratorios = calcular_juros_moratorios_simples(
                    valor_singelo, _extrair_percentual(taxa_juros_moratorios), data_base
                )

            calculado_automaticamente = True
        except Exception:
            # Falha pontual (rede fora, data num formato inesperado etc.)
            # nunca derruba o relatório inteiro — cai pro fallback da IA,
            # sinalizado como não-automático pro humano conferir.
            valor_atualizado = item.get("valor_atualizado_estimado_ia") or 0.0
            juros_moratorios = item.get("juros_moratorios_estimados_ia") or 0.0
    else:
        valor_atualizado = item.get("valor_atualizado_estimado_ia") or 0.0
        juros_moratorios = item.get("juros_moratorios_estimados_ia") or 0.0

    total = valor_atualizado + juros_compensatorios + juros_moratorios

    return {
        "descricao": item.get("descricao", ""),
        "data": data_base,
        "valor_singelo": valor_singelo,
        "valor_atualizado": valor_atualizado,
        "juros_compensatorios": juros_compensatorios,
        "juros_moratorios": juros_moratorios,
        "total": total,
        "calculado_automaticamente": calculado_automaticamente,
        "meses_sem_indice_publicado": meses_sem_indice_publicado,
    }


def _sem_condenacao_liquida(dados):
    dados["itens_calculo_processados"] = []
    dados["totais"] = None
    dados["subtotal_1"] = None
    dados["honorarios_valor"] = None
    dados["subtotal_2"] = None
    dados["aplica_multa_523"] = False
    dados["multa_523_valor"] = None
    dados["honorarios_523_valor"] = None
    dados["total_geral"] = None
    dados["recomendacao_texto"] = ""

    campos_extra_job = {
        "condenacao_recomendacao": None,
        "condenacao_valor_total_geral": None,
    }
    return dados, campos_extra_job


def processar_condenacao(dados):
    """`dados` é o dict devolvido por `ia_cliente.extrair_dados_e_uso`
    (chaves batendo com `FERRAMENTA_CONDENACAO`). Devolve
    `(dados_enriquecidos, campos_extra_job)` — ver docstring de
    `TipoRelatorio.pos_processar`."""
    dados = dict(dados)

    if not dados.get("tem_condenacao_liquida"):
        return _sem_condenacao_liquida(dados)

    indice_correcao = (dados.get("indice_correcao") or "").strip()
    taxa_juros_moratorios = dados.get("taxa_juros_moratorios") or ""

    itens_processados = [
        _calcular_item(item, indice_correcao, taxa_juros_moratorios)
        for item in dados.get("itens_calculo", [])
    ]

    totais = {
        "valor_singelo": sum(item["valor_singelo"] for item in itens_processados),
        "valor_atualizado": sum(item["valor_atualizado"] for item in itens_processados),
        "juros_compensatorios": sum(item["juros_compensatorios"] for item in itens_processados),
        "juros_moratorios": sum(item["juros_moratorios"] for item in itens_processados),
        "total": sum(item["total"] for item in itens_processados),
    }

    subtotal_1 = totais["total"]

    percentual_honorarios = _extrair_percentual(dados.get("honorarios_percentual"))
    honorarios_valor = subtotal_1 * (percentual_honorarios / 100)
    subtotal_2 = subtotal_1 + honorarios_valor

    aplica_multa_523 = bool(dados.get("em_cumprimento_sentenca")) and bool(dados.get("prazo_523_transcorrido"))
    if aplica_multa_523:
        multa_523_valor = subtotal_2 * (PERCENTUAL_MULTA_523 / 100)
        honorarios_523_valor = subtotal_2 * (PERCENTUAL_HONORARIOS_523 / 100)
    else:
        multa_523_valor = 0.0
        honorarios_523_valor = 0.0

    total_geral = subtotal_2 + multa_523_valor + honorarios_523_valor

    # Texto pronto pro molde do Word só encaixar — evita o molde precisar
    # de lógica condicional própria pra decidir o rótulo (mesma filosofia
    # de "esqueleto fixo montado por código" já usada no e-mail da Emenda).
    dados["recomendacao_texto"] = "IMPUGNAR" if dados.get("recomendacao_impugnar") else "NÃO IMPUGNAR"

    dados["itens_calculo_processados"] = itens_processados
    dados["totais"] = totais
    dados["subtotal_1"] = subtotal_1
    dados["honorarios_valor"] = honorarios_valor
    dados["subtotal_2"] = subtotal_2
    dados["aplica_multa_523"] = aplica_multa_523
    dados["multa_523_valor"] = multa_523_valor
    dados["honorarios_523_valor"] = honorarios_523_valor
    dados["total_geral"] = total_geral

    campos_extra_job = {
        "condenacao_recomendacao": "impugnar" if dados.get("recomendacao_impugnar") else "nao_impugnar",
        "condenacao_valor_total_geral": total_geral,
    }

    return dados, campos_extra_job
