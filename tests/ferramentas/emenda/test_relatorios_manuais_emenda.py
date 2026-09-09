import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.ferramentas.nucleo_relatorios.db.jobs import registrar_processado
from app.ferramentas.nucleo_relatorios.db.models import Job
from app.plataforma.db.models import Ferramenta, Usuario, UsuarioFerramenta
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_TESTE = "teste_relatorios_prontos_busca_emenda"
NOME_COLABORADOR_TESTE = "teste_relprontos_colaborador_emenda"
SENHA = "senhaTeste123"

# ID negativo de propósito — não colide com usuário real, mesmo padrão dos
# outros dois módulos no motor compartilhado.
USUARIO_TESTE = -9204
FERRAMENTA_SLUG = "emenda"


@pytest.fixture
def cliente_colaborador_nao_admin():
    with obter_sessao() as sessao:
        usuario_antigo = sessao.exec(select(Usuario).where(Usuario.nome_usuario == NOME_COLABORADOR_TESTE)).first()
        if usuario_antigo:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_antigo.id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_COLABORADOR_TESTE))
        sessao.commit()
        ferramenta_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == FERRAMENTA_SLUG)).first()

    criar_usuario(
        nome="Teste RelProntos Colaborador Não-Admin Emenda", nome_usuario=NOME_COLABORADOR_TESTE,
        email="teste_relprontos_colaborador_emenda@example.com", senha=SENHA, eh_admin=False,
        ferramenta_ids=[ferramenta_id],
        ferramentas_manual_ids=[ferramenta_id],
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
        nome="Teste Relatórios Prontos Busca Emenda", nome_usuario=NOME_USUARIO_TESTE,
        email="teste_relatorios_prontos_busca_emenda@example.com", senha=SENHA, eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA})

    yield cliente

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


def test_pagina_relatorios_emenda_carrega(cliente_logado):
    resp = cliente_logado.get("/emenda/relatorios-urgentes")
    assert resp.status_code == 200


def test_botao_excluir_so_aparece_pro_admin(cliente_colaborador_nao_admin):
    job = registrar_processado(
        arquivo_pdf="teste_botao_excluir_emenda.pdf",
        processo="0000000-00.2026.8.00.0920",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=USUARIO_TESTE,
        ferramenta_slug=FERRAMENTA_SLUG,
        tipo_relatorio="emenda",
    )

    try:
        resp = cliente_colaborador_nao_admin.get("/emenda/relatorios-urgentes")
        assert resp.status_code == 200
        assert "botao-excluir" not in resp.text
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.id == job.id))
            sessao.commit()


def test_excluir_relatorio_admin_apaga_de_verdade(cliente_logado):
    job = registrar_processado(
        arquivo_pdf="teste_excluir_relatorio_admin_emenda.pdf",
        processo="0000000-00.2026.8.00.0921",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=USUARIO_TESTE,
        ferramenta_slug=FERRAMENTA_SLUG,
        tipo_relatorio="emenda",
    )

    resp = cliente_logado.post(f"/emenda/relatorios-urgentes/{job.id}/excluir", follow_redirects=False)

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]

    with obter_sessao() as sessao:
        assert sessao.get(Job, job.id) is None


def test_prazo_fatal_aparece_na_listagem_quando_calculado(cliente_logado):
    """Comportamento genuinamente novo desta tarefa (não existe em
    Extratus/Aburesi, que não têm prazo calculado): a listagem de
    relatórios de Emenda precisa mostrar o prazo fatal já calculado,
    junto com o aviso de "VENCIDO" quando aplicável — ver
    web/templates/relatorios_manuais.html."""
    job_no_prazo = registrar_processado(
        arquivo_pdf="teste_prazo_no_prazo_emenda.pdf",
        processo="0000000-00.2026.8.00.0922",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=USUARIO_TESTE,
        ferramenta_slug=FERRAMENTA_SLUG,
        tipo_relatorio="emenda",
        campos_extra={
            "emenda_data_intimacao": "03/11/2026",
            "emenda_prazo_dias": 4,
            "emenda_dias_uteis": False,
            "emenda_prazo_calculado": "09/11/2026",
            "emenda_prazo_ja_expirado": False,
            "emenda_veiculo_terceiro": False,
        },
    )
    job_vencido = registrar_processado(
        arquivo_pdf="teste_prazo_vencido_emenda.pdf",
        processo="0000000-00.2026.8.00.0923",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=USUARIO_TESTE,
        ferramenta_slug=FERRAMENTA_SLUG,
        tipo_relatorio="emenda",
        campos_extra={
            "emenda_data_intimacao": "01/01/2020",
            "emenda_prazo_dias": 5,
            "emenda_dias_uteis": False,
            "emenda_prazo_calculado": "08/01/2020",
            "emenda_prazo_ja_expirado": True,
            "emenda_veiculo_terceiro": False,
        },
    )

    try:
        resp = cliente_logado.get("/emenda/relatorios-urgentes")

        assert resp.status_code == 200
        assert "Prazo fatal: 09/11/2026" in resp.text
        assert "Prazo VENCIDO: 08/01/2020" in resp.text
        assert "motivo-prazo-vencido" in resp.text
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.id.in_([job_no_prazo.id, job_vencido.id])))
            sessao.commit()


def test_prazo_fatal_nao_aparece_quando_nao_calculado(cliente_logado):
    job = registrar_processado(
        arquivo_pdf="teste_sem_prazo_emenda.pdf",
        processo="0000000-00.2026.8.00.0924",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=USUARIO_TESTE,
        ferramenta_slug=FERRAMENTA_SLUG,
        tipo_relatorio="emenda",
    )

    try:
        resp = cliente_logado.get("/emenda/relatorios-urgentes")
        assert resp.status_code == 200
        assert "Prazo fatal:" not in resp.text
        assert "Prazo VENCIDO:" not in resp.text
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.id == job.id))
            sessao.commit()


def test_ver_pdf_relatorio_job_inexistente_da_404(cliente_logado):
    resp = cliente_logado.get("/emenda/relatorios-urgentes/999999999/pdf")
    assert resp.status_code == 404
