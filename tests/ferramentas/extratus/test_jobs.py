import pytest
from sqlmodel import delete

from app.ferramentas.extratus.db.jobs import (
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

    # job simulado (sem uso_ia) não deve contribuir com custo nenhum.
    job_simulado = registrar_processado(
        arquivo_pdf="teste_custo_simulado.pdf",
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
    limpar_jobs_criados.extend([job_simulado.id, job_erro.id])

    depois = somar_custo_por_usuario()

    assert depois.get(USUARIO_TESTE_B, 0.0) == pytest.approx(custo_antes_b)
