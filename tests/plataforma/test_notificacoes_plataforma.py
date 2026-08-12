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
    notificacoes_falsas = [
        ("extratus", "Extratus - Relatórios", lambda: [{"mensagem": "a", "tipo": "erro", "link": "/x"}]),
        ("extratus-aburesi", "Extratus - Aburesi", lambda: [{"mensagem": "b", "tipo": "erro", "link": "/y"}]),
    ]

    with patch.object(
        notificacoes,
        "usuario_tem_acesso_fila_motor",
        side_effect=lambda usuario, slug: slug == "extratus",
    ), patch.object(notificacoes, "REGISTRO_NOTIFICACOES", notificacoes_falsas):
        itens = notificacoes.notificacoes_do_usuario(object())

    assert itens == [{"mensagem": "a", "tipo": "erro", "link": "/x", "ferramenta": "Extratus - Relatórios"}]


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
