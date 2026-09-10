"""Testes da agregação de `pos_processamento_condenacao.py`. Sempre mocka
`atualizar_por_indice`/`calcular_juros_moratorios_simples` — a matemática
financeira em si (composição de índice, regra da SELIC) já tem sua própria
suíte dedicada em test_correcao_monetaria.py; aqui o foco é só a
sequência de agregação (total de linha -> TOTAIS -> subtotais -> multa/
honorários 523 -> TOTAL GERAL), na ordem exata do documento do Henrique."""

import app.ferramentas.nucleo_relatorios.core.pos_processamento_condenacao as modulo
from app.ferramentas.nucleo_relatorios.core.pos_processamento_condenacao import _extrair_percentual, processar_condenacao


def _dados_base(**overrides):
    dados = {
        "tem_condenacao_liquida": True,
        "indice_correcao": "tabela_tribunal_local",
        "taxa_juros_moratorios": "1% ao mês",
        "em_cumprimento_sentenca": False,
        "prazo_523_transcorrido": False,
        "honorarios_percentual": "",
        "recomendacao_impugnar": False,
        "itens_calculo": [],
    }
    dados.update(overrides)
    return dados


def test_extrair_percentual_tolera_texto_ao_redor_do_numero():
    """Achado real testando contra a API: a IA respondeu "1% ao mês" (não
    "1%" puro) pra taxa_juros_moratorios — um `float()` direto quebrava
    nisso silenciosamente (try/except mascarava, virando 0.0 sem erro
    nenhum aparecer, juros moratórios sempre zerados)."""
    assert _extrair_percentual("1% ao mês") == 1.0
    assert _extrair_percentual("10%") == 10.0
    assert _extrair_percentual("12,5% ao ano") == 12.5
    assert _extrair_percentual("") == 0.0
    assert _extrair_percentual(None) == 0.0
    assert _extrair_percentual("não identificado") == 0.0


def test_juros_moratorios_usa_taxa_com_texto_ao_redor_sem_zerar(monkeypatch):
    """Mesma regressão do teste acima, mas na integração real com
    `calcular_juros_moratorios_simples` (sem mockar essa função) — prova
    que a taxa chega corretamente convertida pro cálculo de verdade."""
    monkeypatch.setattr(
        modulo, "atualizar_por_indice",
        lambda indice, data_base, valor_singelo: {
            "valor_atualizado": valor_singelo, "juros_moratorios": None,
            "fator_acumulado": 1.0, "meses_sem_indice_publicado": [],
        },
    )

    dados = _dados_base(indice_correcao="IPCA", taxa_juros_moratorios="1% ao mês", itens_calculo=[
        {"descricao": "Capital", "data": "01/01/2026", "valor_singelo": 1000.0, "juros_compensatorios": 0.0,
         "valor_atualizado_estimado_ia": 0.0, "juros_moratorios_estimados_ia": 0.0},
    ])
    resultado, _ = processar_condenacao(dados)

    assert resultado["itens_calculo_processados"][0]["juros_moratorios"] > 0.0


def test_sem_condenacao_liquida_devolve_totais_none_e_nao_quebra():
    dados, campos_extra = processar_condenacao(_dados_base(tem_condenacao_liquida=False, itens_calculo=[
        {"descricao": "x", "data": "01/01/2026", "valor_singelo": 100.0, "juros_compensatorios": 0.0,
         "valor_atualizado_estimado_ia": 0.0, "juros_moratorios_estimados_ia": 0.0},
    ]))

    assert dados["total_geral"] is None
    assert dados["itens_calculo_processados"] == []
    assert campos_extra == {"condenacao_recomendacao": None, "condenacao_valor_total_geral": None}


def test_indice_nao_automatizavel_usa_estimativa_da_ia_sem_chamar_calculadora(monkeypatch):
    def explode(*a, **k):
        raise AssertionError("não deveria chamar atualizar_por_indice pra tabela_tribunal_local")

    monkeypatch.setattr(modulo, "atualizar_por_indice", explode)

    dados = _dados_base(itens_calculo=[
        {"descricao": "Capital", "data": "01/01/2026", "valor_singelo": 1000.0, "juros_compensatorios": 0.0,
         "valor_atualizado_estimado_ia": 1050.0, "juros_moratorios_estimados_ia": 30.0},
    ])
    resultado, _ = processar_condenacao(dados)

    item = resultado["itens_calculo_processados"][0]
    assert item["calculado_automaticamente"] is False
    assert item["valor_atualizado"] == 1050.0
    assert item["juros_moratorios"] == 30.0
    assert item["total"] == 1080.0  # 1050 + 0 (compensatorios) + 30


def test_indice_automatizavel_substitui_estimativa_da_ia_pelo_valor_calculado(monkeypatch):
    monkeypatch.setattr(
        modulo, "atualizar_por_indice",
        lambda indice, data_base, valor_singelo: {
            "valor_atualizado": 1100.0, "juros_moratorios": None,
            "fator_acumulado": 1.1, "meses_sem_indice_publicado": [],
        },
    )
    monkeypatch.setattr(modulo, "calcular_juros_moratorios_simples", lambda *a, **k: 25.0)

    dados = _dados_base(indice_correcao="IPCA", itens_calculo=[
        {"descricao": "Capital", "data": "01/01/2026", "valor_singelo": 1000.0, "juros_compensatorios": 5.0,
         "valor_atualizado_estimado_ia": 999999.0, "juros_moratorios_estimados_ia": 999999.0},  # nunca deveriam aparecer
    ])
    resultado, _ = processar_condenacao(dados)

    item = resultado["itens_calculo_processados"][0]
    assert item["calculado_automaticamente"] is True
    assert item["valor_atualizado"] == 1100.0
    assert item["juros_moratorios"] == 25.0
    assert item["total"] == 1130.0  # 1100 + 5 (compensatorios, sempre da IA) + 25


