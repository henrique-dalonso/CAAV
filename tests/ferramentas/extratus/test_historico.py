import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.plataforma.db.models import Ferramenta, Usuario, UsuarioFerramenta
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_ADMIN_PLATAFORMA = "teste_historico_admin_plataforma"
NOME_ADMIN_SO_FERRAMENTA = "teste_historico_admin_ferramenta"
SENHA = "senhaTeste123"


@pytest.fixture
def limpar_usuarios_teste():
    with obter_sessao() as sessao:
        ids = sessao.exec(
            select(Usuario.id).where(
                Usuario.nome_usuario.in_([NOME_ADMIN_PLATAFORMA, NOME_ADMIN_SO_FERRAMENTA])
            )
        ).all()
        # Apaga os vínculos de ferramenta ANTES do usuário — um id
        # reciclado pelo SQLite pode "herdar" UsuarioFerramenta órfã de
        # uma rodada anterior (mesmo bug já visto antes nesta suíte).
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

    resp = cliente.get("/extratus/historico", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_pagina_historico_admin_de_ferramenta_sem_ser_admin_plataforma_e_recusado(limpar_usuarios_teste):
    """Henrique, 2026-08-11: Custos deixou de ser uma aba dentro do
    Extratus — só admin da PLATAFORMA acessa agora, mesmo que a pessoa
    seja "admin da ferramenta" (liberado só nessa ferramenta, sem ser
    admin geral). Antes desta mudança esse mesmo usuário conseguia
    acessar; hoje precisa ser barrado — é exatamente o comportamento
    que essa correção existe pra travar."""
    with obter_sessao() as sessao:
        extratus_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "extratus")).first()

    criar_usuario(
        nome="Teste Historico Admin Ferramenta",
        nome_usuario=NOME_ADMIN_SO_FERRAMENTA,
        email="teste_historico_admin_ferramenta@example.com",
        senha=SENHA,
        eh_admin=False,
        ferramenta_ids=[extratus_id],
        ferramentas_admin_ids=[extratus_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_SO_FERRAMENTA, "senha": SENHA})

    resp = cliente.get("/extratus/historico")

    assert resp.status_code == 403


def test_pagina_historico_admin_da_plataforma_acessa(limpar_usuarios_teste):
    criar_usuario(
        nome="Teste Historico Admin Plataforma",
        nome_usuario=NOME_ADMIN_PLATAFORMA,
        email="teste_historico_admin_plataforma@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_PLATAFORMA, "senha": SENHA})

    resp = cliente.get("/extratus/historico")

    assert resp.status_code == 200
    # Sem cabeçalho/abas do Extratus — só a tela dedicada de custos.
    assert "abas-extratus" not in resp.text
    assert "Custos" in resp.text
