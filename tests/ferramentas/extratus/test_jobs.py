import pytest
from sqlmodel import delete

from datetime import datetime, timedelta

from app.ferramentas.extratus.db.jobs import (
    contar_jobs_manuais_do_usuario,
    contar_relatorios_robo_novos,
    contar_relatorios_novos_do_usuario,
    excluir_job,
    listar_jobs_manuais,
    listar_jobs_robo,
    listar_jobs_robo_nao_notificados,
    listar_relatorios_manuais_nao_notificados_do_usuario,
    marcar_notificacao_resolvida,
    marcar_notificacao_resolvida_robo,
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


def test_somar_custo_por_usuario_agrupa_sem_usuario_como_robo_automatico(limpar_jobs_criados):
    antes = somar_custo_por_usuario()
    custo_antes_none = antes.get(None, 0.0)

    job = registrar_processado(
        arquivo_pdf="teste_custo_robo.pdf",
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


def test_listar_jobs_manuais_exclui_jobs_do_robo(limpar_jobs_criados):
    job_manual = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_manual.pdf",
        processo="0000000-00.2026.8.00.0020",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_robo = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_robo.pdf",
        processo="0000000-00.2026.8.00.0021",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.extend([job_manual.id, job_robo.id])

    nomes = {job.arquivo_pdf for job in listar_jobs_manuais(limite=1000)}

    assert "teste_relatorios_finalizados_manual.pdf" in nomes
    assert "teste_relatorios_finalizados_robo.pdf" not in nomes


def test_listar_jobs_robo_inclui_so_jobs_sem_usuario(limpar_jobs_criados):
    job_manual = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_manual2.pdf",
        processo="0000000-00.2026.8.00.0022",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_robo = registrar_processado(
        arquivo_pdf="teste_relatorios_finalizados_robo2.pdf",
        processo="0000000-00.2026.8.00.0023",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.extend([job_manual.id, job_robo.id])

    nomes = {job.arquivo_pdf for job in listar_jobs_robo(limite=1000)}

    assert "teste_relatorios_finalizados_robo2.pdf" in nomes
    assert "teste_relatorios_finalizados_manual2.pdf" not in nomes


def test_contar_jobs_manuais_do_usuario_so_conta_do_proprio_usuario(limpar_jobs_criados):
    """Henrique, 2026-08-12: o número da aba "Seus Relatórios" precisa
    contar só o que o PRÓPRIO usuário solicitou, não o total do
    escritório (nem jobs do Robô, nem de outro colaborador)."""
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
    job_robo = registrar_processado(
        arquivo_pdf="teste_contagem_robo.pdf",
        processo="0000000-00.2026.8.00.0025",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.extend([job_manual_a.id, job_manual_b.id, job_robo.id])

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


def test_contar_relatorios_robo_novos_conta_so_usuario_id_none(limpar_jobs_criados):
    desde = datetime.now() - timedelta(seconds=1)
    antes = contar_relatorios_robo_novos(desde)

    job_robo_sucesso = registrar_processado(
        arquivo_pdf="teste_badge_robo_sucesso.pdf",
        processo="0000000-00.2026.8.00.0032",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    job_robo_revisao = registrar_processado(
        arquivo_pdf="teste_badge_robo_revisao.pdf",
        processo="0000000-00.2026.8.00.0033",
        relatorio_path=None,
        destino_pdf=None,
        confianca="revisao",
        usuario_id=None,
    )
    job_manual = registrar_processado(
        arquivo_pdf="teste_badge_robo_nao_conta_manual.pdf",
        processo="0000000-00.2026.8.00.0034",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.extend([job_robo_sucesso.id, job_robo_revisao.id, job_manual.id])

    depois = contar_relatorios_robo_novos(desde)

    assert depois["sucesso"] == antes["sucesso"] + 1
    assert depois["revisao"] == antes["revisao"] + 1


def test_listar_relatorios_manuais_nao_notificados_do_usuario_traz_sucesso_e_revisao(limpar_jobs_criados):
    job_sucesso = registrar_processado(
        arquivo_pdf="teste_sino_minhas_sucesso.pdf",
        processo="0000000-00.2026.8.00.0040",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_revisao = registrar_processado(
        arquivo_pdf="teste_sino_minhas_revisao.pdf",
        processo="0000000-00.2026.8.00.0041",
        relatorio_path=None,
        destino_pdf=None,
        confianca="media",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.extend([job_sucesso.id, job_revisao.id])

    nomes = {job.arquivo_pdf for job in listar_relatorios_manuais_nao_notificados_do_usuario(USUARIO_TESTE_A)}

    assert "teste_sino_minhas_sucesso.pdf" in nomes
    assert "teste_sino_minhas_revisao.pdf" in nomes


def test_listar_relatorios_manuais_nao_notificados_ignora_ja_resolvido_erro_e_outro_usuario(limpar_jobs_criados):
    job_ja_resolvido = registrar_processado(
        arquivo_pdf="teste_sino_minhas_ja_resolvido.pdf",
        processo="0000000-00.2026.8.00.0042",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    job_erro = registrar_erro(
        arquivo_pdf="teste_sino_minhas_erro.pdf",
        processo=None,
        tipo_erro="erro_ia",
        erro_mensagem="falha simulada",
        usuario_id=USUARIO_TESTE_A,
    )
    job_outro_usuario = registrar_processado(
        arquivo_pdf="teste_sino_minhas_outro_usuario.pdf",
        processo="0000000-00.2026.8.00.0043",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_B,
    )
    limpar_jobs_criados.extend([job_ja_resolvido.id, job_erro.id, job_outro_usuario.id])

    assert marcar_notificacao_resolvida(job_ja_resolvido.id, USUARIO_TESTE_A) is True

    nomes = {job.arquivo_pdf for job in listar_relatorios_manuais_nao_notificados_do_usuario(USUARIO_TESTE_A)}

    assert "teste_sino_minhas_ja_resolvido.pdf" not in nomes
    assert "teste_sino_minhas_erro.pdf" not in nomes
    assert "teste_sino_minhas_outro_usuario.pdf" not in nomes


def test_marcar_notificacao_resolvida_recusa_dono_errado(limpar_jobs_criados):
    job = registrar_processado(
        arquivo_pdf="teste_sino_minhas_dono_errado.pdf",
        processo="0000000-00.2026.8.00.0044",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.append(job.id)

    assert marcar_notificacao_resolvida(job.id, USUARIO_TESTE_B) is False

    do_banco = listar_relatorios_manuais_nao_notificados_do_usuario(USUARIO_TESTE_A)
    assert any(j.id == job.id for j in do_banco)  # não foi marcado


def test_marcar_notificacao_resolvida_job_inexistente_nao_quebra():
    assert marcar_notificacao_resolvida(999999999, USUARIO_TESTE_A) is False


# --- Robô virou notificação plena (Henrique, diretoria, 2026-08-19) —
# não só erro, também sucesso e revisão, sem dono. ---

def test_listar_jobs_robo_nao_notificados_traz_sucesso_revisao_e_erro(limpar_jobs_criados):
    job_sucesso = registrar_processado(
        arquivo_pdf="teste_ferramentas_robo_sucesso.pdf",
        processo="0000000-00.2026.8.00.0060",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    job_revisao = registrar_processado(
        arquivo_pdf="teste_ferramentas_robo_revisao.pdf",
        processo="0000000-00.2026.8.00.0061",
        relatorio_path=None,
        destino_pdf=None,
        confianca="media",
        usuario_id=None,
    )
    job_erro = registrar_erro(
        arquivo_pdf="teste_ferramentas_robo_erro.pdf",
        processo=None,
        tipo_erro="erro_ia",
        erro_mensagem="falha simulada",
        usuario_id=None,
    )
    limpar_jobs_criados.extend([job_sucesso.id, job_revisao.id, job_erro.id])

    nomes = {job.arquivo_pdf for job in listar_jobs_robo_nao_notificados()}

    assert "teste_ferramentas_robo_sucesso.pdf" in nomes
    assert "teste_ferramentas_robo_revisao.pdf" in nomes
    assert "teste_ferramentas_robo_erro.pdf" in nomes


def test_listar_jobs_robo_nao_notificados_ignora_ja_resolvido_e_job_com_dono(limpar_jobs_criados):
    job_robo_resolvido = registrar_processado(
        arquivo_pdf="teste_ferramentas_robo_ja_resolvido.pdf",
        processo="0000000-00.2026.8.00.0062",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    job_manual = registrar_processado(
        arquivo_pdf="teste_ferramentas_robo_com_dono.pdf",
        processo="0000000-00.2026.8.00.0063",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.extend([job_robo_resolvido.id, job_manual.id])

    assert marcar_notificacao_resolvida_robo(job_robo_resolvido.id) is True

    nomes = {job.arquivo_pdf for job in listar_jobs_robo_nao_notificados()}

    assert "teste_ferramentas_robo_ja_resolvido.pdf" not in nomes
    assert "teste_ferramentas_robo_com_dono.pdf" not in nomes


def test_marcar_notificacao_resolvida_robo_recusa_job_com_dono(limpar_jobs_criados):
    job = registrar_processado(
        arquivo_pdf="teste_ferramentas_robo_recusa_dono.pdf",
        processo="0000000-00.2026.8.00.0064",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.append(job.id)

    assert marcar_notificacao_resolvida_robo(job.id) is False


def test_marcar_notificacao_resolvida_robo_job_inexistente_nao_quebra():
    assert marcar_notificacao_resolvida_robo(999999999) is False


def test_excluir_job_apaga_arquivos_fisicos_e_a_linha(tmp_path, limpar_jobs_criados):
    relatorio = tmp_path / "relatorio_teste_excluir.docx"
    relatorio.write_text("conteudo")
    pdf_origem = tmp_path / "pdf_origem_teste_excluir.pdf"
    pdf_origem.write_text("conteudo")

    job = registrar_processado(
        arquivo_pdf="teste_excluir_job.pdf",
        processo="0000000-00.2026.8.00.0910",
        relatorio_path=str(relatorio),
        destino_pdf=str(pdf_origem),
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.append(job.id)

    assert excluir_job(job.id) is True
    assert not relatorio.exists()
    assert not pdf_origem.exists()

    with obter_sessao() as sessao:
        assert sessao.get(Job, job.id) is None


def test_excluir_job_sem_arquivo_fisico_nao_quebra(limpar_jobs_criados):
    """job.relatorio_path/destino_pdf apontando pra um arquivo que já não
    existe mais (ex: alguém já mexeu na pasta manualmente) não pode
    derrubar a exclusão — só ignora e segue apagando a linha."""
    job = registrar_processado(
        arquivo_pdf="teste_excluir_job_sem_arquivo.pdf",
        processo="0000000-00.2026.8.00.0911",
        relatorio_path="C:/caminho/que/nao/existe/relatorio.docx",
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE_A,
    )
    limpar_jobs_criados.append(job.id)

    assert excluir_job(job.id) is True

    with obter_sessao() as sessao:
        assert sessao.get(Job, job.id) is None


def test_excluir_job_inexistente_devolve_false():
    assert excluir_job(999999999) is False
