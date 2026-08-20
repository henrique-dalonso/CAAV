import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.plataforma.db.models import Ferramenta, Usuario, UsuarioFerramenta
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.auth import exigir_login
from app.plataforma.web.main import app


NOME_COLABORADOR_TESTE = "teste_erro_colaborador"


def _apagar_usuario_teste_e_vinculos():
    # Precisa apagar UsuarioFerramenta ANTES do Usuario (sem isso, o
    # vínculo fica órfão no banco e quebra o próximo teste com
    # "UNIQUE constraint failed" quando um novo usuário reaproveita o
    # mesmo id — achado rodando a suíte pela primeira vez com este teste).
    with obter_sessao() as sessao:
        usuario = sessao.exec(select(Usuario).where(Usuario.nome_usuario == NOME_COLABORADOR_TESTE)).first()
        if usuario:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario.id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_COLABORADOR_TESTE))
        sessao.commit()


@pytest.fixture
def cliente_colaborador_logado():
    """Usuário comum (não-admin), com acesso à ferramenta "extratus" E ao
    fluxo Manual/URGENTE dela — usado pra provocar um 403 de verdade
    (rota /admin exige `exigir_admin`, ver admin.py) e um 404 com detail
    próprio (download de relatório inexistente exige acesso_manual, ver
    relatorios_manuais.py)."""
    _apagar_usuario_teste_e_vinculos()

    with obter_sessao() as sessao:
        ferramenta_extratus = sessao.exec(select(Ferramenta).where(Ferramenta.slug == "extratus")).first()

    criar_usuario(
        nome="Teste Erro Colaborador",
        nome_usuario=NOME_COLABORADOR_TESTE,
        email="teste_erro_colaborador@example.com",
        senha="senhaColab12345",
        eh_admin=False,
        ferramenta_ids=[ferramenta_extratus.id] if ferramenta_extratus else [],
        ferramentas_manual_ids=[ferramenta_extratus.id] if ferramenta_extratus else [],
    )

    cliente = TestClient(app)
    cliente.post(
        "/login",
        data={"usuario_login": NOME_COLABORADOR_TESTE, "senha": "senhaColab12345"},
    )

    yield cliente

    _apagar_usuario_teste_e_vinculos()


def _eh_pagina_de_erro_estilizada(resposta):
    """Confirma que a resposta é a página HTML nova (erro.html/erro.css),
    não o JSON cru padrão do FastAPI/Starlette (`{"detail": "..."}`)."""
    corpo = resposta.text
    assert resposta.headers["content-type"].startswith("text/html")
    assert "erro-cartao" in corpo
    assert "erro.css" in corpo
    return corpo


def test_404_pagina_inexistente_mostra_pagina_estilizada_em_portugues():
    # Sem login nenhum — uma URL que não bate com rota nenhuma nunca passa
    # por `exigir_login`, então o handler tem que funcionar mesmo sem
    # usuário nenhum na sessão (por isso erro.html não estende base.html).
    cliente = TestClient(app)
    resposta = cliente.get("/essa-pagina-com-certeza-nao-existe")

    assert resposta.status_code == 404
    corpo = _eh_pagina_de_erro_estilizada(resposta)
    assert "Não encontramos isso" in corpo
    # O Starlette preenche `detail="Not Found"` sozinho quando nenhuma rota
    # bate — não pode vazar esse texto em inglês pra tela.
    assert "Not Found" not in corpo
    assert "A página ou o arquivo que você procura não existe" in corpo


def test_404_com_detalhe_especifico_mostra_a_mensagem_customizada(cliente_colaborador_logado):
    # Rota real que levanta 404 com detail próprio (ver inbox.py) — tem
    # que mostrar ESSA mensagem, não a genérica.
    resposta = cliente_colaborador_logado.get("/extratus/download/arquivo-que-nao-existe.docx")

    assert resposta.status_code == 404
    corpo = _eh_pagina_de_erro_estilizada(resposta)
    assert "Arquivo não encontrado." in corpo


def test_403_sem_permissao_mostra_orientacao_de_pedir_acesso(cliente_colaborador_logado):
    # /admin inteiro exige `exigir_admin` (ver admin.py) — colaborador
    # comum tem que cair no 403 estilizado, com a orientação extra.
    resposta = cliente_colaborador_logado.get("/admin")

    assert resposta.status_code == 403
    corpo = _eh_pagina_de_erro_estilizada(resposta)
    assert "Sem permissão" in corpo
    assert "Acesso restrito a administradores." in corpo
    assert "Peça a um administrador para liberar seu acesso." in corpo


def test_404_sem_orientacao_de_pedir_acesso():
    # A orientação "peça a um administrador" é só do 403 — não pode
    # vazar pra outros tipos de erro.
    cliente = TestClient(app)
    resposta = cliente.get("/essa-pagina-com-certeza-nao-existe")

    corpo = _eh_pagina_de_erro_estilizada(resposta)
    assert "Peça a um administrador" not in corpo


def test_500_bug_real_mostra_pagina_estilizada_e_nao_derruba_o_site():
    # Simula um bug de verdade (exceção não tratada) trocando a
    # dependência de login por uma que sempre quebra — sem isso, um bug
    # real em qualquer rota cairia no erro cru do FastAPI/Starlette.
    def _dependencia_quebrada():
        raise RuntimeError("bug simulado pra teste")

    app.dependency_overrides[exigir_login] = _dependencia_quebrada
    try:
        cliente = TestClient(app, raise_server_exceptions=False)
        resposta = cliente.get("/")
    finally:
        del app.dependency_overrides[exigir_login]

    assert resposta.status_code == 500
    corpo = _eh_pagina_de_erro_estilizada(resposta)
    assert "Algo deu errado" in corpo
    assert "avise o suporte" in corpo
