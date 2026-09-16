from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.plataforma.db.models import Ferramenta, NotificacaoDispensada, Usuario, UsuarioFerramenta
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web import notificacoes
from app.plataforma.web.main import app


def _buscar_ferramenta_id_por_slug(slug):
    with obter_sessao() as sessao:
        return sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == slug)).first()


NOME_USUARIO_TESTE = "teste_notificacoes_usuario"


@pytest.fixture
def usuario_sem_acesso():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    usuario = criar_usuario(
        nome="Teste Notificações",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_notificacoes@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        ferramenta_ids=[],
    )

    yield usuario

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


def test_usuario_sem_acesso_a_nenhuma_ferramenta_nao_ve_nada(usuario_sem_acesso):
    assert notificacoes.notificacoes_do_usuario(usuario_sem_acesso) == []


def test_agrega_so_ferramentas_com_acesso_liberado():
    # Henrique, diretoria, 2026-08-19: as 2 famílias (Sistema/erro e
    # Minhas/pessoal) agora usam o MESMO critério — acesso básico à
    # ferramenta, sem flag própria pra Fila do Robô. Um registro com as
    # duas famílias por ferramenta prova que ambas respeitam o acesso.
    # Mensagens já terminadas em ponto de propósito: esse teste é sobre
    # filtro de acesso, não sobre a normalização de pontuação final
    # (ver test_com_ponto_final_* abaixo pra essa regra em isolado).
    item_pessoal_extratus = {
        "mensagem": "c.", "tipo": "pronto", "link": "/z",
        "pessoal": True, "descartavel": True, "resolver": "/r",
    }
    notificacoes_falsas = [
        ("extratus", "Extratus - Relatórios", lambda usuario_id: [{"mensagem": "a.", "tipo": "erro", "link": "/x", "chave": "job:1"}], lambda usuario_id: [item_pessoal_extratus]),
        ("extratus-aburesi", "Extratus - Aburesi", lambda usuario_id: [{"mensagem": "b.", "tipo": "erro", "link": "/y", "chave": "job:2"}], lambda usuario_id: []),
    ]

    with patch.object(
        notificacoes,
        "usuario_tem_acesso",
        side_effect=lambda usuario, slug: slug == "extratus",
    ), patch.object(notificacoes, "REGISTRO_NOTIFICACOES", notificacoes_falsas), patch.object(
        notificacoes, "listar_chaves_notificacoes_dispensadas", return_value=set()
    ):
        itens = notificacoes.notificacoes_do_usuario(SimpleNamespace(id=1))

    # Henrique, diretoria, 2026-09-16: item de "listar" (não
    # "listar_pessoais") com `chave` ganha descartavel/resolver aqui,
    # de forma genérica — resolver aponta pro endpoint único de
    # dispensa lógica, com ferramenta_slug/chave na query string.
    assert itens == [
        {
            "mensagem": "a.", "tipo": "erro", "link": "/x", "ferramenta": "Extratus - Relatórios",
            "descartavel": True, "resolver": "/notificacoes/ferramentas/dispensar?ferramenta_slug=extratus&chave=job%3A1",
        },
        {**item_pessoal_extratus, "ferramenta": "Extratus - Relatórios"},
    ]


def test_item_de_ferramentas_sem_chave_fica_sem_descartavel():
    # Segurança: se algum módulo esquecer de mandar `chave`, o item
    # continua aparecendo (não quebra), só sem X — igual o
    # comportamento de antes dessa dispensa lógica existir.
    notificacoes_falsas = [
        ("extratus", "Extratus - Relatórios", lambda usuario_id: [{"mensagem": "a.", "tipo": "triagem", "link": "/x"}], lambda usuario_id: []),
    ]

    with patch.object(notificacoes, "usuario_tem_acesso", return_value=True), patch.object(
        notificacoes, "REGISTRO_NOTIFICACOES", notificacoes_falsas
    ), patch.object(notificacoes, "listar_chaves_notificacoes_dispensadas", return_value=set()):
        itens = notificacoes.notificacoes_do_usuario(SimpleNamespace(id=1))

    assert itens == [{"mensagem": "a.", "tipo": "triagem", "link": "/x", "ferramenta": "Extratus - Relatórios"}]


def test_notificacao_ja_dispensada_pelo_usuario_nao_aparece():
    # Henrique, diretoria, 2026-09-16: "um apagar lógico... continua
    # existindo a notificação de fato" — o filtro é só pra QUEM
    # dispensou, por isso este teste patcha listar_chaves_notificacoes_
    # dispensadas devolvendo a chave do item, simulando que ESSE
    # usuário já mandou dispensar.
    notificacoes_falsas = [
        ("extratus", "Extratus - Relatórios", lambda usuario_id: [{"mensagem": "a.", "tipo": "erro", "link": "/x", "chave": "job:1"}], lambda usuario_id: []),
    ]

    with patch.object(notificacoes, "usuario_tem_acesso", return_value=True), patch.object(
        notificacoes, "REGISTRO_NOTIFICACOES", notificacoes_falsas
    ), patch.object(notificacoes, "listar_chaves_notificacoes_dispensadas", return_value={"job:1"}):
        itens = notificacoes.notificacoes_do_usuario(SimpleNamespace(id=1))

    assert itens == []


