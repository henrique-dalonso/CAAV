import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.plataforma.db.models import Ferramenta, Usuario, UsuarioFerramenta
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_ADMIN_PLATAFORMA = "teste_historico_admin_plataforma_aburesi"
NOME_ADMIN_SO_FERRAMENTA = "teste_historico_admin_ferramenta_aburesi"
SENHA = "senhaTeste123"


@pytest.fixture
def limpar_usuarios_teste():
    with obter_sessao() as sessao:
        ids = sessao.exec(
            select(Usuario.id).where(
                Usuario.nome_usuario.in_([NOME_ADMIN_PLATAFORMA, NOME_ADMIN_SO_FERRAMENTA])
            )
        ).all()
        if ids:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id.in_(ids)))
        sessao.exec(
            delete(Usuario).where(
                Usuario.nome_usuario.in_([NOME_ADMIN_PLATAFORMA, NOME_ADMIN_SO_FERRAMENTA])
            )
        )
        sessao.commit()

    yield

    with obter_sessao() as sessao:
        ids = sessao.exec(
            select(Usuario.id).where(
                Usuario.nome_usuario.in_([NOME_ADMIN_PLATAFORMA, NOME_ADMIN_SO_FERRAMENTA])
            )
        ).all()
        if ids:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id.in_(ids)))
        sessao.exec(
            delete(Usuario).where(
                Usuario.nome_usuario.in_([NOME_ADMIN_PLATAFORMA, NOME_ADMIN_SO_FERRAMENTA])
            )
        )
        sessao.commit()


def test_pagina_historico_exige_login():
    cliente = TestClient(app)

    resp = cliente.get("/extratus-aburesi/historico", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_pagina_historico_admin_de_ferramenta_sem_ser_admin_plataforma_e_recusado(limpar_usuarios_teste):
    """Ver comentário equivalente em tests/ferramentas/extratus/
    test_historico.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        aburesi_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "extratus-aburesi")).first()

    criar_usuario(
        nome="Teste Historico Admin Ferramenta Aburesi",
        nome_usuario=NOME_ADMIN_SO_FERRAMENTA,
        email="teste_historico_admin_ferramenta_aburesi@example.com",
        senha=SENHA,
        eh_admin=False,
        ferramenta_ids=[aburesi_id],
        ferramentas_admin_ids=[aburesi_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_SO_FERRAMENTA, "senha": SENHA})

    resp = cliente.get("/extratus-aburesi/historico")

    assert resp.status_code == 403


def test_pagina_historico_admin_da_plataforma_acessa(limpar_usuarios_teste):
    criar_usuario(
        nome="Teste Historico Admin Plataforma Aburesi",
        nome_usuario=NOME_ADMIN_PLATAFORMA,
        email="teste_historico_admin_plataforma_aburesi@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_PLATAFORMA, "senha": SENHA})

    resp = cliente.get("/extratus-aburesi/historico")

    assert resp.status_code == 200
    assert "abas-extratus" not in resp.text
    assert "Custos" in resp.text
