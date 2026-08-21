from sqlmodel import delete, select

from app.ferramentas.extratus.db.jobs import listar_jobs as listar_jobs_relatorios
from app.ferramentas.extratus.db.models import Job as JobRelatorios
from app.ferramentas.extratus_aburesi.db.jobs import (
    listar_jobs as listar_jobs_aburesi,
    registrar_processado,
)
from app.ferramentas.extratus_aburesi.db.models import Job as JobAburesi
from app.plataforma.db.models import Ferramenta
from app.plataforma.db.session import obter_sessao


ARQUIVO_TESTE = "teste_isolamento_aburesi.pdf"


def test_ferramenta_extratus_aburesi_registrada_com_dados_corretos():
    with obter_sessao() as sessao:
        ferramenta = sessao.exec(
            select(Ferramenta).where(Ferramenta.slug == "extratus-aburesi")
        ).first()

    assert ferramenta is not None
    assert ferramenta.nome == "Extratus - Aburesi"
    assert ferramenta.url == "/extratus-aburesi/fila"


def test_job_de_um_modulo_nao_aparece_no_outro():
    with obter_sessao() as sessao:
        sessao.exec(delete(JobAburesi).where(JobAburesi.arquivo_pdf == ARQUIVO_TESTE))
        sessao.commit()

    try:
        registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE,
            processo="0000000-00.2026.8.00.0000",
            relatorio_path="relatorio_teste.docx",
            destino_pdf="processados/" + ARQUIVO_TESTE,
            confianca="alta",
        )

        nomes_aburesi = {job.arquivo_pdf for job in listar_jobs_aburesi()}
        nomes_relatorios = {job.arquivo_pdf for job in listar_jobs_relatorios()}

        assert ARQUIVO_TESTE in nomes_aburesi
        assert ARQUIVO_TESTE not in nomes_relatorios
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(JobAburesi).where(JobAburesi.arquivo_pdf == ARQUIVO_TESTE))
            sessao.commit()


def test_tabelas_de_job_sao_fisicamente_diferentes():
    assert JobRelatorios.__tablename__ == "job"
    assert JobAburesi.__tablename__ == "job_aburesi"
