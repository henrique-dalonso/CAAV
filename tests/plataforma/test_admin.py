from datetime import datetime

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


def test_admin_raiz_redireciona_pra_aba_custos(cliente_admin_logado):
    resp = cliente_admin_logado.get("/admin", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/custos"


def test_aba_custos_carrega_grade(cliente_admin_logado):
    resp = cliente_admin_logado.get("/admin/custos")

    assert resp.status_code == 200
    # Grade de ícones (realocada de dentro de cada ferramenta em
    # 2026-08-24) — cada ferramenta com custo de IA rastreado vira um
    # link direto pra /admin/custos/<chave>, não mais /extratus/custos.
    assert "/admin/custos/extratus-relatorios" in resp.text
    assert "/admin/custos/extratus-aburesi" in resp.text
    assert "/extratus/custos" not in resp.text


def test_aba_ferramentas_carrega(cliente_admin_logado):
    resp = cliente_admin_logado.get("/admin/ferramentas")

    assert resp.status_code == 200
    # Ferramentas virou a tela de CONFIGURAÇÃO de cada ferramenta
    # (absorveu "Configurações do Robô", que saiu de dentro de cada
    # ferramenta em 2026-08-24) — não mais um link pra tela de custos.
    assert "/admin/ferramentas/extratus-relatorios" in resp.text
    assert "/admin/ferramentas/extratus-aburesi" in resp.text
    assert "/extratus/custos" not in resp.text


def test_aba_novo_usuario_carrega_formulario(cliente_admin_logado):
    resp = cliente_admin_logado.get("/admin/usuarios/novo")

    assert resp.status_code == 200
    assert "Criar usuário" in resp.text


def test_aba_usuarios_carrega_tabela(cliente_admin_logado):
    resp = cliente_admin_logado.get("/admin/usuarios")

    assert resp.status_code == 200
    assert NOME_ALVO_TESTE in resp.text


def test_redefinir_senha_de_outro_usuario_atualiza_hash(cliente_admin_logado):
    alvo = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)

    resp = cliente_admin_logado.post(
        f"/admin/usuarios/{alvo.id}/redefinir-senha",
        data={"nova_senha": "senhaRedefinida123", "confirmar_senha": "senhaRedefinida123"},
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
        data={"nova_senha": "curta", "confirmar_senha": "curta"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]

    alvo_atualizado = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)
    assert alvo_atualizado.senha_hash == hash_antes


def test_redefinir_senha_com_confirmacao_diferente_nao_atualiza(cliente_admin_logado):
    alvo = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)
    hash_antes = alvo.senha_hash

    resp = cliente_admin_logado.post(
        f"/admin/usuarios/{alvo.id}/redefinir-senha",
        data={"nova_senha": "senhaRedefinida123", "confirmar_senha": "outraSenha456"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]

    alvo_atualizado = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)
    assert alvo_atualizado.senha_hash == hash_antes


def test_desbloquear_usuario_limpa_bloqueio_e_tentativas(cliente_admin_logado):
    alvo = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)

    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, alvo.id)
        usuario.bloqueado = True
        usuario.bloqueado_em = datetime.now()
        usuario.tentativas_login_falhas = 3
        sessao.add(usuario)
        sessao.commit()

    resp = cliente_admin_logado.post(
        f"/admin/usuarios/{alvo.id}/desbloquear",
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]

    alvo_atualizado = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)
    assert alvo_atualizado.bloqueado is False
    assert alvo_atualizado.bloqueado_em is None
    assert alvo_atualizado.tentativas_login_falhas == 0


def test_aba_usuarios_mostra_botao_desbloquear_so_para_bloqueados(cliente_admin_logado):
    alvo = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)

    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, alvo.id)
        usuario.bloqueado = True
        sessao.add(usuario)
        sessao.commit()

    resp = cliente_admin_logado.get("/admin/usuarios")

    assert resp.status_code == 200
    assert f"/admin/usuarios/{alvo.id}/desbloquear" in resp.text

    admin_logado = buscar_usuario_por_nome_usuario(NOME_ADMIN_TESTE)
    assert f"/admin/usuarios/{admin_logado.id}/desbloquear" not in resp.text


def test_aba_usuarios_tem_campo_de_busca_e_checkboxes_de_perfil(cliente_admin_logado):
    resp = cliente_admin_logado.get("/admin/usuarios")

    assert resp.status_code == 200
    assert 'id="campo-busca-usuarios"' in resp.text
    assert 'class="check-input check-filtro-cargo" value="colaborador"' in resp.text
    assert 'class="check-input check-filtro-cargo" value="coordenador"' in resp.text
    assert 'class="check-input check-filtro-cargo" value="admin"' in resp.text


def test_aba_usuarios_data_perfil_e_data_busca_corretos_por_linha(cliente_admin_logado):
    admin_logado = buscar_usuario_por_nome_usuario(NOME_ADMIN_TESTE)
    alvo = buscar_usuario_por_nome_usuario(NOME_ALVO_TESTE)

    resp = cliente_admin_logado.get("/admin/usuarios")

    assert resp.status_code == 200
    assert f'data-perfil="admin"' in resp.text
    assert f'data-perfil="colaborador"' in resp.text
    assert f'data-busca="{admin_logado.nome.lower()} {NOME_ADMIN_TESTE}"' in resp.text
    assert f'data-busca="{alvo.nome.lower()} {NOME_ALVO_TESTE}"' in resp.text
