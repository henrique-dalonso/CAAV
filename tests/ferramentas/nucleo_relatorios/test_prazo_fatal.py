"""Casos exigidos pra validar o calculador antes de qualquer coisa
depender dele (ver [[extratus-motor-unificado]] / tarefa EMENDA): rollover
de fim de semana, período de recesso, prazo já vencido, dias corridos vs.
dias úteis, e divergência entre data informada e calculada.

Todas as datas de "hoje ainda não vencido" foram escolhidas em novembro de
2026, no futuro em relação à data em que esta tarefa foi escrita
(09/09/2026) — os valores esperados foram conferidos rodando o próprio
calculador e checados à mão (dia da semana) antes de virar asserção fixa
aqui, não copiados cegamente da primeira saída."""

from datetime import date

from app.ferramentas.nucleo_relatorios.calculadores.prazo_fatal import calcular_prazo_fatal


def test_rollover_de_fim_de_semana_dias_corridos():
    """Intimação terça 03/11/2026, prazo de 4 dias CORRIDOS: dia 1 =
    04/11 (quarta), final bruto = 07/11/2026 (sábado) — precisa prorrogar
    pro próximo dia útil. 08/11 é domingo, então o resultado é
    09/11/2026 (segunda)."""
    resultado = calcular_prazo_fatal("03/11/2026", 4, dias_uteis=False)

    assert resultado["data_inicio_contagem"] == date(2026, 11, 4)
    assert resultado["data_final_calculada"] == date(2026, 11, 9)
    assert resultado["ja_vencido"] is False


def test_prazo_atravessando_o_recesso_forense_pula_o_periodo_inteiro():
    """Intimação quinta 17/12/2026, prazo de 3 dias ÚTEIS: dia 1 = sexta
    18/12/2026 (ainda antes do recesso). O 2º dia útil só aparece depois
    de todo o recesso (20/12/2026 a 20/01/2027) terminar — cai em
    21/01/2027 (quinta). O 3º dia útil é 22/01/2027 (sexta), sem nenhum
    feriado nesse meio. O intervalo real de mais de 1 mês (19/12 a
    21/01) inteiro não conta como avanço de prazo nenhum."""
    resultado = calcular_prazo_fatal("17/12/2026", 3, dias_uteis=True)

    assert resultado["data_inicio_contagem"] == date(2026, 12, 18)
    assert resultado["data_final_calculada"] == date(2027, 1, 22)
    assert resultado["ja_vencido"] is False


def test_prazo_ja_vencido_fica_marcado():
    """Intimação de 2010 — não importa a regra de contagem, o resultado
    está muitíssimo no passado em relação a hoje."""
    resultado = calcular_prazo_fatal("01/03/2010", 5, dias_uteis=False)

    assert resultado["data_final_calculada"] == date(2010, 3, 8)
    assert resultado["ja_vencido"] is True


def test_dias_corridos_conta_fim_de_semana_dias_uteis_nao():
    """Mesma intimação (terça 03/11/2026), mesmo dia de início da
    contagem (04/11/2026, quarta) — só muda a regra de contagem. Em
    dias CORRIDOS, sábado e domingo contam como dia do prazo normalmente
    (final cai numa terça comum, sem prorrogação). Em dias ÚTEIS, os
    mesmos 2 dias de fim de semana são pulados, então um prazo bem menor
    (3, não 7) já basta pra terminar antes — evidenciando que as duas
    contagens divergem de propósito quando um fim de semana está no
    meio."""
    corridos = calcular_prazo_fatal("03/11/2026", 7, dias_uteis=False)
    uteis = calcular_prazo_fatal("03/11/2026", 3, dias_uteis=True)

    assert corridos["data_inicio_contagem"] == date(2026, 11, 4)
    assert corridos["data_final_calculada"] == date(2026, 11, 10)  # terça, sem pular fds

    assert uteis["data_inicio_contagem"] == date(2026, 11, 4)
    assert uteis["data_final_calculada"] == date(2026, 11, 6)  # sexta, mesma semana


def test_divergencia_entre_data_informada_e_calculada_e_sinalizada():
    """O prompt pede que uma data "FATAL" já solta num e-mail interno
    seja comparada com o valor calculado aqui, nunca escolhida
    silenciosamente — ver docstring de `calcular_prazo_fatal`."""
    diverge = calcular_prazo_fatal("03/11/2026", 4, dias_uteis=False, data_fatal_informada="10/11/2026")
    bate = calcular_prazo_fatal("03/11/2026", 4, dias_uteis=False, data_fatal_informada="09/11/2026")

    assert diverge["data_final_calculada"] == date(2026, 11, 9)
    assert diverge["data_fatal_informada"] == date(2026, 11, 10)
    assert diverge["diverge_do_informado"] is True

    assert bate["data_fatal_informada"] == date(2026, 11, 9)
    assert bate["diverge_do_informado"] is False


def test_sem_data_informada_diverge_fica_none():
    resultado = calcular_prazo_fatal("03/11/2026", 4, dias_uteis=False)
    assert resultado["data_fatal_informada"] is None
    assert resultado["diverge_do_informado"] is None


def test_aceita_objeto_date_alem_de_string():
    resultado = calcular_prazo_fatal(date(2026, 11, 3), 4, dias_uteis=False)
    assert resultado["data_inicio_contagem"] == date(2026, 11, 4)
