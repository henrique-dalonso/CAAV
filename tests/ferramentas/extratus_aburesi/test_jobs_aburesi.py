from datetime import datetime, timedelta

from sqlmodel import delete

import pytest

from app.ferramentas.extratus_aburesi.db.jobs import (
    contar_jobs_manuais_do_usuario,
    contar_relatorios_motor_novos,
    contar_relatorios_novos_do_usuario,
    listar_jobs_manuais,
    listar_jobs_motor,
    listar_relatorios_manuais_nao_notificados_do_usuario,
    marcar_notificacao_resolvida,
    registrar_erro,
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


# --- Badges "+N" (Henrique, 2026-08-13) — ver comentário equivalente em
# tests/ferramentas/extratus/test_jobs.py, mesma lógica.

def test_contar_relatorios_novos_do_usuario_separa_sucesso_e_revisao(limpar_jobs_criados):
    desde = datetime.now() - timedelta(seconds=1)

    job_sucesso = registrar_processado(
        arquivo_pdf="teste_badge_sucesso_aburesi.pdf",
        processo="0000000-00.2026.8.00.0027",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_revisao = registrar_processado(
        arquivo_pdf="teste_badge_revisao_aburesi.pdf",
        processo="0000000-00.2026.8.00.0028",
        relatorio_path=None,
        destino_pdf=None,
        confianca="media",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.extend([job_sucesso.id, job_revisao.id])

    novos = contar_relatorios_novos_do_usuario(USUARIO_TESTE_A, desde)

    assert novos == {"sucesso": 1, "revisao": 1}


def test_contar_relatorios_novos_do_usuario_ignora_erro_e_outro_usuario(limpar_jobs_criados):
    desde = datetime.now() - timedelta(seconds=1)

    job_erro = registrar_erro(
        arquivo_pdf="teste_badge_erro_aburesi.pdf",
        processo="0000000-00.2026.8.00.0030",
        tipo_erro="erro_ia",
        erro_mensagem="falha simulada",
        usuario_id=USUARIO_TESTE_A,
    )
    job_outro_usuario = registrar_processado(
        arquivo_pdf="teste_badge_outro_usuario_aburesi.pdf",
        processo="0000000-00.2026.8.00.0031",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_B,
    )
    limpar_jobs_criados.extend([job_erro.id, job_outro_usuario.id])

    novos = contar_relatorios_novos_do_usuario(USUARIO_TESTE_A, desde)

    assert novos == {"sucesso": 0, "revisao": 0}


def test_contar_relatorios_motor_novos_conta_so_usuario_id_none(limpar_jobs_criados):
    desde = datetime.now() - timedelta(seconds=1)
    antes = contar_relatorios_motor_novos(desde)

    job_motor_sucesso = registrar_processado(
        arquivo_pdf="teste_badge_motor_sucesso_aburesi.pdf",
        processo="0000000-00.2026.8.00.0032",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    job_motor_revisao = registrar_processado(
        arquivo_pdf="teste_badge_motor_revisao_aburesi.pdf",
        processo="0000000-00.2026.8.00.0033",
        relatorio_path=None,
        destino_pdf=None,
        confianca="revisao",
        usuario_id=None,
    )
    limpar_jobs_criados.extend([job_motor_sucesso.id, job_motor_revisao.id])

    depois = contar_relatorios_motor_novos(desde)

    assert depois["sucesso"] == antes["sucesso"] + 1
    assert depois["revisao"] == antes["revisao"] + 1


def test_listar_relatorios_manuais_nao_notificados_do_usuario_traz_sucesso_e_revisao(limpar_jobs_criados):
    job_sucesso = registrar_processado(
        arquivo_pdf="teste_sino_minhas_sucesso_aburesi.pdf",
        processo="0000000-00.2026.8.00.0040",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_revisao = registrar_processado(
        arquivo_pdf="teste_sino_minhas_revisao_aburesi.pdf",
        processo="0000000-00.2026.8.00.0041",
        relatorio_path=None,
        destino_pdf=None,
        confianca="media",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.extend([job_sucesso.id, job_revisao.id])

    nomes = {job.arquivo_pdf for job in listar_relatorios_manuais_nao_notificados_do_usuario(USUARIO_TESTE_A)}

    assert "teste_sino_minhas_sucesso_aburesi.pdf" in nomes
    assert "teste_sino_minhas_revisao_aburesi.pdf" in nomes


def test_marcar_notificacao_resolvida_recusa_dono_errado(limpar_jobs_criados):
    job = registrar_processado(
        arquivo_pdf="teste_sino_minhas_dono_errado_aburesi.pdf",
        processo="0000000-00.2026.8.00.0044",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.append(job.id)

    assert marcar_notificacao_resolvida(job.id, USUARIO_TESTE_B) is False

    do_banco = listar_relatorios_manuais_nao_notificados_do_usuario(USUARIO_TESTE_A)
    assert any(j.id == job.id for j in do_banco)


def test_marcar_notificacao_resolvida_job_inexistente_nao_quebra():
    assert marcar_notificacao_resolvida(999999999, USUARIO_TESTE_A) is False
