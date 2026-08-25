import json
import time
import urllib.request

from app.plataforma.logger import registrar_log


# Henrique, diretoria, 2026-08-25: valores de custo (sempre em US$, é
# como a Anthropic cobra) agora também aparecem em R$ nas telas de
# Custos, com cotação "de verdade", não um número fixo digitado à mão
# (como o USD/BRL ≈ 5.12 usado antes, ver [[extratus-reducao-custo-motor]]).
# AwesomeAPI (economia.awesomeapi.com.br) — brasileira, gratuita, sem
# chave/cadastro, cotação de mercado quase em tempo real. Testada em
# 2026-08-25: PTAX (Banco Central, a fonte "oficial") só atualiza 1x por
# dia útil — não serve pro "tempo real" pedido.
URL_COTACAO = "https://economia.awesomeapi.com.br/last/USD-BRL"

INTERVALO_CACHE_SEGUNDOS = 60 * 60  # 1h, decisão de Henrique

# Só usado se a API NUNCA respondeu com sucesso desde que o processo
# subiu (ex: servidor sem internet no primeiro request) — aproximado,
# não é "tempo real" nesse caso específico. Mesma ordem de grandeza do
# valor checado ao vivo em jul/2026 (ver memória de redução de custo).
COTACAO_PADRAO_USD_BRL = 5.10

# Cache em memória do próprio processo — 1 valor válido por até 1h,
# reaproveitado por qualquer tela que peça a cotação nesse intervalo,
# em vez de bater na API a cada carregamento de página.
_cache = {"valor": None, "buscado_em": 0.0}


def obter_cotacao_usd_brl():
    """Cotação USD->BRL atual (1 dólar = quantos reais), com cache de 1h.

    Nunca levanta exceção — se a API estiver fora do ar, devolve o
    último valor bom conhecido (mesmo vencido) ou, na falta de
    qualquer valor já obtido, COTACAO_PADRAO_USD_BRL. Uma tela de
    custos não pode quebrar por causa de uma API de câmbio fora do ar.
    """
    agora = time.time()

    if _cache["valor"] is not None and (agora - _cache["buscado_em"]) < INTERVALO_CACHE_SEGUNDOS:
        return _cache["valor"]

    try:
        with urllib.request.urlopen(URL_COTACAO, timeout=5) as resposta:
            dados = json.loads(resposta.read())
            valor = float(dados["USDBRL"]["bid"])
    except Exception as erro:
        registrar_log(f"Cambio: falha ao buscar cotacao USD/BRL na AwesomeAPI ({erro}).")
        return _cache["valor"] if _cache["valor"] is not None else COTACAO_PADRAO_USD_BRL

    _cache["valor"] = valor
    _cache["buscado_em"] = agora
    return valor


def usd_para_brl(valor_usd, cotacao):
    if valor_usd is None:
        return None
    return valor_usd * cotacao
