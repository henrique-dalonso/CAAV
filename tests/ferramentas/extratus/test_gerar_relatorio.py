from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete

from sqlmodel import select

from app.ferramentas.extratus.db import triagem_manual as db_triagem
from app.ferramentas.extratus.db.models import RegistroConferencia, TriagemManual
from app.ferramentas.extratus.web.routes import gerar_relatorio
from app.plataforma.db.models import Ferramenta, Usuario, UsuarioFerramenta
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_A = "teste_inbox_usuario_a"
NOME_USUARIO_B = "teste_inbox_usuario_b"
SENHA = "senhaTeste123"
PREFIXO_TESTE = "teste_inbox_"

CONTEUDO_PDF_FALSO = b"%PDF-1.4\n%teste\n"


@pytest.fixture
def clientes_logados():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario.in_([NOME_USUARIO_A, NOME_USUARIO_B])))
        sessao.commit()

    criar_usuario(
        nome="Teste Inbox A", nome_usuario=NOME_USUARIO_A,
        email="teste_inbox_a@example.com", senha=SENHA, eh_admin=True,
    )
    criar_usuario(
        nome="Teste Inbox B", nome_usuario=NOME_USUARIO_B,
        email="teste_inbox_b@example.com", senha=SENHA, eh_admin=True,
    )

    cliente_a = TestClient(app)
    cliente_a.post("/login", data={"usuario_login": NOME_USUARIO_A, "senha": SENHA})

    cliente_b = TestClient(app)
    cliente_b.post("/login", data={"usuario_login": NOME_USUARIO_B, "senha": SENHA})

    yield cliente_a, cliente_b

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario.in_([NOME_USUARIO_A, NOME_USUARIO_B])))
        sessao.commit()


@pytest.fixture
def limpar_triagem_teste():
    yield
    with obter_sessao() as sessao:
        sessao.exec(delete(TriagemManual).where(TriagemManual.nome_arquivo.like(f"{PREFIXO_TESTE}%")))
        sessao.exec(delete(RegistroConferencia).where(RegistroConferencia.nome_arquivo.like(f"{PREFIXO_TESTE}%")))
        sessao.commit()


def _criar_registro(nome, usuario_id, status="processo_nao_encontrado"):
    with obter_sessao() as sessao:
        registro = TriagemManual(
            nome_arquivo=nome, caminho_pdf=f"/tmp/{nome}", usuario_id=usuario_id, status=status,
        )
        sessao.add(registro)
        sessao.commit()
        sessao.refresh(registro)
        return registro


def test_pagina_inicial_exige_login():
    cliente = TestClient(app)

    resp = cliente.get("/extratus/fila-urgentes", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_estado_exige_login():
    cliente = TestClient(app)

    resp = cliente.get("/extratus/fila-urgentes/estado", follow_redirects=False)

    assert resp.status_code == 303


def test_upload_recusa_mais_de_5_arquivos(clientes_logados, tmp_path, limpar_triagem_teste):
    cliente_a, _ = clientes_logados

    with patch.object(gerar_relatorio, "carregar_config", return_value={"pasta_entrada": str(tmp_path)}):
        arquivos = [
            ("arquivos", (f"{PREFIXO_TESTE}demais_{i}.pdf", CONTEUDO_PDF_FALSO, "application/pdf"))
            for i in range(6)
        ]
        resp = cliente_a.post("/extratus/fila-urgentes/upload", files=arquivos)

    assert resp.status_code == 400


def test_upload_cria_registros_e_agenda_processamento(clientes_logados, tmp_path, limpar_triagem_teste):
    cliente_a, _ = clientes_logados

    with patch.object(
        gerar_relatorio, "carregar_config", return_value={"pasta_entrada": str(tmp_path)},
    ), patch.object(gerar_relatorio, "processar_upload_manual"):
        arquivos = [
            ("arquivos", (f"{PREFIXO_TESTE}um.pdf", CONTEUDO_PDF_FALSO, "application/pdf")),
            ("arquivos", (f"{PREFIXO_TESTE}dois.pdf", CONTEUDO_PDF_FALSO, "application/pdf")),
        ]
        resp = cliente_a.post("/extratus/fila-urgentes/upload", files=arquivos, follow_redirects=False)

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]

    with obter_sessao() as sessao:
        from sqlmodel import select
        registros = sessao.exec(
            select(TriagemManual).where(TriagemManual.nome_arquivo.like(f"{PREFIXO_TESTE}%"))
        ).all()
        nomes = {r.nome_arquivo for r in registros}

    assert f"{PREFIXO_TESTE}um.pdf" in nomes
    assert f"{PREFIXO_TESTE}dois.pdf" in nomes


