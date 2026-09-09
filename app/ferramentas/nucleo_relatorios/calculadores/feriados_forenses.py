"""Feriados forenses NACIONAIS + recesso forense (20/12 a 20/01) — usado só
pelo calculador de prazo fatal (calculadores/prazo_fatal.py) pra saber quais
dias NÃO contam como dia útil na análise de EMENDA/despacho
(nucleo_relatorios/config/prompts/emenda.txt, seção "CÁLCULO DO PRAZO
FATAL").

IMPORTANTE, aceito conscientemente com Henrique (não é um bug a corrigir
agora, é lacuna DOCUMENTADA): isto cobre só o calendário NACIONAL. Feriado/
ponto facultativo de COMARCA (municipal, estadual, aniversário da cidade,
etc.) não entra aqui — cobrir isso exigiria manter uma tabela por comarca,
que muda de tribunal pra tribunal e não tem fonte única confiável pra
automatizar hoje. O prompt de EMENDA já orienta o colaborador a conferir
prazo/feriado local manualmente, e o relatório final (template
config/templates/emenda.docx) inclui uma nota fixa avisando dessa lacuna —
ver campo `nota_feriados_locais` no schema (ia_cliente.FERRAMENTA_EMENDA)
e no template.
"""

from datetime import date, timedelta


def _domingo_de_pascoa(ano):
    """Data do Domingo de Páscoa num ano gregoriano qualquer, pelo
    algoritmo "anônimo gregoriano" (Meeus/Jones/Butcher) — usado pra
    derivar os feriados forenses MÓVEIS (Carnaval, Sexta-feira Santa,
    Corpus Christi), que não têm data fixa no calendário. Não depende de
    nenhuma biblioteca externa de calendário litúrgico — só aritmética
    inteira, testável e sem surpresa de fuso/locale."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def _feriados_moveis(ano):
    pascoa = _domingo_de_pascoa(ano)
    return {
        pascoa - timedelta(days=48),  # Segunda-feira de Carnaval
        pascoa - timedelta(days=47),  # Terça-feira de Carnaval
        pascoa - timedelta(days=2),   # Sexta-feira Santa
        pascoa + timedelta(days=60),  # Corpus Christi
    }


# (mês, dia) — feriados forenses nacionais de data FIXA, sempre no mesmo
# dia todo ano.
_FERIADOS_FIXOS_MES_DIA = [
    (1, 1),    # Confraternização Universal
    (4, 21),   # Tiradentes
    (5, 1),    # Dia do Trabalho
    (9, 7),    # Independência do Brasil
    (10, 12),  # Nossa Senhora Aparecida
    (11, 2),   # Finados
    (11, 15),  # Proclamação da República
    (12, 25),  # Natal
]


def feriados_nacionais_do_ano(ano):
    """Todos os feriados forenses nacionais (fixos + móveis) de UM ano
    específico, como um `set` de `date`. Devolvido ano a ano (não um
    calendário perpétuo pré-computado) porque os móveis dependem da
    Páscoa daquele ano — `eh_dia_util` junta o conjunto de 2 anos quando
    a data cai em dezembro/janeiro, pra um feriado móvel de janeiro do
    ano seguinte (nenhum dos 4 hoje cai em janeiro, mas a função fica
    correta mesmo se isso mudasse) não ficar de fora por engano."""
    fixos = {date(ano, mes, dia) for mes, dia in _FERIADOS_FIXOS_MES_DIA}
    return fixos | _feriados_moveis(ano)


def dentro_do_recesso_forense(dia):
    """Recesso forense nacional: 20/12 a 20/01 (inclusive), atravessando a
    virada do ano (Lei 11.416/2006, art. 62, I — replicada pela grande
    maioria dos tribunais como suspensão de prazo). `dia` está dentro do
    recesso se for >= 20/12 do seu próprio ano OU <= 20/01 do seu próprio
    ano — as duas metades do mesmo período contínuo, uma de cada lado do
    31/12."""
    inicio_dezembro = date(dia.year, 12, 20)
    fim_janeiro = date(dia.year, 1, 20)
    return dia >= inicio_dezembro or dia <= fim_janeiro


def eh_dia_util(dia):
    """Um dia conta como ÚTIL só se NÃO for: fim de semana, feriado
    forense nacional, ou parte do recesso forense. `dia.month` em 12 ou 1
    também confere feriados do ano ADJACENTE (dezembro olha o ano
    seguinte, janeiro olha o ano anterior) — necessário porque um feriado
    "pertence" ao ano da própria data (ex: Confraternização Universal de
    01/01/2027 é um feriado de 2027, não de 2026), mas a função é chamada
    dia a dia sem saber de antemão em qual perna da virada está."""
    if dia.weekday() >= 5:  # 5 = sábado, 6 = domingo
        return False

    if dentro_do_recesso_forense(dia):
        return False

    feriados = feriados_nacionais_do_ano(dia.year)

    if dia.month == 1:
        feriados = feriados | feriados_nacionais_do_ano(dia.year - 1)
    elif dia.month == 12:
        feriados = feriados | feriados_nacionais_do_ano(dia.year + 1)

    return dia not in feriados
