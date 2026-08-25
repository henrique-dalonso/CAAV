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
    """Extrai a tag <a ...>...</a> inteira do botão "Voltar" no
    cabeçalho, ou None se não estiver presente."""
    match = re.search(r'<a href="[^"]*" class="botao-voltar-topo"[^>]*>.*?</a>', html, re.DOTALL)
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


def test_login_redireciona_pra_home_que_nunca_mostra_botao_voltar(cliente_logado):
    """O login (fixture) já seguiu o redirect e pousou em "/" — Home
    nunca mostra o botão, mesmo sendo a primeira parada real da sessão
    (regra explícita de Henrique: nunca em Login/Home)."""
    resp = cliente_logado.get("/")

    assert resp.status_code == 200
    assert _botao_voltar(resp.text) is None


def test_segunda_pagina_mostra_botao_voltar_com_nome_da_primeira(cliente_logado):
    """Regressão do bug real de 2026-08-25: SessionMiddleware registrada
    ANTES dos middlewares que escrevem em request.session virava a
    camada mais INTERNA da pilha — sua escrita do cookie acontecia antes
    de middleware_rastrear_pagina_anterior atualizar "ultima_pagina",
    então a mudança nunca ia pro cookie de verdade (o botão nunca
    aparecia, em nenhuma página, nunca)."""
    cliente_logado.get("/admin/ferramentas")
    resp = cliente_logado.get("/admin/ferramentas/extratus-relatorios")

    assert resp.status_code == 200
    botao = _botao_voltar(resp.text)
    assert botao is not None
    assert 'href="/admin/ferramentas"' in botao
    assert "Voltar para Ferramentas" in botao


def test_pagina_sem_nome_cadastrado_mostra_botao_generico(cliente_logado):
    cliente_logado.get("/rota-sem-nome-cadastrado")  # sem entrada em nomes_paginas.py, 404
    resp = cliente_logado.get("/admin/ferramentas")

    botao = _botao_voltar(resp.text)
    assert botao is not None
    assert 'href="/rota-sem-nome-cadastrado"' in botao
    assert ">Voltar<" in botao
    assert "Voltar para" not in botao