def test_upload_recusa_arquivo_nao_pdf(clientes_logados, tmp_path, limpar_triagem_teste):
    cliente_a, _ = clientes_logados

    with patch.object(
        gerar_relatorio, "carregar_config", return_value={"pasta_entrada": str(tmp_path)},
    ), patch.object(gerar_relatorio, "processar_upload_manual"):
        arquivos = [("arquivos", (f"{PREFIXO_TESTE}naopdf.txt", b"nao e pdf", "text/plain"))]
        resp = cliente_a.post("/extratus/fila-urgentes/upload", files=arquivos, follow_redirects=False)

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]


def test_estado_so_mostra_registros_do_proprio_usuario(clientes_logados, limpar_triagem_teste):
    cliente_a, cliente_b = clientes_logados

    usuario_a_id = _usuario_id(NOME_USUARIO_A)
    usuario_b_id = _usuario_id(NOME_USUARIO_B)

    registro_a = _criar_registro(f"{PREFIXO_TESTE}pendente_a.pdf", usuario_a_id, status="pendente")
    registro_b = _criar_registro(f"{PREFIXO_TESTE}pendente_b.pdf", usuario_b_id, status="pendente")

    resp = cliente_a.get("/extratus/fila-urgentes/estado")

    assert resp.status_code == 200
    nomes = {item["nome"] for item in resp.json()["pendentes"]}
    assert registro_a.nome_arquivo in nomes
    assert registro_b.nome_arquivo not in nomes


def test_estado_mantem_inconsistencia_em_pendentes_com_aguardando_conferencia(clientes_logados, limpar_triagem_teste):
    """Henrique, 2026-08-12: uma inconsistência (falha de leitura,
    duplicidade, processo não encontrado) precisa continuar em Pendentes
    (bolinha vermelha), não sumir só porque caiu em Conferências."""
    cliente_a, _ = clientes_logados
    usuario_a_id = _usuario_id(NOME_USUARIO_A)

    registro = _criar_registro(f"{PREFIXO_TESTE}inconsistencia_pendente.pdf", usuario_a_id, status="falha_leitura")

    resp = cliente_a.get("/extratus/fila-urgentes/estado")

    assert resp.status_code == 200
    corpo = resp.json()
    pendente = next((item for item in corpo["pendentes"] if item["nome"] == registro.nome_arquivo), None)

    assert pendente is not None
    assert pendente["aguardando_conferencia"] is True
    assert registro.nome_arquivo not in {item["nome"] for item in corpo["processando"]}


def test_conferencia_aprovar_dispara_geracao_em_segundo_plano(clientes_logados, limpar_triagem_teste):
    cliente_a, _ = clientes_logados
    usuario_a_id = _usuario_id(NOME_USUARIO_A)

    registro = _criar_registro(f"{PREFIXO_TESTE}conferencia_aprovar.pdf", usuario_a_id, status="duplicado_em_andamento")

    with patch.object(gerar_relatorio, "retomar_apos_conferencia") as retomar_mock:
        resp = cliente_a.post(
            f"/extratus/fila-urgentes/conferencia/{registro.id}/aprovar", follow_redirects=False,
        )

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]
    assert retomar_mock.called


