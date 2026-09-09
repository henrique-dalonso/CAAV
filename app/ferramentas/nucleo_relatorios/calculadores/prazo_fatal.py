"""Calculador determinístico do "prazo fatal" de uma EMENDA/despacho —
implementa a seção "CÁLCULO DO PRAZO FATAL" do prompt de emenda
(nucleo_relatorios/config/prompts/emenda.txt). Puro (sem I/O, sem chamada
de IA) DE PROPÓSITO: a IA (ver `ia_cliente.FERRAMENTA_EMENDA`) só extrai os
FATOS brutos do despacho — data da intimação, quantidade de dias, se são
úteis ou corridos — a aritmética de data em si NUNCA é delegada ao modelo.
Um LLM erra conta de data com frequência, sobretudo perto de feriado ou do
recesso forense; aqui a conta roda em código testável, com os mesmos fatos
que a IA leu.

Interpretação adotada (JUDGMENT CALL, sinalizado no relatório final pro
Henrique/jurídico conferir): o prompt diz, na mesma frase, duas coisas —
"excluir o dia do começo" (art. 224, caput, CPC, vale sempre) e "a
contagem inicia no primeiro dia útil seguinte" (que este módulo trata como
a regra do caso PADRÃO, contagem em dias úteis — é isso que art. 224, §3º
c/c art. 219 do CPC realmente diz: só o prazo contado em dias úteis exige
que o primeiro dia da contagem seja útil). Pra prazo em dias CORRIDOS
(`dias_uteis=False`), o dia seguinte à intimação já é o dia 1, útil ou
não, e só o resultado FINAL é que sofre a prorrogação "cai em dia não
útil, empurra pro próximo dia útil" — regra essa sim aplicada nos dois
casos, por ser uma instrução separada e explícita do prompt.
"""

from datetime import date, datetime, timedelta

from app.ferramentas.nucleo_relatorios.calculadores.feriados_forenses import eh_dia_util


FORMATO_DATA = "%d/%m/%Y"


def _para_date(valor):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, date):
        return valor
    return datetime.strptime(valor.strip(), FORMATO_DATA).date()


def _rolar_para_proximo_dia_util(dia):
    """"Se a data final cair em dia não útil, prorrogar para o primeiro
    dia útil seguinte" — regra final do prompt, aplicada tanto pra
    contagem em dias úteis quanto em dias corridos."""
    while not eh_dia_util(dia):
        dia += timedelta(days=1)
    return dia


def _somar_dias_uteis(data_inicio_util, quantidade):
    """`data_inicio_util` já é garantidamente um dia útil (quem chama
    aplicou `_rolar_para_proximo_dia_util` antes, se preciso) — soma
    `quantidade` dias ÚTEIS a partir dele, INCLUSIVE (ex: prazo de 1 dia
    útil a partir de uma segunda-feira útil = a própria segunda-feira)."""
    dia = data_inicio_util
    contados = 0

    while True:
        if eh_dia_util(dia):
            contados += 1
            if contados == quantidade:
                return dia
        dia += timedelta(days=1)


def calcular_prazo_fatal(data_intimacao, prazo_dias, dias_uteis, data_fatal_informada=None):
    """Calcula o prazo fatal a partir dos fatos extraídos do despacho.

    Parâmetros:
    - `data_intimacao`: string "DD/MM/AAAA" (ou `date`) — data da
      intimação eletrônica CONFIRMADA (leitura ou decurso do prazo de
      consulta), NUNCA a de expedição/disponibilização (a IA já deve ter
      extraído a data certa; este calculador só faz a conta a partir
      dela).
    - `prazo_dias`: inteiro, quantidade de dias do prazo fixado.
    - `dias_uteis`: True conta em dias úteis (pulando fim de semana,
      feriado forense nacional e o recesso 20/12-20/01 — ver
      `calculadores/feriados_forenses.py`); False conta em dias
      corridos.
    - `data_fatal_informada`: opcional, string "DD/MM/AAAA" (ou `date`)
      — uma data "FATAL" que já apareça solta num e-mail interno do
      escritório ou na própria decisão, pra comparar com o valor
      calculado aqui (o prompt pede pra mostrar as duas juntas quando
      divergirem, nunca escolher uma silenciosamente).

    Devolve um dict com:
    - `data_inicio_contagem` (date): primeiro dia contado (dia seguinte
      à intimação, dia zero excluído — art. 224, caput, CPC).
    - `data_final_calculada` (date): resultado da conta, já com a
      prorrogação de dia não útil aplicada se necessário.
    - `ja_vencido` (bool): `data_final_calculada` já passou, comparado a
      HOJE (a data em que o cálculo roda).
    - `data_fatal_informada` (date | None): o valor recebido, já
      convertido — None se não foi informado nada.
    - `diverge_do_informado` (bool | None): None quando
      `data_fatal_informada` não foi passado (nada pra comparar);
      True/False caso contrário.
    """
    data_intimacao = _para_date(data_intimacao)
    if data_intimacao is None:
        raise ValueError("data_intimacao é obrigatória para calcular o prazo fatal.")

    data_fatal_informada = _para_date(data_fatal_informada)

    # art. 224, caput, CPC — exclui o dia do próprio ato de intimação; a
    # contagem começa no dia seguinte.
    data_inicio_contagem = data_intimacao + timedelta(days=1)

    if dias_uteis:
        # Ver docstring do módulo: contagem em dias úteis exige que o
        # PRIMEIRO dia contado também seja útil (art. 224, §3º c/c art.
        # 219, CPC) — se cair em fim de semana/feriado/recesso, avança
        # até o primeiro dia útil antes de começar a contar de fato.
        data_inicio_contagem = _rolar_para_proximo_dia_util(data_inicio_contagem)
        data_final_calculada = _somar_dias_uteis(data_inicio_contagem, prazo_dias)
    else:
        # Dias corridos: o dia 1 é o próprio dia seguinte à intimação,
        # útil ou não — só o resultado final sofre prorrogação.
        data_final_calculada = data_inicio_contagem + timedelta(days=prazo_dias - 1)
        data_final_calculada = _rolar_para_proximo_dia_util(data_final_calculada)

    ja_vencido = data_final_calculada < date.today()

    diverge_do_informado = None
    if data_fatal_informada is not None:
        diverge_do_informado = data_final_calculada != data_fatal_informada

    return {
        "data_inicio_contagem": data_inicio_contagem,
        "data_final_calculada": data_final_calculada,
        "ja_vencido": ja_vencido,
        "data_fatal_informada": data_fatal_informada,
        "diverge_do_informado": diverge_do_informado,
    }
