import json
from io import BytesIO
from unittest.mock import patch

import pytest

from app.plataforma import cambio


@pytest.fixture(autouse=True)
def limpar_cache_cambio():
    cambio._cache["valor"] = None
    cambio._cache["buscado_em"] = 0.0
    yield
    cambio._cache["valor"] = None
    cambio._cache["buscado_em"] = 0.0


def _resposta_falsa(bid):
    corpo = json.dumps({"USDBRL": {"bid": str(bid)}}).encode("utf-8")

    class _RespostaFalsa:
        def __enter__(self):
            return BytesIO(corpo)

        def __exit__(self, *args):
            return False

    return _RespostaFalsa()


def test_obter_cotacao_busca_na_api_na_primeira_vez():
    with patch("app.plataforma.cambio.urllib.request.urlopen", return_value=_resposta_falsa(5.20)) as mock_urlopen:
        cotacao = cambio.obter_cotacao_usd_brl()

    assert cotacao == 5.20
    mock_urlopen.assert_called_once()


def test_obter_cotacao_reaproveita_cache_dentro_do_intervalo():
    with patch("app.plataforma.cambio.urllib.request.urlopen", return_value=_resposta_falsa(5.20)) as mock_urlopen:
        cambio.obter_cotacao_usd_brl()
        cotacao_2 = cambio.obter_cotacao_usd_brl()

    assert cotacao_2 == 5.20
    mock_urlopen.assert_called_once()


def test_obter_cotacao_busca_de_novo_apos_o_cache_vencer():
    with patch("app.plataforma.cambio.urllib.request.urlopen", return_value=_resposta_falsa(5.20)):
        cambio.obter_cotacao_usd_brl()

    cambio._cache["buscado_em"] -= cambio.INTERVALO_CACHE_SEGUNDOS + 1

    with patch("app.plataforma.cambio.urllib.request.urlopen", return_value=_resposta_falsa(5.35)) as mock_urlopen:
        cotacao = cambio.obter_cotacao_usd_brl()

    assert cotacao == 5.35
    mock_urlopen.assert_called_once()


def test_obter_cotacao_com_api_fora_do_ar_usa_cache_vencido():
    with patch("app.plataforma.cambio.urllib.request.urlopen", return_value=_resposta_falsa(5.20)):
        cambio.obter_cotacao_usd_brl()

    cambio._cache["buscado_em"] -= cambio.INTERVALO_CACHE_SEGUNDOS + 1

    with patch("app.plataforma.cambio.urllib.request.urlopen", side_effect=OSError("sem rede")):
        cotacao = cambio.obter_cotacao_usd_brl()

    # Câmbio de verdade não pode quebrar a tela de custos — usa o último
    # valor bom conhecido, mesmo vencido, em vez de propagar o erro.
    assert cotacao == 5.20


def test_obter_cotacao_sem_cache_nenhum_e_api_fora_do_ar_usa_padrao():
    with patch("app.plataforma.cambio.urllib.request.urlopen", side_effect=OSError("sem rede")):
        cotacao = cambio.obter_cotacao_usd_brl()

    assert cotacao == cambio.COTACAO_PADRAO_USD_BRL


def test_usd_para_brl_multiplica_pela_cotacao():
    assert cambio.usd_para_brl(2.0, 5.0) == 10.0


def test_usd_para_brl_none_devolve_none():
    assert cambio.usd_para_brl(None, 5.0) is None