def test_conferencia_aprovar_sem_processo_quando_nao_encontrado_falha(clientes_logados, limpar_triagem_teste):
    cliente_a, _ = clientes_logados
    usuario_a_id = _usuario_id(NOME_USUARIO_A)

    registro = _criar_registro(f"{PREFIXO_TESTE}sem_processo.pdf", usuario_a_id, status="processo_nao_encontrado")

    resp = cliente_a.post(f"/extratus/fila-urgentes/conferencia/{registro.id}/aprovar", follow_redirects=False)

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]


def test_conferencia_descartar_apaga_registro(clientes_logados, tmp_path, limpar_triagem_teste):
    cliente_a, _ = clientes_logados
    usuario_a_id = _usuario_id(NOME_USUARIO_A)

    caminho = tmp_path / f"{PREFIXO_TESTE}descartar.pdf"
    caminho.write_bytes(CONTEUDO_PDF_FALSO)

    with obter_sessao() as sessao:
        registro = TriagemManual(
            nome_arquivo=caminho.name, caminho_pdf=str(caminho), usuario_id=usuario_a_id,
            status="processo_nao_encontrado",
        )
        sessao.add(registro)
        sessao.commit()
        sessao.refresh(registro)

    resp = cliente_a.post(f"/extratus/fila-urgentes/conferencia/{registro.id}/descartar", follow_redirects=False)

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]
    assert db_triagem.obter_registro(registro.id) is None
    assert not caminho.exists()


def test_usuario_nao_ve_conferencia_de_outro(clientes_logados, limpar_triagem_teste):
    cliente_a, _ = clientes_logados
    usuario_b_id = _usuario_id(NOME_USUARIO_B)

    registro_b = _criar_registro(f"{PREFIXO_TESTE}conferencia_de_outro.pdf", usuario_b_id, status="processo_nao_encontrado")

    resp = cliente_a.post(f"/extratus/fila-urgentes/conferencia/{registro_b.id}/descartar", follow_redirects=False)

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]
    assert db_triagem.obter_registro(registro_b.id) is not None


def _usuario_id(nome_usuario):
    from app.plataforma.db.usuarios import buscar_usuario_por_nome_usuario
    return buscar_usuario_por_nome_usuario(nome_usuario).id


def test_pagina_inicial_mostra_badge_ambar_ate_resolver(clientes_logados, limpar_triagem_teste):
    # Badge "+N" âmbar (Henrique, 2026-08-13) — Conferências pendentes do
    # próprio usuário no fluxo manual. Fica ligado até alguém aprovar ou
    # descartar — só visitar a página não zera mais (achado 2026-08-13:
    # o comportamento antigo, "zera ao revisitar", estava errado).
    cliente_a, _ = clientes_logados
    usuario_a_id = _usuario_id(NOME_USUARIO_A)

    registro = _criar_registro(f"{PREFIXO_TESTE}badge_ambar.pdf", usuario_a_id, status="processo_nao_encontrado")

    # Texto exato do badge nesse tab específico (não só a classe CSS —
    # "Relatórios do Robô" usa a MESMA classe pro badge dele, que é
    # outra coisa; checar só a classe solta pega falso positivo/negativo
    # se houver algum revisão real pendente lá também).
    badge_gerar_relatorio = 'Gerar Relatório URGENTE <span class="contagem-aba contagem-aba-revisao">+1</span>'

    primeira_visita = cliente_a.get("/extratus/fila-urgentes")
    assert primeira_visita.status_code == 200
    assert badge_gerar_relatorio in primeira_visita.text

    segunda_visita = cliente_a.get("/extratus/fila-urgentes")
    assert segunda_visita.status_code == 200
    assert badge_gerar_relatorio in segunda_visita.text

    db_triagem.descartar(registro.id)

    depois_de_resolver = cliente_a.get("/extratus/fila-urgentes")
    assert depois_de_resolver.status_code == 200
    assert badge_gerar_relatorio not in depois_de_resolver.text


