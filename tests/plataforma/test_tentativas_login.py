from datetime import datetime, timedelta

import pytest
from sqlmodel import delete

from app.plataforma.db.models import TentativaLoginFalha
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.tentativas_login import ip_esta_bloqueado, registrar_tentativa_falha


IP_TESTE = "203.0.113.10"
IP_OUTRO_TESTE = "198.51.100.20"


@pytest.fixture(autouse=True)
def limpar_tentativas():
    def _limpar():
        with obter_sessao() as sessao:
            sessao.exec(
                delete(TentativaLoginFalha).where(
                    TentativaLoginFalha.ip.in_([IP_TESTE, IP_OUTRO_TESTE])
                )
            )
            sessao.commit()

    _limpar()
    yield
    _limpar()


def test_menos_de_5_contas_distintas_nao_bloqueia():
    for nome in ["a", "b", "c", "d"]:
        registrar_tentativa_falha(IP_TESTE, nome)

    assert ip_esta_bloqueado(IP_TESTE) is False


def test_5_contas_distintas_bloqueia():
    for nome in ["a", "b", "c", "d", "e"]:
        registrar_tentativa_falha(IP_TESTE, nome)

    assert ip_esta_bloqueado(IP_TESTE) is True


def test_mesma_conta_repetida_nao_conta_multiplas_vezes():
    for _ in range(10):
        registrar_tentativa_falha(IP_TESTE, "sempre_a_mesma")

    assert ip_esta_bloqueado(IP_TESTE) is False


def test_tentativa_fora_da_janela_de_15_minutos_nao_conta():
    with obter_sessao() as sessao:
        for nome in ["a", "b", "c", "d", "e"]:
            sessao.add(
                TentativaLoginFalha(
                    ip=IP_TESTE,
                    nome_usuario_tentado=nome,
                    criado_em=datetime.now() - timedelta(minutes=20),
                )
            )
        sessao.commit()

    assert ip_esta_bloqueado(IP_TESTE) is False


def test_ip_diferente_nao_soma_junto():
    for nome in ["a", "b", "c", "d", "e"]:
        registrar_tentativa_falha(IP_OUTRO_TESTE, nome)

    assert ip_esta_bloqueado(IP_TESTE) is False
