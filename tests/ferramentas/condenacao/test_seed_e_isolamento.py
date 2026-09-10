from sqlmodel import delete, select

from app.ferramentas.nucleo_relatorios.db.jobs import (
    listar_jobs_manuais,
    listar_jobs_robo,
    registrar_processado,
)
from app.ferramentas.nucleo_relatorios.db.models import Job
from app.ferramentas.nucleo_relatorios.tipos import REGISTRO_TIPOS
from app.plataforma.db.models import Ferramenta
from app.plataforma.db.session import obter_sessao


ARQUIVO_TESTE_CONDENACAO = "teste_isolamento_condenacao.pdf"
ARQUIVO_TESTE_RELATORIOS = "teste_isolamento_relatorios_vs_condenacao.pdf"

# ID negativo de propósito — não colide com usuário real, mesmo padrão de
# tests/ferramentas/emenda/test_seed_e_isolamento.py.
USUARIO_TESTE = -9198


def test_ferramenta_condenacao_registrada_com_dados_corretos():
    with obter_sessao() as sessao:
        ferramenta = sessao.exec(
            select(Ferramenta).where(Ferramenta.slug == "condenacao")
        ).first()

    assert ferramenta is not None
    assert ferramenta.nome == "Extratus - Condenação"
    assert ferramenta.url == "/condenacao/fila-robo"
    assert ferramenta.suporta_fila_robo is True
    # Cor própria (âmbar) — não deve ficar sem identidade (None cairia no
    # azul padrão da plataforma, ver seed.py::_SEM_COR_PROPRIA).
    assert ferramenta.cor_acento == "#d97706"


def test_tipo_condenacao_registrado_no_motor_compartilhado():
    """Ver nucleo_relatorios/tipos.py — "condenacao" precisa existir ao
    lado de "bancario"/"emenda" sem substituir nenhum dos dois."""
    assert "bancario" in REGISTRO_TIPOS
    assert "emenda" in REGISTRO_TIPOS
    assert "condenacao" in REGISTRO_TIPOS

    tipo_condenacao = REGISTRO_TIPOS["condenacao"]
    assert tipo_condenacao.chave == "condenacao"
    assert tipo_condenacao.pos_processar is not None
    assert tipo_condenacao.template_docx_path.name == "condenacao.docx"


def test_job_de_condenacao_nao_aparece_em_relatorios_e_vice_versa():
    """Mesma prova de isolamento por `ferramenta_slug` já usada por
    extratus/aburesi/emenda — Condenação entra na MESMA tabela `Job`
    compartilhada (motor único), então a isolação inteira depende desse
    filtro nunca falhar silenciosamente."""
    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.arquivo_pdf.in_([ARQUIVO_TESTE_CONDENACAO, ARQUIVO_TESTE_RELATORIOS])))
        sessao.commit()

    try:
        registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_CONDENACAO,
            processo="0000000-00.2026.8.00.0900",
            relatorio_path="relatorio_teste_condenacao.docx",
            destino_pdf="processados/" + ARQUIVO_TESTE_CONDENACAO,
            confianca="alta",
            usuario_id=USUARIO_TESTE,
            ferramenta_slug="condenacao",
            tipo_relatorio="condenacao",
        )
        registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_RELATORIOS,
            processo="0000000-00.2026.8.00.0901",
            relatorio_path="relatorio_teste_relatorios_vs_condenacao.docx",
            destino_pdf="processados/" + ARQUIVO_TESTE_RELATORIOS,
            confianca="alta",
            usuario_id=USUARIO_TESTE,
            ferramenta_slug="extratus-relatorios",
        )

        nomes_condenacao = {job.arquivo_pdf for job in listar_jobs_manuais(ferramenta_slug="condenacao")}
        nomes_relatorios = {job.arquivo_pdf for job in listar_jobs_manuais(ferramenta_slug="extratus-relatorios")}

        assert ARQUIVO_TESTE_CONDENACAO in nomes_condenacao
        assert ARQUIVO_TESTE_CONDENACAO not in nomes_relatorios

        assert ARQUIVO_TESTE_RELATORIOS in nomes_relatorios
        assert ARQUIVO_TESTE_RELATORIOS not in nomes_condenacao
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.arquivo_pdf.in_([ARQUIVO_TESTE_CONDENACAO, ARQUIVO_TESTE_RELATORIOS])))
            sessao.commit()


def test_jobs_de_condenacao_do_robo_tambem_isolados():
    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_CONDENACAO))
        sessao.commit()

    try:
        registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_CONDENACAO,
            processo="0000000-00.2026.8.00.0902",
            relatorio_path="relatorio_teste_condenacao_robo.docx",
            destino_pdf=None,
            confianca="alta",
            usuario_id=None,
            ferramenta_slug="condenacao",
            tipo_relatorio="condenacao",
        )

        nomes_condenacao = {job.arquivo_pdf for job in listar_jobs_robo(ferramenta_slug="condenacao")}
        nomes_relatorios = {job.arquivo_pdf for job in listar_jobs_robo(ferramenta_slug="extratus-relatorios")}

        assert ARQUIVO_TESTE_CONDENACAO in nomes_condenacao
        assert ARQUIVO_TESTE_CONDENACAO not in nomes_relatorios
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_CONDENACAO))
            sessao.commit()


def test_campos_extra_de_condenacao_sao_persistidos_no_job():
    """`registrar_processado(campos_extra=...)` — ver core/pipeline.py e
    db/jobs.py — precisa gravar as colunas condenacao_* de verdade, não
    só aceitar o parâmetro sem efeito."""
    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_CONDENACAO))
        sessao.commit()

    try:
        job = registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_CONDENACAO,
            processo="0000000-00.2026.8.00.0903",
            relatorio_path="relatorio_teste_condenacao_campos.docx",
            destino_pdf=None,
            confianca="alta",
            usuario_id=USUARIO_TESTE,
            ferramenta_slug="condenacao",
            tipo_relatorio="condenacao",
            campos_extra={
                "condenacao_recomendacao": "impugnar",
                "condenacao_valor_total_geral": 21163.18,
            },
        )

        with obter_sessao() as sessao:
            atualizado = sessao.get(Job, job.id)
            assert atualizado.condenacao_recomendacao == "impugnar"
            assert atualizado.condenacao_valor_total_geral == 21163.18
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_CONDENACAO))
            sessao.commit()


def test_job_bancario_sem_campos_extra_fica_com_colunas_condenacao_nulas():
    """Nenhuma linha "bancario" deve ganhar valor nenhum nas colunas
    novas — são exclusivas do tipo "condenacao" (ver docstring de Job em
    nucleo_relatorios/db/models.py)."""
    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_RELATORIOS))
        sessao.commit()

    try:
        job = registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_RELATORIOS,
            processo="0000000-00.2026.8.00.0904",
            relatorio_path=None,
            destino_pdf=None,
            confianca="alta",
            usuario_id=USUARIO_TESTE,
            ferramenta_slug="extratus-relatorios",
        )

        with obter_sessao() as sessao:
            atualizado = sessao.get(Job, job.id)
            assert atualizado.condenacao_recomendacao is None
            assert atualizado.condenacao_valor_total_geral is None
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_RELATORIOS))
            sessao.commit()
