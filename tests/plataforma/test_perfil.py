import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete

from app.plataforma.auth import verificar_senha
from app.plataforma.db.models import Usuario
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import buscar_usuario_por_nome_usuario, criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_TESTE = "teste_perfil_senha"
SENHA_INICIAL = "senhaInicial123"


@pytest.fixture
def cliente_logado():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Perfil Senha",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_perfil_senha@example.com",
        senha=SENHA_INICIAL,
        eh_admin=False,
    )

    cliente = TestClient(app)
    cliente.post(
        "/login",
        data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA_INICIAL},
    )

    yield cliente

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


def _hash_atual():
    return buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE).senha_hash


def test_alterar_senha_com_senha_atual_errada_nao_muda_nada(cliente_logado):
    hash_antes = _hash_atual()

    resp = cliente_logado.post(
        "/perfil/senha",
        data={
            "senha_atual": "senhaErrada",
            "nova_senha": "senhaNova12345",
            "confirmar_senha": "senhaNova12345",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]
    assert _hash_atual() == hash_antes


def test_alterar_senha_com_confirmacao_diferente_nao_muda_nada(cliente_logado):
    hash_antes = _hash_atual()

    resp = cliente_logado.post(
        "/perfil/senha",
        data={
            "senha_atual": SENHA_INICIAL,
            "nova_senha": "senhaNova12345",
            "confirmar_senha": "outraCoisaTotalmenteDiferente",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]
    assert _hash_atual() == hash_antes


def test_alterar_senha_muito_curta_nao_muda_nada(cliente_logado):
    hash_antes = _hash_atual()

    resp = cliente_logado.post(
        "/perfil/senha",
        data={
            "senha_atual": SENHA_INICIAL,
            "nova_senha": "curta",
            "confirmar_senha": "curta",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]
    assert _hash_atual() == hash_antes


def test_alterar_senha_com_dados_corretos_atualiza_hash(cliente_logado):
    resp = cliente_logado.post(
        "/perfil/senha",
        data={
            "senha_atual": SENHA_INICIAL,
            "nova_senha": "senhaNova12345",
            "confirmar_senha": "senhaNova12345",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]

    usuario_atualizado = buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE)
    assert verificar_senha("senhaNova12345", usuario_atualizado.senha_hash)
    assert not verificar_senha(SENHA_INICIAL, usuario_atualizado.senha_hash)


def test_novo_usuario_comeca_com_tema_sistema(cliente_logado):
    assert buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE).tema == "sistema"


def test_alterar_tema_para_valor_valido_salva(cliente_logado):
    resp = cliente_logado.post(
        "/perfil/preferencias/tema",
        data={"tema": "escuro"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE).tema == "escuro"


def test_alterar_tema_para_valor_invalido_nao_muda_nada(cliente_logado):
    resp = cliente_logado.post(
        "/perfil/preferencias/tema",
        data={"tema": "roxo"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE).tema == "sistema"


def test_pagina_perfil_aplica_data_theme_quando_usuario_escolheu_escuro(cliente_logado):
    cliente_logado.post("/perfil/preferencias/tema", data={"tema": "escuro"})

    resp = cliente_logado.get("/perfil/preferencias")

    assert 'data-theme="escuro"' in resp.text


def test_pagina_perfil_nao_aplica_data_theme_no_automatico(cliente_logado):
    resp = cliente_logado.get("/perfil/preferencias")

    assert "data-theme=" not in resp.text


def test_novo_usuario_comeca_com_cor_perfil_padrao(cliente_logado):
    assert buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE).cor_perfil == "#4f46e5"


def test_alterar_cor_perfil_para_valor_valido_salva(cliente_logado):
    resp = cliente_logado.post(
        "/perfil/preferencias/cor",
        data={"cor": "#16a34a"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE).cor_perfil == "#16a34a"


def test_alterar_cor_perfil_para_valor_invalido_nao_muda_nada(cliente_logado):
    resp = cliente_logado.post(
        "/perfil/preferencias/cor",
        data={"cor": "javascript:alert(1)"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE).cor_perfil == "#4f46e5"


def test_cor_perfil_escolhida_aparece_no_avatar_do_cabecalho(cliente_logado):
    cliente_logado.post("/perfil/preferencias/cor", data={"cor": "#e11d48"})

    resp = cliente_logado.get("/perfil/dados")

    assert "background: #e11d48;" in resp.text