def test_com_ponto_final_adiciona_ponto_quando_falta():
    assert notificacoes._com_ponto_final("relatório pronto") == "relatório pronto."


def test_com_ponto_final_nao_duplica_pontuacao_existente():
    assert notificacoes._com_ponto_final("já tem ponto.") == "já tem ponto."
    assert notificacoes._com_ponto_final("já tem exclamação!") == "já tem exclamação!"
    assert notificacoes._com_ponto_final("já tem interrogação?") == "já tem interrogação?"


def test_com_ponto_final_string_vazia_fica_vazia():
    assert notificacoes._com_ponto_final("") == ""


def test_endpoint_notificacoes_exige_login():
    cliente = TestClient(app)

    resp = cliente.get("/notificacoes", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_endpoint_notificacoes_devolve_json_pra_quem_esta_logado():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Notificações",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_notificacoes@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        ferramenta_ids=[],
    )

    cliente = TestClient(app)
    cliente.post(
        "/login",
        data={"usuario_login": NOME_USUARIO_TESTE, "senha": "senhaTeste123"},
    )

    resp = cliente.get("/notificacoes")

    assert resp.status_code == 200
    assert resp.json() == {"itens": []}

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


# --- POST /notificacoes/ferramentas/dispensar — dispensa lógica por
# pessoa (Henrique, diretoria, 2026-09-16) ---

def test_endpoint_dispensar_exige_login():
    cliente = TestClient(app)

    resp = cliente.post(
        "/notificacoes/ferramentas/dispensar",
        params={"ferramenta_slug": "extratus", "chave": "job:1"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_endpoint_dispensar_grava_e_e_idempotente():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    extratus_id = _buscar_ferramenta_id_por_slug("extratus")
    usuario = criar_usuario(
        nome="Teste Notificações",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_notificacoes@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        ferramenta_ids=[extratus_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": "senhaTeste123"})

    resp = cliente.post("/notificacoes/ferramentas/dispensar", params={"ferramenta_slug": "extratus", "chave": "job:999"})
    assert resp.status_code == 200

    with obter_sessao() as sessao:
        assert sessao.get(NotificacaoDispensada, (usuario.id, "extratus", "job:999")) is not None

    # 2º clique (ou 2 abas quase juntas) não quebra nem duplica.
    resp2 = cliente.post("/notificacoes/ferramentas/dispensar", params={"ferramenta_slug": "extratus", "chave": "job:999"})
    assert resp2.status_code == 200

    with obter_sessao() as sessao:
        # UsuarioFerramenta precisa ser limpo À PARTE de Usuario: sem
        # isso, o rowid do Usuario deletado é reaproveitado pelo
        # PRÓXIMO teste que cria o mesmo nome_usuario (SQLite reusa
        # max(id)+1), e o vínculo órfão passa a valer pro usuário novo
        # — achado real rodando este arquivo inteiro (vazava acesso
        # falso pro teste seguinte, test_endpoint_dispensar_exige_
        # acesso_a_ferramenta).
        sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario.id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.exec(delete(NotificacaoDispensada).where(NotificacaoDispensada.usuario_id == usuario.id))
        sessao.commit()


def test_endpoint_dispensar_exige_acesso_a_ferramenta():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Notificações",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_notificacoes@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        ferramenta_ids=[],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": "senhaTeste123"})

    resp = cliente.post("/notificacoes/ferramentas/dispensar", params={"ferramenta_slug": "extratus", "chave": "job:1"})

    assert resp.status_code == 404

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


# --- Aba "Erros" (sininho) — só pra admin (Henrique, diretoria,
# 2026-09-16: "cria uma nova aba de notificações para ADM, que notifica
# somente os erros das ferramentas... aparecendo somente para adms") ---

def test_aba_erros_aparece_no_html_pra_admin():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Notificações",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_notificacoes@example.com",
        senha="senhaTeste123",
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": "senhaTeste123"})

    resp = cliente.get("/")

    assert 'id="aba-erros"' in resp.text
    assert 'id="lista-notificacoes-erros"' in resp.text

    with obter_sessao() as sessao:
        # eh_admin=True nunca cria UsuarioFerramenta (ver criar_usuario,
        # app/plataforma/db/usuarios.py) — só Usuario mesmo pra limpar.
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


def test_aba_erros_nao_aparece_no_html_pra_nao_admin():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Notificações",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_notificacoes@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        ferramenta_ids=[],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": "senhaTeste123"})

    resp = cliente.get("/")

    assert 'id="aba-erros"' not in resp.text
    assert 'id="lista-notificacoes-erros"' not in resp.text

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()
