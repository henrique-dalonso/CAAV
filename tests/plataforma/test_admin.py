import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete

from app.plataforma.auth import verificar_senha
from app.plataforma.db.models import Usuario
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import buscar_usuario_por_nome_usuario, criar_usuario
from app.plataforma.web.main import app


NOME_ADMIN_TESTE = "teste_admin_varredura"
NOME_ALVO_TESTE = "teste_admin_alvo"


@pytest.fixture
def cliente_admin_logado():
    with obter_sessao() as sessao:
        sessao.exec(
            delete(Usuario).where(
                Usuario.nome_usuario.in_([NOME_ADMIN_TESTE, NOME_ALVO_TESTE])
            )
        )
        sessao.commit()

    criar_usuario(
        nome="Teste Admin Varredura",
        nome_usuario=NOME_ADMIN_TESTE,
        email="teste_admin_varredura@example.com",
        senha="senhaAdmin12345",
        eh_admin=True,
    )
    criar_usuario(
        nome="Teste Admin Alvo",
        nome_usuario=NOME_ALVO_TESTE,
        email="teste_admin_alvo@example.com",
        senha="senhaOriginal123",
        eh_admin=False,
    )

    cliente = TestClient(app)
    cliente.post(
        "/login",
        data={"usuario_login": NOME_ADMIN_TESTE, "senha": "senhaAdmin12345"},
    )

    yield cliente

    with obter_sessao() as sessao:
        sessao.exec(
            delete(Usuario).where(
                Usuario.nome_usuario.in_([NOME_ADMIN_TESTE, NOME_ALVO_TESTE])
            )
        )
        sessao.commit()


def test_pagina_admin_carrega_para_administrador(cliente_admin_logado):
    resp = cliente_admin_logado.get("/admin")

    assert resp.status_code == 200
    assert "Visão geral" in resp.text
    assert "Novo usuário" in resp.text


def test_redefinir_senha_de_outro_usuario_atualiza_hash(cliente_admin_logado):
    alvo = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)

    resp = cliente_admin_logado.post(
        f"/admin/usuarios/{alvo.id}/redefinir-senha",
        data={"nova_senha": "senhaRedefinida123"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]

    alvo_atualizado = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)
    assert verificar_senha("senhaRedefinida123", alvo_atualizado.senha_hash)
    assert not verificar_senha("senhaOriginal123", alvo_atualizado.senha_hash)


def test_redefinir_senha_muito_curta_nao_atualiza(cliente_admin_logado):
    alvo = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)
    hash_antes = alvo.senha_hash

    resp = cliente_admin_logado.post(
        f"/admin/usuarios/{alvo.id}/redefinir-senha",
        data={"nova_senha": "curta"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]

    alvo_atualizado = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)
    assert alvo_atualizado.senha_hash == hash_antes
