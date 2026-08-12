import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete

from app.ferramentas.extratus.db.jobs import registrar_processado
from app.ferramentas.extratus.db.models import Job
from app.plataforma.db.models import Usuario
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_TESTE = "teste_relatorios_prontos_busca"
SENHA = "senhaTeste123"

# ID negativo de propósito — não colide com usuário real, mesmo padrão de
# tests/ferramentas/extratus/test_jobs.py.
USUARIO_TESTE = -9304


@pytest.fixture
def cliente_logado():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Relatórios Prontos Busca", nome_usuario=NOME_USUARIO_TESTE,
        email="teste_relatorios_prontos_busca@example.com", senha=SENHA, eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA})

    yield cliente

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


@pytest.fixture
def job_manual_de_teste():
    job = registrar_processado(
        arquivo_pdf="teste_relatorios_prontos_busca.pdf",
        processo="0000000-00.2026.8.00.0900",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE,
    )

    yield job

    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.id == job.id))
        sessao.commit()


def test_pagina_sem_processo_na_query_nao_preenche_busca(cliente_logado, job_manual_de_teste):
    resp = cliente_logado.get("/extratus/relatorios")

    assert resp.status_code == 200
    assert 'data-processo-inicial=""' in resp.text


def test_pagina_com_processo_na_query_preenche_busca_inicial(cliente_logado, job_manual_de_teste):
    resp = cliente_logado.get("/extratus/relatorios?processo=0000000-00.2026.8.00.0900")

    assert resp.status_code == 200
    assert 'data-processo-inicial="0000000-00.2026.8.00.0900"' in resp.text
    assert 'data-processo="0000000-00.2026.8.00.0900"' in resp.text
