from types import SimpleNamespace
from unittest.mock import patch

from app.ferramentas.extratus_aburesi.core import pipeline_manual
from app.ferramentas.extratus_aburesi.db import triagem_manual as db_triagem

# ID negativo de propósito — não colide com usuário real (FK não é
# imposta pelo SQLite por padrão neste projeto, mesmo padrão de
# tests/ferramentas/extratus/test_jobs.py).
USUARIO_TESTE = -9301


def _criar_registro(nome="teste_pipeline_manual.pdf"):
    return db_triagem.criar_registro(nome, f"/tmp/{nome}", USUARIO_TESTE)


def _limpar(registro_id):
    db_triagem.descartar(registro_id)


def _job_falso(usuario_id):
    return SimpleNamespace(usuario_id=usuario_id)


def test_triar_e_processar_aprovado_dispara_geracao_sem_estado_intermediario():
    """Sinal verde da triagem já dispara a geração na mesma chamada —
    "a triagem que dá sinal verde" (Henrique, 2026-08-11)."""
    registro = _criar_registro()

    with patch.object(
        pipeline_manual, "analisar_pdf_isolado",
        return_value={"dominante": {"processo": "0000000-00.2026.8.00.0100"}, "confianca": {"nivel": "alta", "motivo": "ok"}},
    ), patch.object(
        pipeline_manual, "obter_relatorio_existente_para_processo", return_value=None,
    ), patch.object(
        pipeline_manual, "existe_conflito_de_processo", return_value=False,
    ), patch.object(
        pipeline_manual, "gerar_relatorio",
        return_value=({"parecer": "..."}, {"custo_estimado_usd": 0.10}),
    ), patch.object(
        pipeline_manual, "finalizar_processamento",
        return_value={"sucesso": True, "job_id": 4242},
    ) as finalizar_mock:
        pipeline_manual._triar_e_processar(registro.id)

    assert finalizar_mock.called

    atualizado = db_triagem.obter_registro(registro.id)
    assert atualizado.status == db_triagem.CONCLUIDO
    assert atualizado.job_id == 4242

    _limpar(registro.id)


def test_triar_e_processar_processo_nao_encontrado_nao_chama_ia():
    registro = _criar_registro("teste_pipeline_manual_sem_processo.pdf")

    with patch.object(
        pipeline_manual, "analisar_pdf_isolado",
        return_value={"dominante": None, "confianca": {"nivel": "revisao", "motivo": "nada encontrado"}},
    ), patch.object(pipeline_manual, "gerar_relatorio") as gerar_mock:
        pipeline_manual._triar_e_processar(registro.id)

    assert not gerar_mock.called

    atualizado = db_triagem.obter_registro(registro.id)
    assert atualizado.status == db_triagem.NAO_ENCONTRADO

    _limpar(registro.id)


def test_triar_e_processar_falha_ao_ler_pdf_vira_inconsistencia_nao_erro_definitivo():
    """Henrique, 2026-08-12: uma falha de LEITURA (PDF corrompido/
    ilegível) não pode virar Job "erro" na hora — trava em Pendentes
    (bolinha vermelha) até alguém decidir em Conferências, igual às
    outras inconsistências."""
    registro = _criar_registro("teste_pipeline_manual_falha_leitura.pdf")

    with patch.object(
        pipeline_manual, "analisar_pdf_isolado", side_effect=RuntimeError("pdf corrompido"),
    ), patch.object(pipeline_manual, "gerar_relatorio") as gerar_mock, patch.object(
        pipeline_manual, "tratar_erro",
    ) as tratar_erro_mock:
        pipeline_manual._triar_e_processar(registro.id)

    assert not gerar_mock.called
    assert not tratar_erro_mock.called  # nenhum Job "erro" criado na hora

    atualizado = db_triagem.obter_registro(registro.id)
    assert atualizado.status == db_triagem.FALHA_LEITURA
    assert atualizado.status in db_triagem.STATUS_INCONSISTENCIA
    assert atualizado.status in db_triagem.STATUS_EXIGE_PROCESSO_MANUAL

    _limpar(registro.id)


def test_triar_e_processar_duplicado_relatorio_do_motor_marca_origem_motor():
    """Henrique, 2026-08-12: "Ir ao relatório" estava sempre mandando pra
    "Seus Relatórios", mesmo quando o duplicado era do Motor (usuario_id
    None) — onde ele nunca aparece. origem_duplicado precisa refletir
    onde o relatório existente realmente mora."""
    registro = _criar_registro("teste_pipeline_manual_duplicado_motor.pdf")

    with patch.object(
        pipeline_manual, "analisar_pdf_isolado",
        return_value={"dominante": {"processo": "0000000-00.2026.8.00.0200"}, "confianca": {"nivel": "alta", "motivo": "ok"}},
    ), patch.object(
        pipeline_manual, "obter_relatorio_existente_para_processo", return_value=_job_falso(usuario_id=None),
    ), patch.object(pipeline_manual, "gerar_relatorio") as gerar_mock:
        pipeline_manual._triar_e_processar(registro.id)

    assert not gerar_mock.called

    atualizado = db_triagem.obter_registro(registro.id)
    assert atualizado.status == db_triagem.DUPLICADO_RELATORIO
    assert atualizado.origem_duplicado == "motor"

    _limpar(registro.id)


