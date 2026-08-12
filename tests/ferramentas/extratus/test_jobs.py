import pytest
from sqlmodel import delete

from datetime import datetime, timedelta

from app.ferramentas.extratus.db.jobs import (
    contar_jobs_manuais_do_usuario,
    contar_relatorios_motor_novos,
    contar_relatorios_novos_do_usuario,
    listar_jobs_manuais,
    listar_jobs_motor,
    registrar_erro,
    registrar_processado,
    somar_custo_por_usuario,
)
from app.ferramentas.extratus.db.models import Job
from app.plataforma.db.session import obter_sessao


# IDs negativos de propósito — usuario_id real nunca é negativo (é
# autoincremento a partir de 1), então não colidem com dado de produção.
USUARIO_TESTE_A = -9001
USUARIO_TESTE_B = -9002


@pytest.fixture
def limpar_jobs_criados():
    """Cada teste registra os IDs dos jobs que criou nessa lista — a
    limpeza no final apaga só esses IDs exatos, nunca em massa (o banco
    compartilhado tem dado real de produção junto)."""
    ids_criados = []

    yield ids_criados

    if ids_criados:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.id.in_(ids_criados)))
            sessao.commit()


def test_somar_custo_por_usuario_agrega_por_usuario(limpar_jobs_criados):
    antes = somar_custo_por_usuario()
    custo_antes_a = antes.get(USUARIO_TESTE_A, 0.0)

    job1 = registrar_processado(
        arquivo_pdf="teste_custo_a_1.pdf",
        processo="0000000-00.2026.8.00.0000",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        uso_ia={"modelo": "claude-sonnet-5", "custo_estimado_usd": 0.10},
        usuario_id=USUARIO_TESTE_A,
    )
    job2 = registrar_processado(
        arquivo_pdf="teste_custo_a_2.pdf",
        processo="0000000-00.2026.8.00.0001",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        uso_ia={"modelo": "claude-sonnet-5", "custo_estimado_usd": 0.25},
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.extend([job1.id, job2.id])

    depois = somar_custo_por_usuario()

    assert depois[USUARIO_TESTE_A] == pytest.approx(custo_antes_a + 0.35)


def test_somar_custo_por_usuario_agrupa_sem_usuario_como_motor_automatico(limpar_jobs_criados):
    antes = somar_custo_por_usuario()
    custo_antes_none = antes.get(None, 0.0)

    job = registrar_processado(
        arquivo_pdf="teste_custo_motor.pdf",
        processo="0000000-00.2026.8.00.0002",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        uso_ia={"modelo": "claude-sonnet-5", "custo_estimado_usd": 0.42},
        usuario_id=None,
    )
    limpar_jobs_criados.append(job.id)

    depois = somar_custo_por_usuario()

    assert depois[None] == pytest.approx(custo_antes_none + 0.42)


def test_somar_custo_por_usuario_ignora_jobs_sem_custo(limpar_jobs_criados):
    antes = somar_custo_por_usuario()
    custo_antes_b = antes.get(USUARIO_TESTE_B, 0.0)

    # job sem uso_ia registrado não deve contribuir com custo nenhum.
    job_sem_uso_ia = registrar_processado(
        arquivo_pdf="teste_custo_sem_uso_ia.pdf",
        processo="0000000-00.2026.8.00.0003",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_B,
    )
    # erro também não tem custo associado.
    job_erro = registrar_erro(
        arquivo_pdf="teste_custo_erro.pdf",
        processo=None,
        tipo_erro="erro_pdf",
        erro_mensagem="falha de teste",
        usuario_id=USUARIO_TESTE_B,
    )
    limpar_jobs_criados.extend([job_sem_uso_ia.id, job_erro.id])

    depois = somar_custo_por_usuario()

    assert depois.get(USUARIO_TESTE_B, 0.0) == pytest.approx(custo_antes_b)


def test_listar_jobs_manuais_exclui_jobs_do_motor(limpar_jobs_criados):
    job_manual = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_manual.pdf",
        processo="0000000-00.2026.8.00.0020",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_motor = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_motor.pdf",
        processo="0000000-00.2026.8.00.0021",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.extend([job_manual.id, job_motor.id])

    nomes = {job.arquivo_pdf for job in listar_jobs_manuais(limite=1000)}

    assert "teste_relatorios_finalizados_manual.pdf" in nomes
    assert "teste_relatorios_finalizados_motor.pdf" not in nomes


def test_listar_jobs_motor_inclui_so_jobs_sem_usuario(limpar_jobs_criados):
    job_manual = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_manual2.pdf",
        processo="0000000-00.2026.8.00.0022",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_motor = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_motor2.pdf",
        processo="0000000-00.2026.8.00.0023",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.extend([job_manual.id, job_motor.id])

    nomes = {job.arquivo_pdf for job in listar_jobs_motor(limite=1000)}

    assert "teste_relatorios_finalizados_motor2.pdf" in nomes
    assert "teste_relatorios_finalizados_manual2.pdf" not in nomes


def test_contar_jobs_manuais_do_usuario_so_conta_do_proprio_usuario(limpar_jobs_criados):
    """Henrique, 2026-08-12: o número da aba "Seus Relatórios" precisa
    contar só o que o PRÓPRIO usuário solicitou, não o total do
    escritório (nem jobs do Motor, nem de outro colaborador)."""
    antes_a = contar_jobs_manuais_do_usuario(USUARIO_TESTE_A)

    job_manual_a = registrar_processado(
        arquivo_pdf="teste_contagem_manual.pdf",
        processo="0000000-00.2026.8.00.0024",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_manual_b = registrar_processado(
        arquivo_pdf="teste_contagem_manual_outro_usuario.pdf",
        processo="0000000-00.2026.8.00.0026",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_B,
    )
    job_motor = registrar_processado(
        arquivo_pdf="teste_contagem_motor.pdf",
        processo="0000000-00.2026.8.00.0025",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.extend([job_manual_a.id, job_manual_b.id, job_motor.id])

    depois_a = contar_jobs_manuais_do_usuario(USUARIO_TESTE_A)

    assert depois_a == antes_a + 1


def test_contar_relatorios_novos_do_usuario_separa_sucesso_e_revisao(limpar_jobs_criados):
    desde = datetime.now() - timedelta(seconds=1)

    job_sucesso = registrar_processado(
        arquivo_pdf="teste_badge_sucesso.pdf",
        processo="0000000-00.2026.8.00.0027",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_revisao = registrar_processado(
        arquivo_pdf="teste_badge_revisao.pdf",
        processo="0000000-00.2026.8.00.0028",
        relatorio_path=None,
        destino_pdf=None,
        confianca="media",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.extend([job_sucesso.id, job_revisao.id])

    novos = contar_relatorios_novos_do_usuario(USUARIO_TESTE_A, desde)

    assert novos == {"sucesso": 1, "revisao": 1}


def test_contar_relatorios_novos_do_usuario_ignora_o_que_e_de_antes_do_desde(limpar_jobs_criados):
    job = registrar_processado(
        arquivo_pdf="teste_badge_antigo.pdf",
        processo="0000000-00.2026.8.00.0029",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.append(job.id)

    desde = datetime.now() + timedelta(seconds=1)  # "no futuro" -> nada é novo
    novos = contar_relatorios_novos_do_usuario(USUARIO_TESTE_A, desde)

    assert novos == {"sucesso": 0, "revisao": 0}


def test_contar_relatorios_novos_do_usuario_ignora_erro_e_outro_usuario(limpar_jobs_criados):
    desde = datetime.now() - timedelta(seconds=1)

    job_erro = registrar_erro(
        arquivo_pdf="teste_badge_erro.pdf",
        processo="0000000-00.2026.8.00.0030",
        tipo_erro="erro_ia",
        erro_mensagem="falha simulada",
        usuario_id=USUARIO_TESTE_A,
    )
    job_outro_usuario = registrar_processado(
        arquivo_pdf="teste_badge_outro_usuario.pdf",
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
        arquivo_pdf="teste_badge_motor_sucesso.pdf",
        processo="0000000-00.2026.8.00.0032",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    job_motor_revisao = registrar_processado(
        arquivo_pdf="teste_badge_motor_revisao.pdf",
        processo="0000000-00.2026.8.00.0033",
        relatorio_path=None,
        destino_pdf=None,
        confianca="revisao",
        usuario_id=None,
    )
    job_manual = registrar_processado(
        arquivo_pdf="teste_badge_motor_nao_conta_manual.pdf",
        processo="0000000-00.2026.8.00.0034",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.extend([job_motor_sucesso.id, job_motor_revisao.id, job_manual.id])

    depois = contar_relatorios_motor_novos(desde)

    assert depois["sucesso"] == antes["sucesso"] + 1
    assert depois["revisao"] == antes["revisao"] + 1