# --- Manual/URGENTE virou exceção, restrita a acesso_manual (Henrique,
# diretoria, 2026-08-19) ---

NOME_COLABORADOR_PADRAO_TESTE = "teste_gerar_relatorio_colaborador_padrao"
NOME_COLABORADOR_MANUAL_TESTE = "teste_gerar_relatorio_colaborador_manual"


def _apagar_usuario_e_vinculos(nome_usuario):
    # Apaga UsuarioFerramenta ANTES do Usuario — sem isso, o vínculo fica
    # órfão e "ressurge" num usuário novo que recicle o mesmo id (SQLite),
    # quebrando testes sem relação nenhuma com este arquivo.
    with obter_sessao() as sessao:
        usuario = sessao.exec(select(Usuario).where(Usuario.nome_usuario == nome_usuario)).first()
        if usuario:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario.id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == nome_usuario))
        sessao.commit()


@pytest.fixture
def cliente_colaborador_sem_acesso_manual():
    """Colaborador comum, só com acesso básico à ferramenta (sem
    acesso_manual) — prova que o fluxo Manual/URGENTE não é mais padrão."""
    _apagar_usuario_e_vinculos(NOME_COLABORADOR_PADRAO_TESTE)

    with obter_sessao() as sessao:
        extratus_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "extratus")).first()

    criar_usuario(
        nome="Teste Gerar Relatório Colaborador Padrão",
        nome_usuario=NOME_COLABORADOR_PADRAO_TESTE,
        email="teste_gerar_relatorio_colaborador_padrao@example.com",
        senha=SENHA,
        eh_admin=False,
        ferramenta_ids=[extratus_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_COLABORADOR_PADRAO_TESTE, "senha": SENHA})

    yield cliente

    _apagar_usuario_e_vinculos(NOME_COLABORADOR_PADRAO_TESTE)


@pytest.fixture
def cliente_colaborador_com_acesso_manual():
    """Colaborador comum, com acesso_manual concedido explicitamente —
    prova que o checkbox continua flexível (não travado a coordenador)."""
    _apagar_usuario_e_vinculos(NOME_COLABORADOR_MANUAL_TESTE)

    with obter_sessao() as sessao:
        extratus_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "extratus")).first()

    criar_usuario(
        nome="Teste Gerar Relatório Colaborador Manual",
        nome_usuario=NOME_COLABORADOR_MANUAL_TESTE,
        email="teste_gerar_relatorio_colaborador_manual@example.com",
        senha=SENHA,
        eh_admin=False,
        ferramenta_ids=[extratus_id],
        ferramentas_manual_ids=[extratus_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_COLABORADOR_MANUAL_TESTE, "senha": SENHA})

    yield cliente

    _apagar_usuario_e_vinculos(NOME_COLABORADOR_MANUAL_TESTE)


def test_colaborador_sem_acesso_manual_e_redirecionado_pra_fila(cliente_colaborador_sem_acesso_manual):
    # Henrique, 2026-08-19: a Home/bandeja de apps sempre manda pra "/" —
    # um colaborador sem acesso_manual não pode tomar um 403 seco só por
    # ter clicado no ícone da ferramenta, tem que cair num lugar que ele
    # realmente pode usar (Fila do Robô, o padrão de todo mundo).
    resposta = cliente_colaborador_sem_acesso_manual.get("/extratus/fila-urgentes", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/extratus/fila-robo"

    resposta_seguida = cliente_colaborador_sem_acesso_manual.get("/extratus/fila-urgentes")
    assert resposta_seguida.status_code == 200
    assert "Fila do Robô" in resposta_seguida.text


def test_colaborador_com_acesso_manual_acessa_gerar_relatorio(cliente_colaborador_com_acesso_manual):
    resposta = cliente_colaborador_com_acesso_manual.get("/extratus/fila-urgentes")
    assert resposta.status_code == 200
