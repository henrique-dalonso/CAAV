from sqlmodel import delete

import pytest

from app.ferramentas.extratus_aburesi.db.jobs import (
    contar_jobs_manuais_do_usuario,
    listar_jobs_manuais,
    listar_jobs_motor,
    registrar_processado,
)
from app.ferramentas.extratus_aburesi.db.models import Job
from app.plataforma.db.session import obter_sessao


# Ver comentário equivalente em tests/ferramentas/extratus/test_jobs.py
# (Extratus - Relatórios) — mesma lógica.
USUARIO_TESTE_A = -9001
USUARIO_TESTE_B = -9002


@pytest.fixture
def limpar_jobs_criados():
    ids_criados = []

    yield ids_criados

    if ids_criados:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.id.in_(ids_criados)))
            sessao.commit()


def test_listar_jobs_manuais_exclui_jobs_do_motor(limpar_jobs_criados):
    job_manual = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_manual_aburesi.pdf",
        processo="0000000-00.2026.8.00.0030",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_motor = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_motor_aburesi.pdf",
        processo="0000000-00.2026.8.00.0031",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.extend([job_manual.id, job_motor.id])

    nomes = {job.arquivo_pdf for job in listar_jobs_manuais(limite=1000)}

    assert "teste_relatorios_finalizados_manual_aburesi.pdf" in nomes
    assert "teste_relatorios_finalizados_motor_aburesi.pdf" not in nomes


def test_listar_jobs_motor_inclui_so_jobs_sem_usuario(limpar_jobs_criados):
    job_manual = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_manual2_aburesi.pdf",
        processo="0000000-00.2026.8.00.0032",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_motor = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_motor2_aburesi.pdf",
        processo="0000000-00.2026.8.00.0033",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.extend([job_manual.id, job_motor.id])

    nomes = {job.arquivo_pdf for job in listar_jobs_motor(limite=1000)}

    assert "teste_relatorios_finalizados_motor2_aburesi.pdf" in nomes
    assert "teste_relatorios_finalizados_manual2_aburesi.pdf" not in nomes


def test_contar_jobs_manuais_do_usuario_so_conta_do_proprio_usuario(limpar_jobs_criados):
    antes_a = contar_jobs_manuais_do_usuario(USUARIO_TESTE_A)

    job_manual_a = registrar_processado(
        arquivo_pdf="teste_contagem_manual_aburesi.pdf",
        processo="0000000-00.2026.8.00.0034",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_manual_b = registrar_processado(
        arquivo_pdf="teste_contagem_manual_outro_usuario_aburesi.pdf",
        processo="0000000-00.2026.8.00.0036",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_B,
    )
    job_motor = registrar_processado(
        arquivo_pdf="teste_contagem_motor_aburesi.pdf",
        processo="0000000-00.2026.8.00.0035",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.extend([job_manual_a.id, job_manual_b.id, job_motor.id])

    depois_a = contar_jobs_manuais_do_usuario(USUARIO_TESTE_A)

    assert depois_a == antes_a + 1
