import asyncio

import pytest

from app.plataforma.web import eventos_sse


@pytest.fixture(autouse=True)
def limpar_conexoes():
    # eventos_sse._conexoes é um estado global em memória — cada teste
    # começa e termina com a lista zerada, senão um teste vaza conexão
    # "fantasma" pro próximo.
    eventos_sse._conexoes.clear()
    yield
    eventos_sse._conexoes.clear()


def test_avisar_mudanca_acorda_conexoes_registradas():
    fila = eventos_sse.registrar_conexao()

    eventos_sse.avisar_mudanca()

    assert fila.qsize() == 1


def test_remover_conexao_para_de_receber_avisos():
    fila = eventos_sse.registrar_conexao()
    eventos_sse.remover_conexao(fila)

    eventos_sse.avisar_mudanca()

    assert fila.qsize() == 0


def test_avisar_mudanca_acorda_todas_as_conexoes_abertas():
    fila1 = eventos_sse.registrar_conexao()
    fila2 = eventos_sse.registrar_conexao()

    eventos_sse.avisar_mudanca()

    assert fila1.qsize() == 1
    assert fila2.qsize() == 1


def test_avisar_mudanca_sem_conexao_nenhuma_nao_da_erro():
    eventos_sse.avisar_mudanca()  # não deveria levantar exceção


def test_avisar_mudanca_nao_estoura_quando_fila_cheia():
    fila = eventos_sse.registrar_conexao()

    for _ in range(20):
        eventos_sse.avisar_mudanca()

    # maxsize=10 — o excesso é descartado silenciosamente (QueueFull),
    # nunca deveria propagar uma exceção pra quem chamou.
    assert fila.qsize() <= 10


def test_registrar_conexao_devolve_fila_assincrona_de_verdade():
    fila = eventos_sse.registrar_conexao()

    assert isinstance(fila, asyncio.Queue)
