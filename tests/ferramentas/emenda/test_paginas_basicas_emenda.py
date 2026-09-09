"""Smoke tests de acesso às 4 telas de Emenda (Fila do Robô, Gerar
Relatório URGENTE, Relatórios do Robô e Relatórios URGENTES já têm teste
dedicado em test_relatorios_manuais_emenda.py) — provam que o mount de
router/static em app/plataforma/web/main.py e a checagem de permissão
(`exigir_acesso_ferramenta("emenda")` / `exigir_acesso_manual("emenda")`)
funcionam de ponta a ponta pro novo slug, sem repetir a cobertura extensa
que Extratus-Relatórios/Aburesi já têm pra esse MESMO comportamento
mecânico (mirror 1:1 do motor compartilhado)."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.plataforma.db.models import Ferramenta, Usuario, UsuarioFerramenta
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_COM_ACESSO = "teste_paginas_basicas_emenda_com_acesso"
NOME_USUARIO_SEM_ACESSO = "teste_paginas_basicas_emenda_sem_acesso"
SENHA = "senhaTeste123"


def _limpar(nome_usuario):
    with obter_sessao() as sessao:
        usuario = sessao.exec(select(Usuario).where(Usuario.nome_usuario == nome_usuario)).first()
        if usuario:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario.id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == nome_usuario))
        sessao.commit()


@pytest.fixture
def cliente_com_acesso():
    _limpar(NOME_USUARIO_COM_ACESSO)

    with obter_sessao() as sessao:
        ferramenta_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "emenda")).first()

    criar_usuario(
        nome="Teste Páginas Básicas Emenda Com Acesso", nome_usuario=NOME_USUARIO_COM_ACESSO,
        email="teste_paginas_basicas_emenda_com_acesso@example.com", senha=SENHA, eh_admin=False,
        ferramenta_ids=[ferramenta_id],
        ferramentas_manual_ids=[ferramenta_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_COM_ACESSO, "senha": SENHA})

    yield cliente

    _limpar(NOME_USUARIO_COM_ACESSO)


@pytest.fixture
def cliente_sem_acesso():
    _limpar(NOME_USUARIO_SEM_ACESSO)

    criar_usuario(
        nome="Teste Páginas Básicas Emenda Sem Acesso", nome_usuario=NOME_USUARIO_SEM_ACESSO,
        email="teste_paginas_basicas_emenda_sem_acesso@example.com", senha=SENHA, eh_admin=False,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_SEM_ACESSO, "senha": SENHA})

    yield cliente

    _limpar(NOME_USUARIO_SEM_ACESSO)


def test_fila_robo_emenda_carrega_pra_quem_tem_acesso(cliente_com_acesso):
    resp = cliente_com_acesso.get("/emenda/fila-robo")
    assert resp.status_code == 200
    assert "Fila do Robô" in resp.text


def test_fila_robo_emenda_bloqueada_pra_quem_nao_tem_acesso(cliente_sem_acesso):
    resp = cliente_sem_acesso.get("/emenda/fila-robo")
    assert resp.status_code == 403


def test_relatorios_robo_emenda_carrega(cliente_com_acesso):
    resp = cliente_com_acesso.get("/emenda/relatorios-robo")
    assert resp.status_code == 200


def test_gerar_relatorio_urgente_emenda_carrega_pra_quem_tem_acesso_manual(cliente_com_acesso):
    resp = cliente_com_acesso.get("/emenda/fila-urgentes")
    assert resp.status_code == 200


def test_estatico_css_emenda_e_servido():
    """Prova que o mount de `/emenda/static` em app/plataforma/web/main.py
    de fato aponta pra pasta certa (app/ferramentas/emenda/web/static/)."""
    cliente = TestClient(app)
    resp = cliente.get("/emenda/static/extratus.css")
    assert resp.status_code == 200