def test_triar_e_processar_duplicado_relatorio_manual_marca_origem_manual():
    registro = _criar_registro("teste_pipeline_manual_duplicado_manual.pdf")

    with patch.object(
        pipeline_manual, "analisar_pdf_isolado",
        return_value={"dominante": {"processo": "0000000-00.2026.8.00.0210"}, "confianca": {"nivel": "alta", "motivo": "ok"}},
    ), patch.object(
        pipeline_manual, "obter_relatorio_existente_para_processo", return_value=_job_falso(usuario_id=-1234),
    ), patch.object(pipeline_manual, "gerar_relatorio") as gerar_mock:
        pipeline_manual._triar_e_processar(registro.id)

    assert not gerar_mock.called

    atualizado = db_triagem.obter_registro(registro.id)
    assert atualizado.status == db_triagem.DUPLICADO_RELATORIO
    assert atualizado.origem_duplicado == "manual"

    _limpar(registro.id)


def test_triar_e_processar_duplicado_em_andamento_nao_chama_ia():
    registro = _criar_registro("teste_pipeline_manual_em_andamento.pdf")

    with patch.object(
        pipeline_manual, "analisar_pdf_isolado",
        return_value={"dominante": {"processo": "0000000-00.2026.8.00.0300"}, "confianca": {"nivel": "alta", "motivo": "ok"}},
    ), patch.object(
        pipeline_manual, "obter_relatorio_existente_para_processo", return_value=None,
    ), patch.object(
        pipeline_manual, "existe_conflito_de_processo", return_value=True,
    ), patch.object(pipeline_manual, "gerar_relatorio") as gerar_mock:
        pipeline_manual._triar_e_processar(registro.id)

    assert not gerar_mock.called

    atualizado = db_triagem.obter_registro(registro.id)
    assert atualizado.status == db_triagem.DUPLICADO_EM_ANDAMENTO

    _limpar(registro.id)


def test_triar_e_processar_falha_na_ia_marca_erro():
    registro = _criar_registro("teste_pipeline_manual_erro_ia.pdf")

    with patch.object(
        pipeline_manual, "analisar_pdf_isolado",
        return_value={"dominante": {"processo": "0000000-00.2026.8.00.0400"}, "confianca": {"nivel": "alta", "motivo": "ok"}},
    ), patch.object(
        pipeline_manual, "obter_relatorio_existente_para_processo", return_value=None,
    ), patch.object(
        pipeline_manual, "existe_conflito_de_processo", return_value=False,
    ), patch.object(
        pipeline_manual, "gerar_relatorio", side_effect=RuntimeError("falha simulada"),
    ), patch.object(pipeline_manual, "tratar_erro", return_value={"sucesso": False}):
        pipeline_manual._triar_e_processar(registro.id)

    atualizado = db_triagem.obter_registro(registro.id)
    assert atualizado.status == db_triagem.ERRO

    _limpar(registro.id)


def test_retomar_apos_conferencia_aprova_e_gera_direto():
    registro = _criar_registro("teste_pipeline_manual_conferencia.pdf")
    db_triagem.atualizar_apos_triagem(registro.id, db_triagem.NAO_ENCONTRADO, None, "revisao", "não achou nada")

    with patch.object(
        pipeline_manual, "gerar_relatorio",
        return_value=({"parecer": "..."}, {"custo_estimado_usd": 0.05}),
    ), patch.object(
        pipeline_manual, "finalizar_processamento",
        return_value={"sucesso": True, "job_id": 7777},
    ) as finalizar_mock:
        pipeline_manual._retomar_apos_conferencia_sync(registro.id, "0000000-00.2026.8.00.0500")

    assert finalizar_mock.called

    atualizado = db_triagem.obter_registro(registro.id)
    assert atualizado.status == db_triagem.CONCLUIDO
    assert atualizado.processo_detectado == "0000000-00.2026.8.00.0500"
    assert atualizado.confianca_nivel == "revisao"

    _limpar(registro.id)


def test_retomar_apos_conferencia_a_partir_de_falha_leitura_com_processo_manual():
    """A pessoa digitou o CNJ na mão pra um caso que tinha travado por
    falha de leitura — aprovação segue igual à de "processo não
    encontrado", sem tratamento especial."""
    registro = _criar_registro("teste_pipeline_manual_conferencia_falha_leitura.pdf")
    db_triagem.atualizar_apos_triagem(registro.id, db_triagem.FALHA_LEITURA, None, None, "Falha ao ler o PDF: erro simulado")

    with patch.object(
        pipeline_manual, "gerar_relatorio",
        return_value=({"parecer": "..."}, {"custo_estimado_usd": 0.05}),
    ), patch.object(
        pipeline_manual, "finalizar_processamento",
        return_value={"sucesso": True, "job_id": 8888},
    ) as finalizar_mock:
        pipeline_manual._retomar_apos_conferencia_sync(registro.id, "0000000-00.2026.8.00.0600")

    assert finalizar_mock.called

    atualizado = db_triagem.obter_registro(registro.id)
    assert atualizado.status == db_triagem.CONCLUIDO
    assert atualizado.processo_detectado == "0000000-00.2026.8.00.0600"

    _limpar(registro.id)
