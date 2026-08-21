import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.ferramentas.extratus.db.jobs import registrar_processado
from app.ferramentas.extratus.db.models import Job
from app.plataforma.db.models import Ferramenta, Usuario, UsuarioFerramenta
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import buscar_usuario_por_nome_usuario, criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_TESTE = "teste_relatorios_prontos_busca"
NOME_COLABORADOR_TESTE = "teste_relatorios_prontos_colaborador"
SENHA = "senhaTeste123"

# ID negativo de propósito — não colide com usuário real, mesmo padrão de
# tests/ferramentas/extratus/test_jobs.py.
USUARIO_TESTE = -9304


@pytest.fixture
def cliente_colaborador_nao_admin():
    """Colaborador comum (não-admin) com acesso à ferramenta — prova que
    excluir relatório é restrito a admin da plataforma, mesmo tendo
    acesso normal à tela de Relatórios."""
    with obter_sessao() as sessao:
        usuario_antigo = sessao.exec(
            select(Usuario).where(Usuario.nome_usuario == NOME_COLABORADOR_TESTE)
        ).first()
        if usuario_antigo:
            # Apaga o vínculo ANTES do usuário — sem isso, o vínculo fica
            # órfão e "ressurge" num usuário novo que recicle o mesmo id
            # (SQLite), quebrando um INSERT sem relação com este teste.
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_antigo.id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_COLABORADOR_TESTE))
        sessao.commit()
        extratus_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "extratus")).first()

    criar_usuario(
        nome="Teste Relatórios Colaborador Não-Admin", nome_usuario=NOME_COLABORADOR_TESTE,
        email="teste_relatorios_prontos_colaborador@example.com", senha=SENHA, eh_admin=False,
        ferramenta_ids=[extratus_id],
        # acesso_manual concedido de propósito: precisa passar pelo gate
        # do router (exigir_acesso_manual) pra provar que quem trava a
        # exclusão de verdade é o exigir_admin da rota, não esse gate.
        ferramentas_manual_ids=[extratus_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_COLABORADOR_TESTE, "senha": SENHA})

    yield cliente

    with obter_sessao() as sessao:
        usuario = sessao.exec(select(Usuario).where(Usuario.nome_usuario == NOME_COLABORADOR_TESTE)).first()
        if usuario:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario.id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_COLABORADOR_TESTE))
        sessao.commit()


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


def test_botao_marcar_revisado_aparece_so_pro_dono_em_revisao(cliente_logado):
    usuario = buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE)
    job_proprio_revisao = registrar_processado(
        arquivo_pdf="teste_relatorios_prontos_botao_revisado.pdf",
        processo="0000000-00.2026.8.00.0903",
        relatorio_path=None, destino_pdf=None, confianca="media",
        usuario_id=usuario.id,
    )
    job_outro_revisao = registrar_processado(
        arquivo_pdf="teste_relatorios_prontos_botao_revisado_outro.pdf",
        processo="0000000-00.2026.8.00.0904",
        relatorio_path=None, destino_pdf=None, confianca="media",
        usuario_id=USUARIO_TESTE,
    )

    resp = cliente_logado.get("/extratus/relatorios")

    assert resp.status_code == 200
    assert f'data-job-id="{job_proprio_revisao.id}"' in resp.text
    assert f'data-job-id="{job_outro_revisao.id}"' not in resp.text

    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.id.in_([job_proprio_revisao.id, job_outro_revisao.id])))
        sessao.commit()


def test_excluir_relatorio_admin_apaga_de_verdade(cliente_logado):
    job = registrar_processado(
        arquivo_pdf="teste_excluir_relatorio_admin.pdf",
        processo="0000000-00.2026.8.00.0912",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=USUARIO_TESTE,
    )

    resp = cliente_logado.post(f"/extratus/relatorios/{job.id}/excluir", follow_redirects=False)

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]

    with obter_sessao() as sessao:
        assert sessao.get(Job, job.id) is None


def test_excluir_relatorio_inexistente_redireciona_com_erro(cliente_logado):
    resp = cliente_logado.post("/extratus/relatorios/999999999/excluir", follow_redirects=False)

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]


def test_excluir_relatorio_recusa_nao_admin(cliente_colaborador_nao_admin):
    job = registrar_processado(
        arquivo_pdf="teste_excluir_relatorio_nao_admin.pdf",
        processo="0000000-00.2026.8.00.0913",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=USUARIO_TESTE,
    )

    resp = cliente_colaborador_nao_admin.post(f"/extratus/relatorios/{job.id}/excluir")

    assert resp.status_code == 403

    with obter_sessao() as sessao:
        assert sessao.get(Job, job.id) is not None
        sessao.exec(delete(Job).where(Job.id == job.id))
        sessao.commit()


def test_botao_excluir_so_aparece_pro_admin(cliente_colaborador_nao_admin, job_manual_de_teste):
    resp = cliente_colaborador_nao_admin.get("/extratus/relatorios")

    assert resp.status_code == 200
    assert "botao-excluir" not in resp.text


def test_marcar_notificacao_resolvida_route_funciona_pro_dono(cliente_logado):
    usuario = buscar_usuario_por_nome_usuario(NOME_USUARIO_TESTE)
    job = registrar_processado(
        arquivo_pdf="teste_relatorios_prontos_marcar_resolvido.pdf",
        processo="0000000-00.2026.8.00.0905",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=usuario.id,
    )

    resp = cliente_logado.post(f"/extratus/relatorios/{job.id}/marcar-notificacao-resolvida")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    with obter_sessao() as sessao:
        atualizado = sessao.get(Job, job.id)
        assert atualizado.notificacao_resolvida is True
        sessao.exec(delete(Job).where(Job.id == job.id))
        sessao.commit()


def test_marcar_notificacao_resolvida_route_404_pra_job_de_outro_usuario(cliente_logado):
    job = registrar_processado(
        arquivo_pdf="teste_relatorios_prontos_marcar_resolvido_outro.pdf",
        processo="0000000-00.2026.8.00.0906",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=USUARIO_TESTE,
    )

    resp = cliente_logado.post(f"/extratus/relatorios/{job.id}/marcar-notificacao-resolvida")

    assert resp.status_code == 404

    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.id == job.id))
        sessao.commit()
