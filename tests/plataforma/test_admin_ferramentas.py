import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete

from app.plataforma.db.models import Usuario
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_ADMIN_PLATAFORMA = "teste_admin_ferramentas_plataforma"
NOME_COORDENADOR = "teste_admin_ferramentas_coord"
SENHA = "senhaTeste123"


@pytest.fixture
def limpar_usuarios_teste():
    with obter_sessao() as sessao:
        sessao.exec(
            delete(Usuario).where(
                Usuario.nome_usuario.in_([NOME_ADMIN_PLATAFORMA, NOME_COORDENADOR])
            )
        )
        sessao.commit()

    yield

    with obter_sessao() as sessao:
        sessao.exec(
            delete(Usuario).where(
                Usuario.nome_usuario.in_([NOME_ADMIN_PLATAFORMA, NOME_COORDENADOR])
            )
        )
        sessao.commit()


def test_pagina_ferramenta_detalhe_exige_login():
    cliente = TestClient(app)

    resp = cliente.get("/admin/ferramentas/extratus-relatorios", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_pagina_ferramenta_detalhe_coordenador_sem_ser_admin_plataforma_e_recusado(limpar_usuarios_teste):
    """Configurações do Robô saiu de dentro de cada ferramenta (engrenagem
    própria, acessível a coordenador com admin_ferramenta) e virou 100%
    admin-da-plataforma — Henrique, 2026-08-24: "área extremamente
    sensível". admin_ferramenta foi removido do sistema por completo."""
    criar_usuario(
        nome="Teste Coordenador Ferramentas",
        nome_usuario=NOME_COORDENADOR,
        email="teste_admin_ferramentas_coord@example.com",
        senha=SENHA,
        eh_admin=False,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_COORDENADOR, "senha": SENHA})

    resp = cliente.get("/admin/ferramentas/extratus-relatorios")

    assert resp.status_code == 403


def test_pagina_ferramenta_detalhe_admin_da_plataforma_acessa(limpar_usuarios_teste):
    criar_usuario(
        nome="Teste Admin Ferramentas Plataforma",
        nome_usuario=NOME_ADMIN_PLATAFORMA,
        email="teste_admin_ferramentas_plataforma@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_PLATAFORMA, "senha": SENHA})

    resp_relatorios = cliente.get("/admin/ferramentas/extratus-relatorios")
    resp_aburesi = cliente.get("/admin/ferramentas/extratus-aburesi")

    assert resp_relatorios.status_code == 200
    assert "Configurações — Extratus - Relatórios" in resp_relatorios.text
    assert resp_aburesi.status_code == 200
    assert "Configurações — Extratus - Aburesi" in resp_aburesi.text


def test_pagina_ferramenta_detalhe_chave_invalida_404(limpar_usuarios_teste):
    criar_usuario(
        nome="Teste Admin Ferramentas Plataforma",
        nome_usuario=NOME_ADMIN_PLATAFORMA,
        email="teste_admin_ferramentas_plataforma@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_PLATAFORMA, "senha": SENHA})

    resp = cliente.get("/admin/ferramentas/ferramenta-que-nao-existe")

    assert resp.status_code == 404
