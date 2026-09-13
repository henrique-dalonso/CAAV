import re

import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete

from app.plataforma.db.models import Usuario
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_TESTE = "teste_pagina_voltar"
SENHA = "senhaTeste123"


def _botao_voltar(html):
    """Extrai a tag <button ...>...</button> inteira do botão "Voltar"
    (4ª geração: vive dentro do <h1> de cada tela, ver botao_voltar em
    templates_util.py), ou None se não estiver presente."""
    match = re.search(r'<button[^>]*class="botao-voltar-titulo"[^>]*>.*?</button>', html, re.DOTALL)
    return match.group(0) if match else None


@pytest.fixture
def cliente_logado():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Página Voltar",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_pagina_voltar@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA})

    yield cliente

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


def test_home_nunca_mostra_botao_voltar(cliente_logado):
    """Henrique, 2026-08-25: "nunca no Login/Home" — Início é a raiz,
    nada "antes" dela faz sentido mostrar. Na 4ª geração isso acontece
    naturalmente: home.html não tem .cabecalho-ferramenta/<h1> nenhum,
    então nunca chama `botao_voltar()` — sem precisar de checagem de
    rota nenhuma."""
    resp = cliente_logado.get("/")

    assert resp.status_code == 200
    assert _botao_voltar(resp.text) is None


def test_login_nunca_mostra_botao_voltar():
    cliente = TestClient(app)
    resp = cliente.get("/login")

    assert resp.status_code == 200
    assert _botao_voltar(resp.text) is None


def test_outras_paginas_mostram_botao_voltar(cliente_logado):
    """Henrique, 2026-09-13, 4ª geração: o botão saiu do cabeçalho global
    e passou a viver dentro do <h1> de cada tela (3ª geração, ao lado da
    logo, também foi rejeitada: "não gostei da posição"). Ícone só, sem
    texto "Voltar" — a dica (tooltip) já explica, e o botão agora está
    claramente junto do título, contexto suficiente."""
    resp = cliente_logado.get("/admin/ferramentas")

    botao = _botao_voltar(resp.text)
    assert botao is not None
    assert 'data-dica="Voltar"' in botao


def test_botao_usa_history_back_do_navegador(cliente_logado):
    """A troca de mecanismo é o ponto central desta rodada: em vez de uma
    "última página" calculada no servidor (que não enxergava navegação
    via JavaScript dentro de uma ferramenta, sempre voltando longe
    demais), o botão usa o histórico real do próprio navegador."""
    resp = cliente_logado.get("/admin/ferramentas")

    botao = _botao_voltar(resp.text)
    assert botao is not None
    assert 'onclick="history.back()"' in botao


def test_botao_fica_dentro_do_h1_da_tela(cliente_logado):
    """Henrique, 2026-09-13: 2ª geração (position:fixed) "parecia tapa-
    buraco"; 3ª geração (dentro de .marca-sistema, ao lado da logo)
    "não gostei da posição". 4ª geração: o botão precisa estar de
    verdade dentro do <h1> de .cabecalho-ferramenta — sempre alinhado
    com o título da tela, não mais com o cabeçalho global/logo."""
    resp = cliente_logado.get("/admin/ferramentas")

    h1 = re.search(r"<h1>.*?</h1>", resp.text, re.DOTALL)
    assert h1 is not None
    assert "botao-voltar-titulo" in h1.group(0)


def test_botao_aparece_em_varias_ferramentas_diferentes(cliente_logado):
    """Não é um caso isolado de uma tela só — confirma em telas de
    módulos diferentes (Administração e Crivus) que o botão realmente
    aparece em qualquer .cabecalho-ferramenta, não só numa exceção."""
    resp_admin = cliente_logado.get("/admin/ferramentas")
    assert _botao_voltar(resp_admin.text) is not None

    resp_crivus = cliente_logado.get("/crivus/leitor-individual")
    assert _botao_voltar(resp_crivus.text) is not None
