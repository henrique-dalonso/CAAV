"""Calculador determinístico de correção monetária + juros de mora pra
Condenação, usando índices OFICIAIS buscados ao vivo na API pública e
gratuita do Banco Central (SGS — Sistema Gerenciador de Séries Temporais),
em vez de confiar na IA pra "lembrar" o valor de um índice ou fazer a
conta de composição mensal de cabeça. Mesmo raciocínio de
`calculadores/prazo_fatal.py`: um LLM não tem acesso confiável e sempre
atualizado a série histórica de índice nenhum, e conta de juros compostos
"de memória" é exatamente o tipo de erro que passa despercebido — aqui a
IA só extrai QUAL índice a decisão manda usar e as datas/valores base; a
conta em si roda em código testável, contra dado real buscado na hora.

Só cobre os índices NACIONAIS (SELIC, IPCA, INPC, IGP-M, IPCA-E), que têm
série pública e gratuita no Banco Central — confirmado por consulta real
à API antes de escrever este módulo (não presumido). Quando a decisão
exige "tabela do tribunal local" (cada estado publica a própria, sem
fonte pública automatizável conhecida), este módulo não se aplica —
`pos_processamento_condenacao.py` cai de volta pra estimativa da IA nesse
caso, sinalizando isso claramente no relatório final.

Códigos de série confirmados por chamada real à API (não é suposição):
SELIC acumulada no mês = 4390, IPCA = 433, INPC = 188, IGP-M = 189,
IPCA-E = 10764.

**Regra especial da SELIC** (Lei 14.905/2024, art. 406 do Código Civil):
quando a SELIC é a taxa aplicável, ela SUBSTITUI correção monetária E
juros de mora por uma taxa única combinada — não se soma juros por cima
da atualização pela SELIC, diferente dos outros índices (que só corrigem
o valor; juros de mora vêm por fora, calculados à parte). Ver
`atualizar_por_indice` — `indice="SELIC"` sempre devolve
`juros_moratorios=0` de propósito, com o valor já embutido em
`valor_atualizado`.

**Meses ainda não publicados**: a API do BCB simplesmente OMITE meses sem
dado ainda divulgado (confirmado testando contra a API real) — não
retorna erro nem zero. Este módulo trata isso como "correção calculada
até o último mês disponível", nunca inventa um valor pro mês faltante, e
sinaliza `meses_sem_indice_publicado` no resultado pra aparecer no
relatório."""

from datetime import date, datetime

import httpx


FORMATO_DATA_BCB = "%d/%m/%Y"

# Confirmados por chamada real à API do BCB antes de codar (ver docstring
# do módulo) — nunca usar um código aqui sem testar contra
# https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados primeiro.
CODIGOS_SGS = {
    "SELIC": 4390,
    "IPCA": 433,
    "INPC": 188,
    "IGP-M": 189,
    "IPCA-E": 10764,
}

INDICES_NACIONAIS_RECONHECIDOS = frozenset(CODIGOS_SGS.keys())

TIMEOUT_SEGUNDOS = 10


def _para_date(valor):
    if isinstance(valor, date):
        return valor
    return datetime.strptime(valor.strip(), FORMATO_DATA_BCB).date()


def buscar_serie_mensal(codigo_sgs, data_inicio, data_fim):
    """Busca a série de variação mensal (%) na API do BCB entre duas datas
    (inclusive). Devolve lista de `(date, float)` ordenada por data
    crescente — cada item é o mês inteiro (a API do BCB sempre devolve o
    dia 1 de cada mês como marcador, não um dia específico).

    Função isolada de propósito (só faz a chamada HTTP, nenhuma conta) —
    testes de aritmética mockam esta função, nunca batem na API de
    verdade; só o teste dedicado do cliente HTTP (com resposta mockada)
    verifica o parsing.
    """
    data_inicio = _para_date(data_inicio)
    data_fim = _para_date(data_fim)

    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_sgs}/dados"
    parametros = {
        "formato": "json",
        "dataInicial": data_inicio.strftime(FORMATO_DATA_BCB),
        "dataFinal": data_fim.strftime(FORMATO_DATA_BCB),
    }

    resposta = httpx.get(url, params=parametros, timeout=TIMEOUT_SEGUNDOS)
    resposta.raise_for_status()

    itens = [
        (datetime.strptime(item["data"], FORMATO_DATA_BCB).date(), float(item["valor"]))
        for item in resposta.json()
    ]
    itens.sort(key=lambda item: item[0])
    return itens


