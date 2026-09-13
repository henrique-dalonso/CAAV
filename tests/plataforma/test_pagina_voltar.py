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
    """Extrai a tag <button ...>...</button> inteira do botão "Voltar" no
    cabeçalho, ou None se não estiver presente."""
    match = re.search(r'<button[^>]*class="botao-voltar-topo"[^>]*>.*?</button>', html, re.DOTALL)
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
    nada "antes" dela faz sentido mostrar."""
    resp = cliente_logado.get("/")

    assert resp.status_code == 200
    assert _botao_voltar(resp.text) is None


def test_login_nunca_mostra_botao_voltar():
    cliente = TestClient(app)
    resp = cliente.get("/login")

    assert resp.status_code == 200
    assert _botao_voltar(resp.text) is None


def test_outras_paginas_mostram_botao_voltar_sempre_com_texto_fixo(cliente_logado):
    """Henrique, 2026-09-13, 3ª geração do botão: descartou 100% o nome
    dinâmico da tela anterior ("ficou horrível, texto às vezes imenso")
    — agora é sempre só "Voltar", em qualquer tela fora de Início/Login,
    não importa de onde a pessoa veio."""
    resp = cliente_logado.get("/admin/ferramentas")

    botao = _botao_voltar(resp.text)
    assert botao is not None
    assert ">Voltar<" in botao
    assert "Voltar para" not in botao


def test_botao_usa_history_back_do_navegador(cliente_logado):
    """A troca de mecanismo é o ponto central desta rodada: em vez de uma
    "última página" calculada no servidor (que não enxergava navegação
    via JavaScript dentro de uma ferramenta, sempre voltando longe
    demais), o botão usa o histórico real do próprio navegador."""
    resp = cliente_logado.get("/admin/ferramentas")

    botao = _botao_voltar(resp.text)
    assert botao is not None
    assert 'onclick="history.back()"' in botao


def test_botao_fica_dentro_do_cabecalho_ao_lado_da_marca(cliente_logado):
    """Henrique, 2026-09-13: o botão antigo era position:fixed, solto na
    viewport, "parecia tapa-buraco isolado no canto". Agora precisa
    estar de verdade dentro de .marca-sistema, no fluxo normal do
    cabeçalho — não mais fora de .pagina/.barra-superior."""
    resp = cliente_logado.get("/admin/ferramentas")

    marca = re.search(r'<div class="marca-sistema">.*?</div>\s*</div>', resp.text, re.DOTALL)
    assert marca is not None
    assert "botao-voltar-topo" in marca.group(0)
