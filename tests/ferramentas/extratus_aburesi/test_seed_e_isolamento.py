from sqlmodel import delete, select

from app.ferramentas.nucleo_relatorios.db.jobs import (
    listar_jobs_manuais,
    listar_jobs_robo,
    registrar_processado,
)
from app.ferramentas.nucleo_relatorios.db.models import Job
from app.plataforma.db.models import Ferramenta
from app.plataforma.db.session import obter_sessao


ARQUIVO_TESTE_ABURESI = "teste_isolamento_aburesi.pdf"
ARQUIVO_TESTE_RELATORIOS = "teste_isolamento_relatorios.pdf"

# ID negativo de propósito — não colide com usuário real, mesmo padrão de
# tests/ferramentas/extratus/test_jobs.py.
USUARIO_TESTE = -9099


def test_ferramenta_extratus_aburesi_registrada_com_dados_corretos():
    with obter_sessao() as sessao:
        ferramenta = sessao.exec(
            select(Ferramenta).where(Ferramenta.slug == "extratus-aburesi")
        ).first()

    assert ferramenta is not None
    assert ferramenta.nome == "Extratus - Aburesi"
    assert ferramenta.url == "/extratus-aburesi/fila-robo"


def test_job_de_um_modulo_nao_aparece_no_outro():
    """Stage 1 (2026-09-08) uniu as tabelas de Relatórios e Aburesi num
    único `Job` compartilhado (nucleo_relatorios/db/models.py) — a
    isolação entre módulos deixou de ser "tabela física própria" (ver
    test_tabelas_de_job_sao_fisicamente_diferentes, removido) e passou a
    ser inteiramente pelo campo `ferramenta_slug`. Este teste prova que a
    função de listagem de cada tela (`listar_jobs_manuais`, chamada por
    web/routes/relatorios_manuais.py em cada módulo) só enxerga jobs do
    seu próprio `ferramenta_slug`, mesmo os dois vivendo lado a lado na
    mesma tabela física."""
    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.arquivo_pdf.in_([ARQUIVO_TESTE_ABURESI, ARQUIVO_TESTE_RELATORIOS])))
        sessao.commit()

    try:
        registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_ABURESI,
            processo="0000000-00.2026.8.00.0000",
            relatorio_path="relatorio_teste_aburesi.docx",
            destino_pdf="processados/" + ARQUIVO_TESTE_ABURESI,
            confianca="alta",
            usuario_id=USUARIO_TESTE,
            ferramenta_slug="extratus-aburesi",
        )
        registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_RELATORIOS,
            processo="0000000-00.2026.8.00.0001",
            relatorio_path="relatorio_teste_relatorios.docx",
            destino_pdf="processados/" + ARQUIVO_TESTE_RELATORIOS,
            confianca="alta",
            usuario_id=USUARIO_TESTE,
            ferramenta_slug="extratus-relatorios",
        )

        nomes_aburesi = {job.arquivo_pdf for job in listar_jobs_manuais(ferramenta_slug="extratus-aburesi")}
        nomes_relatorios = {job.arquivo_pdf for job in listar_jobs_manuais(ferramenta_slug="extratus-relatorios")}

        assert ARQUIVO_TESTE_ABURESI in nomes_aburesi
        assert ARQUIVO_TESTE_ABURESI not in nomes_relatorios

        assert ARQUIVO_TESTE_RELATORIOS in nomes_relatorios
        assert ARQUIVO_TESTE_RELATORIOS not in nomes_aburesi
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.arquivo_pdf.in_([ARQUIVO_TESTE_ABURESI, ARQUIVO_TESTE_RELATORIOS])))
            sessao.commit()


def test_jobs_do_robo_tambem_isolados_por_ferramenta_slug():
    """Mesma prova de isolamento acima, mas pra `listar_jobs_robo`
    (relatorios_robo.py) — a outra tela que lista `Job`, garantindo que a
    isolação por `ferramenta_slug` vale pras duas listagens, não só pra
    manual."""
    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.arquivo_pdf.in_([ARQUIVO_TESTE_ABURESI, ARQUIVO_TESTE_RELATORIOS])))
        sessao.commit()

    try:
        registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_ABURESI,
            processo="0000000-00.2026.8.00.0002",
            relatorio_path="relatorio_teste_aburesi_robo.docx",
            destino_pdf=None,
            confianca="alta",
            usuario_id=None,
            ferramenta_slug="extratus-aburesi",
        )
        registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_RELATORIOS,
            processo="0000000-00.2026.8.00.0003",
            relatorio_path="relatorio_teste_relatorios_robo.docx",
            destino_pdf=None,
            confianca="alta",
            usuario_id=None,
            ferramenta_slug="extratus-relatorios",
        )

        nomes_aburesi = {job.arquivo_pdf for job in listar_jobs_robo(ferramenta_slug="extratus-aburesi")}
        nomes_relatorios = {job.arquivo_pdf for job in listar_jobs_robo(ferramenta_slug="extratus-relatorios")}

        assert ARQUIVO_TESTE_ABURESI in nomes_aburesi
        assert ARQUIVO_TESTE_ABURESI not in nomes_relatorios

        assert ARQUIVO_TESTE_RELATORIOS in nomes_relatorios
        assert ARQUIVO_TESTE_RELATORIOS not in nomes_aburesi
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.arquivo_pdf.in_([ARQUIVO_TESTE_ABURESI, ARQUIVO_TESTE_RELATORIOS])))
            sessao.commit()
