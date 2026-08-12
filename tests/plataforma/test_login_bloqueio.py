import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete

from app.plataforma.db.models import TentativaLoginFalha, Usuario
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import buscar_usuario_por_nome_usuario, criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_TESTE = "teste_bloqueio_login"
SENHA_CORRETA = "senhaCorreta123"


@pytest.fixture
def usuario_teste():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.exec(delete(TentativaLoginFalha))
        sessao.commit()

    criar_usuario(
        nome="Teste Bloqueio Login",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_bloqueio_login@example.com",
        senha=SENHA_CORRETA,
        eh_admin=False,
    )

    yield

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.exec(delete(TentativaLoginFalha))
        sessao.commit()


def test_tres_senhas_erradas_seguidas_bloqueia_conta(usuario_teste):
    cliente = TestClient(app)

    for _ in range(3):
        resp = cliente.post(
            "/login",
            data={"usuario_login": NOME_USUARIO_TESTE, "senha": "errada"},
            follow_redirects=False,
        )

    assert resp.status_code == 401
    assert "bloqueada" in resp.text.lower()

    usuario = buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE)
    assert usuario.bloqueado is True
    assert usuario.bloqueado_em is not None


def test_conta_bloqueada_recusa_login_mesmo_com_senha_certa(usuario_teste):
    cliente = TestClient(app)

    for _ in range(3):
        cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": "errada"})

    resp = cliente.post(
        "/login",
        data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA_CORRETA},
        follow_redirects=False,
    )

    assert resp.status_code == 401
    assert "bloqueada" in resp.text.lower()


def test_acerto_no_meio_zera_contador_e_nao_bloqueia(usuario_teste):
    cliente = TestClient(app)

    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": "errada"})
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": "errada"})
    resp = cliente.post(
        "/login",
        data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA_CORRETA},
        follow_redirects=False,
    )

    assert resp.status_code == 303

    usuario = buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE)
    assert usuario.tentativas_login_falhas == 0
    assert usuario.bloqueado is False


def test_cinco_contas_diferentes_erradas_bloqueia_a_rede(usuario_teste):
    cliente = TestClient(app)

    for i in range(5):
        cliente.post("/login", data={"usuario_login": f"conta_inexistente_{i}", "senha": "errada"})

    # mesmo o dono de uma conta real e não bloqueada, com a senha CERTA,
    # é recusado enquanto a rede estiver bloqueada.
    resp = cliente.post(
        "/login",
        data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA_CORRETA},
        follow_redirects=False,
    )

    assert resp.status_code == 401
    assert "rede" in resp.text.lower()


def test_quatro_contas_diferentes_erradas_nao_bloqueia_a_rede(usuario_teste):
    cliente = TestClient(app)

    for i in range(4):
        cliente.post("/login", data={"usuario_login": f"conta_inexistente_{i}", "senha": "errada"})

    resp = cliente.post(
        "/login",
        data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA_CORRETA},
        follow_redirects=False,
    )

    assert resp.status_code == 303


def test_mesma_conta_inexistente_repetida_nao_conta_como_distinta(usuario_teste):
    cliente = TestClient(app)

    for _ in range(10):
        cliente.post(
            "/login",
            data={"usuario_login": "sempre_a_mesma_conta_inexistente", "senha": "errada"},
        )

    resp = cliente.post(
        "/login",
        data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA_CORRETA},
        follow_redirects=False,
    )

    assert resp.status_code == 303