def _fator_acumulado(taxas_mensais_percentuais):
    """Composição de juros/correção compostos mês a mês: fator = produto
    de (1 + taxa/100) de cada mês — NUNCA soma simples das taxas (erro
    comum, e significativo em períodos longos). Lista vazia = fator 1.0
    (nenhuma correção — usado quando o período cai todo dentro de um mês
    ainda não publicado)."""
    fator = 1.0
    for taxa_percentual in taxas_mensais_percentuais:
        fator *= 1 + (taxa_percentual / 100)
    return fator


def _meses_no_intervalo(data_inicio, data_fim):
    """Quantos marcadores de mês (dia 1) existem entre duas datas,
    inclusive — usado só pra saber quantos meses ESPERÁVAMOS receber da
    API, pra detectar quantos ficaram sem índice publicado ainda."""
    meses = []
    cursor = date(data_inicio.year, data_inicio.month, 1)
    fim = date(data_fim.year, data_fim.month, 1)
    while cursor <= fim:
        meses.append(cursor)
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return meses


def atualizar_por_indice(indice, data_base, valor_singelo, data_referencia=None, buscar_serie=buscar_serie_mensal):
    """Calcula o valor atualizado (correção monetária) de `valor_singelo`
    entre `data_base` (termo inicial daquela rubrica) e `data_referencia`
    (hoje, se não informado), usando o índice oficial buscado ao vivo no
    BCB.

    `indice` precisa ser uma chave de `CODIGOS_SGS` (ver
    `INDICES_NACIONAIS_RECONHECIDOS`) — quem chama já deve ter conferido
    isso antes (é `pos_processamento_condenacao.py` quem decide se cai
    aqui ou na estimativa da IA, baseado em `FERRAMENTA_CONDENACAO.
    indice_correcao`).

    `buscar_serie` é injetável só pra teste (mockar sem bater na API).

    Devolve um dict:
    - `valor_atualizado` (float): valor corrigido (e, se `indice ==
      "SELIC"`, já com os juros embutidos — ver docstring do módulo).
    - `juros_moratorios` (float): sempre `0.0` quando `indice == "SELIC"`
      (embutido acima); calculado à parte por quem chama pros outros
      índices (este módulo só faz correção monetária pura, juros de mora
      não têm índice, são uma taxa fixa informada separadamente).
    - `fator_acumulado` (float): o fator de composição aplicado, pra
      auditoria/conferência manual.
    - `meses_sem_indice_publicado` (list[date]): meses dentro do período
      que a API ainda não tinha valor publicado — vazio no caso comum.
    """
    if indice not in CODIGOS_SGS:
        raise ValueError(
            f"Índice {indice!r} não é um dos índices nacionais automatizáveis "
            f"({sorted(CODIGOS_SGS)}) — não chame esta função pra 'tabela do "
            "tribunal local' ou outro índice não reconhecido."
        )

    data_base = _para_date(data_base)
    data_referencia = _para_date(data_referencia) if data_referencia else date.today()

    serie = buscar_serie(CODIGOS_SGS[indice], data_base, data_referencia)
    meses_recebidos = {mes for mes, _valor in serie}
    meses_esperados = _meses_no_intervalo(data_base, data_referencia)
    meses_sem_indice_publicado = [mes for mes in meses_esperados if mes not in meses_recebidos]

    fator = _fator_acumulado(valor for _mes, valor in serie)
    valor_atualizado = valor_singelo * fator

    return {
        "valor_atualizado": valor_atualizado,
        "juros_moratorios": 0.0 if indice == "SELIC" else None,
        "fator_acumulado": fator,
        "meses_sem_indice_publicado": meses_sem_indice_publicado,
    }


def calcular_juros_moratorios_simples(valor_base, taxa_mensal_percentual, data_inicio, data_fim=None):
    """Juros de mora — convenção jurídica padrão: SIMPLES (não compostos),
    proporcionais ao tempo decorrido em MESES (fração de mês contada como
    dias/30, prática comum em cálculo judicial de juros simples). Só se
    aplica aos índices que não embutem juros (SELIC não usa esta função —
    ver `atualizar_por_indice`)."""
    data_inicio = _para_date(data_inicio)
    data_fim = _para_date(data_fim) if data_fim else date.today()

    dias = (data_fim - data_inicio).days
    if dias <= 0:
        return 0.0

    meses = dias / 30
    return valor_base * (taxa_mensal_percentual / 100) * meses
