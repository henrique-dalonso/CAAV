import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete

from app.plataforma.db.models import Usuario
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import SESSAO_MAX_IDADE_SEGUNDOS, app


NOME_USUARIO_TESTE = "teste_auth_sessao"
SENHA = "senhaTeste123"


@pytest.fixture
def usuario_teste():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Auth Sessão",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_auth_sessao@example.com",
        senha=SENHA,
        eh_admin=False,
    )

    yield

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


def test_sessao_maxima_e_36_horas():
    # Henrique, 2026-08-24: "1 dia e meio de tolerância" — cobre uma
    # folga de um dia pro outro sem expirar à toa, mas ainda expira
    # depois de um fim de semana sem acesso.
    assert SESSAO_MAX_IDADE_SEGUNDOS == 36 * 60 * 60


def test_login_grava_cookie_com_max_age_de_36_horas(usuario_teste):
    cliente = TestClient(app)

    resp = cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA})

    assert f"Max-Age={SESSAO_MAX_IDADE_SEGUNDOS}" in resp.headers["set-cookie"]


def test_requisicao_autenticada_renova_o_cookie_da_sessao(usuario_teste):
    # "Deve renovar se a pessoa acessar, resetando o timer" — toda
    # requisição autenticada precisa vir com um Set-Cookie novo (mesmo
    # Max-Age, mas o navegador recalcula a expiração a partir de AGORA),
    # não só a do login. Ver auth.usuario_logado.
    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA})

    resp = cliente.get("/")

    assert resp.status_code == 200
    assert f"Max-Age={SESSAO_MAX_IDADE_SEGUNDOS}" in resp.headers["set-cookie"]


def test_visitante_sem_login_nao_recebe_cookie_de_sessao_renovado():
    cliente = TestClient(app)

    resp = cliente.get("/", follow_redirects=False)

    assert "set-cookie" not in resp.headers
