"""Testes da calculadora de correção monetária (ver docstring do módulo
pra racional completo). Regra de ouro: NENHUM teste aqui bate na API real
do BCB — `buscar_serie_mensal` é sempre mockada, exceto no teste dedicado
de parsing HTTP (que mocka `httpx.get`, não a rede de verdade).

O teste `test_atualizar_por_indice_ipca_composicao_real_verificada_a_mao`
usa valores REAIS de IPCA (jan-jul/2026), obtidos consultando a API do
BCB de verdade antes de escrever este módulo, com o fator acumulado
recalculado à mão (produto de (1+taxa/100) mês a mês) antes de virar
asserção fixa aqui — mesmo cuidado já usado em test_prazo_fatal.py, nunca
copiar cegamente a primeira saída do próprio código como "esperado"."""

from datetime import date

import pytest

from app.ferramentas.nucleo_relatorios.calculadores.correcao_monetaria import (
    CODIGOS_SGS,
    INDICES_NACIONAIS_RECONHECIDOS,
    atualizar_por_indice,
    buscar_serie_mensal,
    calcular_juros_moratorios_simples,
)


def test_todos_os_indices_reconhecidos_tem_codigo_sgs():
    assert INDICES_NACIONAIS_RECONHECIDOS == frozenset(CODIGOS_SGS)
    assert {"SELIC", "IPCA", "INPC", "IGP-M", "IPCA-E"} == INDICES_NACIONAIS_RECONHECIDOS


def test_atualizar_por_indice_ipca_composicao_real_verificada_a_mao():
    """IPCA real jan-jul/2026 (consultado na API do BCB antes de escrever
    este módulo): 0.33, 0.70, 0.88, 0.67, 0.58, 0.16, 0.07 (%). Fator
    acumulado recalculado à mão: produto de (1+taxa/100) = 1.034368...
    (≈3,4368% acumulado no período) — conferido multiplicando cada termo
    manualmente antes de virar asserção aqui."""
    serie_real_ipca = [
        (date(2026, 1, 1), 0.33),
        (date(2026, 2, 1), 0.70),
        (date(2026, 3, 1), 0.88),
        (date(2026, 4, 1), 0.67),
        (date(2026, 5, 1), 0.58),
        (date(2026, 6, 1), 0.16),
        (date(2026, 7, 1), 0.07),
    ]

    def buscar_serie_mockada(codigo_sgs, data_inicio, data_fim):
        assert codigo_sgs == CODIGOS_SGS["IPCA"]
        return serie_real_ipca

    resultado = atualizar_por_indice(
        "IPCA",
        data_base="01/01/2026",
        valor_singelo=10_000.0,
        data_referencia="31/07/2026",
        buscar_serie=buscar_serie_mockada,
    )

    assert resultado["fator_acumulado"] == pytest.approx(1.034368, abs=1e-6)
    assert resultado["valor_atualizado"] == pytest.approx(10_343.68, abs=0.01)
    assert resultado["juros_moratorios"] is None  # não é SELIC, juros calculados à parte por quem chama
    assert resultado["meses_sem_indice_publicado"] == []


def test_atualizar_por_indice_selic_zera_juros_pois_ja_embutido():
    """SELIC (Lei 14.905/2024, art. 406 CC) substitui juros E correção
    por uma taxa única — juros_moratorios sempre 0.0 aqui, nunca soma por
    cima em outro lugar."""
    def buscar_serie_mockada(codigo_sgs, data_inicio, data_fim):
        assert codigo_sgs == CODIGOS_SGS["SELIC"]
        return [(date(2026, 1, 1), 1.09), (date(2026, 2, 1), 0.98)]

    resultado = atualizar_por_indice(
        "SELIC",
        data_base="01/01/2026",
        valor_singelo=5_000.0,
        data_referencia="28/02/2026",
        buscar_serie=buscar_serie_mockada,
    )

    assert resultado["juros_moratorios"] == 0.0
    assert resultado["valor_atualizado"] > 5_000.0


def test_atualizar_por_indice_indice_nao_reconhecido_leva_erro():
    with pytest.raises(ValueError):
        atualizar_por_indice(
            "TABELA_TJPR", data_base="01/01/2026", valor_singelo=100.0,
            buscar_serie=lambda *a: [],
        )


def test_meses_sem_indice_publicado_detectado():
    """Pede jan-mar/2026 mas a API (mockada) só devolve jan e fev —
    simula o atraso normal de divulgação do BCB (confirmado por consulta
    real: meses recentes simplesmente não vêm na resposta, sem erro)."""
    def buscar_serie_incompleta(codigo_sgs, data_inicio, data_fim):
        return [(date(2026, 1, 1), 0.5), (date(2026, 2, 1), 0.4)]

    resultado = atualizar_por_indice(
        "IPCA", data_base="01/01/2026", valor_singelo=1_000.0,
        data_referencia="31/03/2026", buscar_serie=buscar_serie_incompleta,
    )

    assert resultado["meses_sem_indice_publicado"] == [date(2026, 3, 1)]


def test_fator_acumulado_composicao_nao_e_soma_simples():
    """Preserva a regra mais fácil de errar: composição é MULTIPLICAÇÃO
    de fatores, não soma das taxas. 2 meses de 10% cada não dá 20%, dá
    21% (1.1 * 1.1 = 1.21)."""
    def buscar_serie_10_por_cento_2_meses(codigo_sgs, data_inicio, data_fim):
        return [(date(2026, 1, 1), 10.0), (date(2026, 2, 1), 10.0)]

    resultado = atualizar_por_indice(
        "IPCA", data_base="01/01/2026", valor_singelo=100.0,
        data_referencia="28/02/2026", buscar_serie=buscar_serie_10_por_cento_2_meses,
    )

    assert resultado["fator_acumulado"] == pytest.approx(1.21)
    assert resultado["valor_atualizado"] == pytest.approx(121.0)


def test_juros_moratorios_simples_proporcional_ao_tempo():
    # 1% a.m., 60 dias (2 meses) sobre R$ 1.000 = 20.00
    juros = calcular_juros_moratorios_simples(1_000.0, 1.0, date(2026, 1, 1), date(2026, 3, 2))
    assert juros == pytest.approx(20.0, abs=0.5)


def test_juros_moratorios_simples_zero_quando_datas_iguais_ou_invertidas():
    assert calcular_juros_moratorios_simples(1_000.0, 1.0, date(2026, 5, 1), date(2026, 5, 1)) == 0.0
    assert calcular_juros_moratorios_simples(1_000.0, 1.0, date(2026, 5, 10), date(2026, 5, 1)) == 0.0


def test_buscar_serie_mensal_faz_parsing_correto_da_resposta_bcb(monkeypatch):
    """Único teste que toca o cliente HTTP — mocka `httpx.get`, nunca a
    rede de verdade, só pra provar que o parsing da resposta real do BCB
    (formato confirmado por chamada manual: [{"data": "DD/MM/AAAA",
    "valor": "0.33"}, ...]) está certo."""
    import app.ferramentas.nucleo_relatorios.calculadores.correcao_monetaria as modulo

    class RespostaFalsa:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                {"data": "01/02/2026", "valor": "0.70"},
                {"data": "01/01/2026", "valor": "0.33"},  # fora de ordem de propósito
            ]

    def get_falso(url, params, timeout):
        assert "433" in url  # IPCA
        return RespostaFalsa()

    monkeypatch.setattr(modulo.httpx, "get", get_falso)

    serie = buscar_serie_mensal(433, "01/01/2026", "28/02/2026")

    assert serie == [(date(2026, 1, 1), 0.33), (date(2026, 2, 1), 0.70)]
