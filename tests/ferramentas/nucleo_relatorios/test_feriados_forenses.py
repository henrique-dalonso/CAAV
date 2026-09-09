from datetime import date

from app.ferramentas.nucleo_relatorios.calculadores.feriados_forenses import (
    dentro_do_recesso_forense,
    eh_dia_util,
    feriados_nacionais_do_ano,
)


def test_pascoa_deriva_feriados_moveis_corretos_2026():
    # Domingo de Páscoa de 2026 é 05/04/2026 (data pública, conferida
    # contra o calendário real) — os móveis derivam dela.
    feriados = feriados_nacionais_do_ano(2026)
    assert date(2026, 2, 16) in feriados  # Segunda de Carnaval
    assert date(2026, 2, 17) in feriados  # Terça de Carnaval
    assert date(2026, 4, 3) in feriados   # Sexta-feira Santa
    assert date(2026, 6, 4) in feriados   # Corpus Christi


def test_feriados_fixos_presentes():
    feriados = feriados_nacionais_do_ano(2026)
    assert date(2026, 1, 1) in feriados
    assert date(2026, 4, 21) in feriados
    assert date(2026, 5, 1) in feriados
    assert date(2026, 9, 7) in feriados
    assert date(2026, 10, 12) in feriados
    assert date(2026, 11, 2) in feriados
    assert date(2026, 11, 15) in feriados
    assert date(2026, 12, 25) in feriados


def test_recesso_forense_cruza_virada_do_ano():
    assert dentro_do_recesso_forense(date(2026, 12, 20)) is True
    assert dentro_do_recesso_forense(date(2026, 12, 31)) is True
    assert dentro_do_recesso_forense(date(2027, 1, 1)) is True
    assert dentro_do_recesso_forense(date(2027, 1, 20)) is True
    assert dentro_do_recesso_forense(date(2026, 12, 19)) is False
    assert dentro_do_recesso_forense(date(2027, 1, 21)) is False


def test_dia_util_exclui_fim_de_semana_feriado_e_recesso():
    assert eh_dia_util(date(2026, 11, 3)) is True   # terça comum
    assert eh_dia_util(date(2026, 11, 7)) is False  # sábado
    assert eh_dia_util(date(2026, 11, 8)) is False  # domingo
    assert eh_dia_util(date(2026, 11, 2)) is False  # Finados (feriado fixo)
    assert eh_dia_util(date(2026, 12, 25)) is False  # Natal (e recesso)
    assert eh_dia_util(date(2027, 1, 10)) is False  # dentro do recesso, dia de semana
