import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete

from app.plataforma.db.models import Usuario
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_ADMIN_PLATAFORMA = "teste_admin_custos_plataforma"
NOME_COORDENADOR = "teste_admin_custos_coord"
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


def test_pagina_custos_grade_exige_login():
    cliente = TestClient(app)

    resp = cliente.get("/admin/custos", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_pagina_custos_detalhe_exige_login():
    cliente = TestClient(app)

    resp = cliente.get("/admin/custos/extratus-relatorios", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_pagina_custos_detalhe_coordenador_sem_ser_admin_plataforma_e_recusado(limpar_usuarios_teste):
    """Custos é 100% admin-da-plataforma — nem coordenador com todas as
    ferramentas liberadas acessa (não existe mais "admin da ferramenta"
    pra abrir essa porta, ver docstring de UsuarioFerramenta)."""
    criar_usuario(
        nome="Teste Coordenador Custos",
        nome_usuario=NOME_COORDENADOR,
        email="teste_admin_custos_coord@example.com",
        senha=SENHA,
        eh_admin=False,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_COORDENADOR, "senha": SENHA})

    resp = cliente.get("/admin/custos/extratus-relatorios")

    assert resp.status_code == 403


def test_pagina_custos_detalhe_admin_da_plataforma_acessa(limpar_usuarios_teste):
    criar_usuario(
        nome="Teste Admin Custos Plataforma",
        nome_usuario=NOME_ADMIN_PLATAFORMA,
        email="teste_admin_custos_plataforma@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_PLATAFORMA, "senha": SENHA})

    resp_relatorios = cliente.get("/admin/custos/extratus-relatorios")
    resp_aburesi = cliente.get("/admin/custos/extratus-aburesi")

    assert resp_relatorios.status_code == 200
    assert "Extratus - Relatórios" in resp_relatorios.text
    assert resp_aburesi.status_code == 200
    assert "Extratus - Aburesi" in resp_aburesi.text


def test_pagina_custos_detalhe_chave_invalida_404(limpar_usuarios_teste):
    criar_usuario(
        nome="Teste Admin Custos Plataforma",
        nome_usuario=NOME_ADMIN_PLATAFORMA,
        email="teste_admin_custos_plataforma@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_PLATAFORMA, "senha": SENHA})

    resp = cliente.get("/admin/custos/ferramenta-que-nao-existe")

    assert resp.status_code == 404


def test_pagina_custos_detalhe_mostra_dashboard_novo(limpar_usuarios_teste):
    """Redesenho 2026-08-26 (Henrique, diretoria: "tela de insights
    financeiros") — confere que as novas seções renderizam sem quebrar."""
    criar_usuario(
        nome="Teste Admin Custos Plataforma",
        nome_usuario=NOME_ADMIN_PLATAFORMA,
        email="teste_admin_custos_plataforma@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_PLATAFORMA, "senha": SENHA})

    resp = cliente.get("/admin/custos/extratus-relatorios")

    assert resp.status_code == 200
    assert "Mês atual" in resp.text
    assert "Economia estimada no mês" in resp.text
    assert "Gasto ao longo do tempo" in resp.text
    assert "Por status" in resp.text
    assert "Por modelo de IA" in resp.text
    assert 'id="dados-grafico-custos"' in resp.text


def test_salvar_parametros_economia_admin_atualiza_e_reflete_na_tela(limpar_usuarios_teste):
    criar_usuario(
        nome="Teste Admin Custos Plataforma",
        nome_usuario=NOME_ADMIN_PLATAFORMA,
        email="teste_admin_custos_plataforma@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_PLATAFORMA, "senha": SENHA})

    resp = cliente.post(
        "/admin/custos/extratus-relatorios/parametros-economia",
        data={"horas_estimadas_por_caso": "4.5", "valor_hora_profissional": "250"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/custos/extratus-relatorios"

    resp_tela = cliente.get("/admin/custos/extratus-relatorios")
    assert 'value="4.5"' in resp_tela.text
    assert 'value="250.0"' in resp_tela.text

    # devolve ao valor padrão pra não vazar estado entre testes/sessões
    cliente.post(
        "/admin/custos/extratus-relatorios/parametros-economia",
        data={"horas_estimadas_por_caso": "3.0", "valor_hora_profissional": "200.0"},
    )


def test_salvar_parametros_economia_valor_invalido_mostra_erro_sem_salvar(limpar_usuarios_teste):
    criar_usuario(
        nome="Teste Admin Custos Plataforma",
        nome_usuario=NOME_ADMIN_PLATAFORMA,
        email="teste_admin_custos_plataforma@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_PLATAFORMA, "senha": SENHA})

    resp = cliente.post(
        "/admin/custos/extratus-relatorios/parametros-economia",
        data={"horas_estimadas_por_caso": "0", "valor_hora_profissional": "200"},
    )

    assert resp.status_code == 200
    assert "maior que zero" in resp.text


def test_salvar_parametros_economia_chave_invalida_404(limpar_usuarios_teste):
    criar_usuario(
        nome="Teste Admin Custos Plataforma",
        nome_usuario=NOME_ADMIN_PLATAFORMA,
        email="teste_admin_custos_plataforma@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_ADMIN_PLATAFORMA, "senha": SENHA})

    resp = cliente.post(
        "/admin/custos/ferramenta-que-nao-existe/parametros-economia",
        data={"horas_estimadas_por_caso": "3", "valor_hora_profissional": "200"},
    )

    assert resp.status_code == 404