def test_selic_zera_juros_moratorios_mesmo_com_taxa_informada(monkeypatch):
    monkeypatch.setattr(
        modulo, "atualizar_por_indice",
        lambda indice, data_base, valor_singelo: {
            "valor_atualizado": 1080.0, "juros_moratorios": 0.0,
            "fator_acumulado": 1.08, "meses_sem_indice_publicado": [],
        },
    )

    def explode(*a, **k):
        raise AssertionError("SELIC nao deveria chamar calculo de juros moratorios separado")

    monkeypatch.setattr(modulo, "calcular_juros_moratorios_simples", explode)

    dados = _dados_base(indice_correcao="SELIC", taxa_juros_moratorios="SELIC", itens_calculo=[
        {"descricao": "Capital", "data": "01/01/2026", "valor_singelo": 1000.0, "juros_compensatorios": 0.0,
         "valor_atualizado_estimado_ia": 0.0, "juros_moratorios_estimados_ia": 0.0},
    ])
    resultado, _ = processar_condenacao(dados)

    assert resultado["itens_calculo_processados"][0]["juros_moratorios"] == 0.0


def test_falha_na_api_cai_pro_fallback_sem_quebrar(monkeypatch):
    def explode(*a, **k):
        raise ConnectionError("BCB fora do ar")

    monkeypatch.setattr(modulo, "atualizar_por_indice", explode)

    dados = _dados_base(indice_correcao="IPCA", itens_calculo=[
        {"descricao": "Capital", "data": "01/01/2026", "valor_singelo": 1000.0, "juros_compensatorios": 0.0,
         "valor_atualizado_estimado_ia": 1020.0, "juros_moratorios_estimados_ia": 10.0},
    ])
    resultado, _ = processar_condenacao(dados)  # não deve levantar exceção

    item = resultado["itens_calculo_processados"][0]
    assert item["calculado_automaticamente"] is False
    assert item["valor_atualizado"] == 1020.0
    assert item["juros_moratorios"] == 10.0


def test_agregacao_sem_multa_523_sequencia_correta():
    """2 itens, sem estar em cumprimento de sentença — a sequência do
    documento até o TOTAL GERAL, sem as linhas de multa/honorários 523."""
    dados = _dados_base(honorarios_percentual="10%", itens_calculo=[
        {"descricao": "Capital", "data": "01/01/2026", "valor_singelo": 1000.0, "juros_compensatorios": 0.0,
         "valor_atualizado_estimado_ia": 1000.0, "juros_moratorios_estimados_ia": 0.0},
        {"descricao": "Custas", "data": "01/01/2026", "valor_singelo": 200.0, "juros_compensatorios": 0.0,
         "valor_atualizado_estimado_ia": 200.0, "juros_moratorios_estimados_ia": 0.0},
    ])
    resultado, campos_extra = processar_condenacao(dados)

    # subtotal_1 = 1000 + 200 = 1200
    assert resultado["subtotal_1"] == 1200.0
    # honorarios = 10% de 1200 = 120
    assert resultado["honorarios_valor"] == 120.0
    # subtotal_2 = 1200 + 120 = 1320
    assert resultado["subtotal_2"] == 1320.0
    assert resultado["aplica_multa_523"] is False
    assert resultado["multa_523_valor"] == 0.0
    assert resultado["honorarios_523_valor"] == 0.0
    # total geral = subtotal_2, sem 523
    assert resultado["total_geral"] == 1320.0
    assert campos_extra["condenacao_valor_total_geral"] == 1320.0
    assert campos_extra["condenacao_recomendacao"] == "nao_impugnar"


def test_agregacao_com_multa_523_sequencia_completa():
    """Mesmo caso acima, mas em cumprimento de sentença com prazo do
    art. 523 já vencido — soma multa E honorários de 10% cada sobre o
    subtotal_2."""
    dados = _dados_base(
        honorarios_percentual="10%", em_cumprimento_sentenca=True, prazo_523_transcorrido=True,
        recomendacao_impugnar=True,
        itens_calculo=[
            {"descricao": "Capital", "data": "01/01/2026", "valor_singelo": 1000.0, "juros_compensatorios": 0.0,
             "valor_atualizado_estimado_ia": 1000.0, "juros_moratorios_estimados_ia": 0.0},
        ],
    )
    resultado, campos_extra = processar_condenacao(dados)

    assert resultado["subtotal_1"] == 1000.0
    assert resultado["honorarios_valor"] == 100.0
    assert resultado["subtotal_2"] == 1100.0
    assert resultado["aplica_multa_523"] is True
    assert resultado["multa_523_valor"] == 110.0  # 10% de 1100
    assert resultado["honorarios_523_valor"] == 110.0  # 10% de 1100
    assert resultado["total_geral"] == 1320.0  # 1100 + 110 + 110
    assert campos_extra["condenacao_recomendacao"] == "impugnar"


def test_em_cumprimento_sentenca_sem_prazo_transcorrido_nao_aplica_multa():
    """Em cumprimento de sentença, mas o prazo de pagamento voluntário
    ainda não venceu — as duas condições precisam ser verdadeiras."""
    dados = _dados_base(em_cumprimento_sentenca=True, prazo_523_transcorrido=False, itens_calculo=[
        {"descricao": "Capital", "data": "01/01/2026", "valor_singelo": 1000.0, "juros_compensatorios": 0.0,
         "valor_atualizado_estimado_ia": 1000.0, "juros_moratorios_estimados_ia": 0.0},
    ])
    resultado, _ = processar_condenacao(dados)

    assert resultado["aplica_multa_523"] is False
    assert resultado["total_geral"] == 1000.0
