from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete

from app.plataforma.db.models import Usuario
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web import notificacoes
from app.plataforma.web.main import app


NOME_USUARIO_TESTE = "teste_notificacoes_usuario"


@pytest.fixture
def usuario_sem_acesso():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    usuario = criar_usuario(
        nome="Teste Notificações",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_notificacoes@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        ferramenta_ids=[],
    )

    yield usuario

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


def test_usuario_sem_acesso_a_nenhuma_ferramenta_nao_ve_nada(usuario_sem_acesso):
    assert notificacoes.notificacoes_do_usuario(usuario_sem_acesso) == []


def test_agrega_so_ferramentas_com_acesso_liberado():
    # Henrique, diretoria, 2026-08-19: as 2 famílias (Sistema/erro e
    # Minhas/pessoal) agora usam o MESMO critério — acesso básico à
    # ferramenta, sem flag própria pra Fila do Robô. Um registro com as
    # duas famílias por ferramenta prova que ambas respeitam o acesso.
    # Mensagens já terminadas em ponto de propósito: esse teste é sobre
    # filtro de acesso, não sobre a normalização de pontuação final
    # (ver test_com_ponto_final_* abaixo pra essa regra em isolado).
    item_pessoal_extratus = {
        "mensagem": "c.", "tipo": "pronto", "link": "/z",
        "pessoal": True, "descartavel": True, "resolver": "/r",
    }
    notificacoes_falsas = [
        ("extratus", "Extratus - Relatórios", lambda usuario_id: [{"mensagem": "a.", "tipo": "erro", "link": "/x"}], lambda usuario_id: [item_pessoal_extratus]),
        ("extratus-aburesi", "Extratus - Aburesi", lambda usuario_id: [{"mensagem": "b.", "tipo": "erro", "link": "/y"}], lambda usuario_id: []),
    ]

    with patch.object(
        notificacoes,
        "usuario_tem_acesso",
        side_effect=lambda usuario, slug: slug == "extratus",
    ), patch.object(notificacoes, "REGISTRO_NOTIFICACOES", notificacoes_falsas):
        itens = notificacoes.notificacoes_do_usuario(SimpleNamespace(id=1))

    assert itens == [
        {"mensagem": "a.", "tipo": "erro", "link": "/x", "ferramenta": "Extratus - Relatórios"},
        {**item_pessoal_extratus, "ferramenta": "Extratus - Relatórios"},
    ]


def test_com_ponto_final_adiciona_ponto_quando_falta():
    assert notificacoes._com_ponto_final("relatório pronto") == "relatório pronto."


def test_com_ponto_final_nao_duplica_pontuacao_existente():
    assert notificacoes._com_ponto_final("já tem ponto.") == "já tem ponto."
    assert notificacoes._com_ponto_final("já tem exclamação!") == "já tem exclamação!"
    assert notificacoes._com_ponto_final("já tem interrogação?") == "já tem interrogação?"


def test_com_ponto_final_string_vazia_fica_vazia():
    assert notificacoes._com_ponto_final("") == ""


def test_endpoint_notificacoes_exige_login():
    cliente = TestClient(app)

    resp = cliente.get("/notificacoes", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_endpoint_notificacoes_devolve_json_pra_quem_esta_logado():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Notificações",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_notificacoes@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        ferramenta_ids=[],
    )

    cliente = TestClient(app)
    cliente.post(
        "/login",
        data={"usuario_login": NOME_USUARIO_TESTE, "senha": "senhaTeste123"},
    )

    resp = cliente.get("/notificacoes")

    assert resp.status_code == 200
    assert resp.json() == {"itens": []}

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()
