"""lotes_crivus.py — LoteCrivus e as AnalisePublicacao (origem="lote")
que ele agrupa. Nomeação/convenções paralelas a test_analises.py."""

from datetime import date

import pytest
from sqlmodel import delete, select

from app.ferramentas.crivus.db.analises import listar_itens
from app.ferramentas.crivus.db.lotes_crivus import (
    concluir_analise_de_lote,
    criar_lote,
    listar_analises_do_batch,
    listar_batch_ids_em_andamento,
    listar_pendentes_de_despacho,
    lote_ainda_tem_linha_processando,
    marcar_analise_atrasada,
    marcar_analise_de_lote_com_erro,
    marcar_analise_descartada,
    marcar_batch_id,
    marcar_lote_concluido,
    obter_lote,
    registrar_custo_triagem,
)
from app.ferramentas.crivus.db.models import AnalisePublicacao, AnexoAnalise, ItemAcompanhamento, ItemAgendamento, LoteCrivus
from app.plataforma.db.models import CARGO_COLABORADOR
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario, excluir_usuario

NOME_USUARIO_TESTE = "teste_crivus_lotes"


def _linhas_fake(quantidade=2):
    return [
        {
            "npjur": f"01000{indice:02d}",
            "data_publicacao": date(2026, 9, 10),
            "data_importacao": date(2026, 9, 11),
            "teor": f"teor da linha {indice}",
        }
        for indice in range(quantidade)
    ]


def _dados_ia_fake():
    return {
        "processo": "0000000-00.0000.0.00.0000",
        "carteira": "OUTRA",
        "conclusao_operacional": "conclusão de teste",
        "nivel_confianca": "ALTO",
        "tem_alerta_critico": False,
        "texto_alerta_critico": None,
        "acompanhamentos": [{"tipo": "PUBLICAÇÃO"}],
        "agendamentos": [{"tipo": "MANIFESTAÇÃO", "dias_inicio": 5, "dias_fim": 5}],
    }, {"modelo": "claude-sonnet-5", "tokens_entrada": 1000, "tokens_saida": 200, "custo_estimado_usd": 0.05}


@pytest.fixture
def usuario_teste():
    usuario = criar_usuario(
        nome="Teste Crivus Lotes",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_crivus_lotes@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COLABORADOR,
    )
    yield usuario

    with obter_sessao() as sessao:
        analises = sessao.exec(select(AnalisePublicacao).where(AnalisePublicacao.usuario_id == usuario.id)).all()
        for analise in analises:
            sessao.exec(delete(ItemAcompanhamento).where(ItemAcompanhamento.analise_id == analise.id))
            sessao.exec(delete(ItemAgendamento).where(ItemAgendamento.analise_id == analise.id))
            sessao.exec(delete(AnexoAnalise).where(AnexoAnalise.analise_id == analise.id))
        sessao.exec(delete(AnalisePublicacao).where(AnalisePublicacao.usuario_id == usuario.id))
        sessao.exec(delete(LoteCrivus).where(LoteCrivus.criado_por == usuario.id))
        sessao.commit()

    excluir_usuario(usuario.id)


def test_criar_lote_cria_uma_analise_por_linha(usuario_teste):
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", _linhas_fake(3))

    assert lote.total_linhas == 3
    assert lote.status == "processando"

    with obter_sessao() as sessao:
        analises = sessao.exec(select(AnalisePublicacao).where(AnalisePublicacao.lote_id == lote.id)).all()

    assert len(analises) == 3
    assert all(a.origem == "lote" for a in analises)
    assert all(a.status == "processando" for a in analises)
    assert all(a.data_publicacao_original == date(2026, 9, 10) for a in analises)
    assert all(a.data_importacao_original == date(2026, 9, 11) for a in analises)


def test_listar_pendentes_de_despacho_so_pega_lote_sem_batch_id(usuario_teste):
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", _linhas_fake(2))
    pendentes = listar_pendentes_de_despacho(lote.id)
    assert len(pendentes) == 2

    marcar_batch_id([pendentes[0].id], "msgbatch_teste")

    pendentes_depois = listar_pendentes_de_despacho(lote.id)
    assert len(pendentes_depois) == 1
    assert pendentes_depois[0].id == pendentes[1].id


def test_marcar_batch_id_e_listar_batch_ids_em_andamento(usuario_teste):
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", _linhas_fake(2))
    pendentes = listar_pendentes_de_despacho(lote.id)
    ids = [item.id for item in pendentes]

    marcar_batch_id(ids, "msgbatch_abc")

    assert listar_batch_ids_em_andamento() == ["msgbatch_abc"]
    do_batch = listar_analises_do_batch("msgbatch_abc")
    assert {a.id for a in do_batch} == set(ids)


def test_concluir_analise_de_lote_preenche_sem_duplicar(usuario_teste):
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", _linhas_fake(1))
    pendente = listar_pendentes_de_despacho(lote.id)[0]
    dados_ia, uso_ia = _dados_ia_fake()

    concluida = concluir_analise_de_lote(pendente.id, dados_ia, uso_ia)

    assert concluida.status == "aguardando_revisao"
    assert concluida.processo == "0000000-00.0000.0.00.0000"

    with obter_sessao() as sessao:
        total = len(sessao.exec(select(AnalisePublicacao).where(AnalisePublicacao.lote_id == lote.id)).all())
    assert total == 1  # não criou uma linha nova, só preencheu a que já existia

    acompanhamentos, agendamentos = listar_itens(concluida.id)
    assert len(acompanhamentos) == 1
    assert len(agendamentos) == 1


def test_marcar_analise_de_lote_com_erro(usuario_teste):
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", _linhas_fake(1))
    pendente = listar_pendentes_de_despacho(lote.id)[0]

    marcada = marcar_analise_de_lote_com_erro(pendente.id, "Falha ao analisar: timeout")

    assert marcada.status == "erro"
    assert marcada.erro_mensagem == "Falha ao analisar: timeout"


def test_lote_ainda_tem_linha_processando_e_marcar_lote_concluido(usuario_teste, tmp_path):
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", _linhas_fake(2))
    pendentes = listar_pendentes_de_despacho(lote.id)

    assert lote_ainda_tem_linha_processando(lote.id) is True

    dados_ia, uso_ia = _dados_ia_fake()
    concluir_analise_de_lote(pendentes[0].id, dados_ia, uso_ia)
    assert lote_ainda_tem_linha_processando(lote.id) is True  # ainda falta 1

    marcar_analise_de_lote_com_erro(pendentes[1].id, "erro de teste")
    assert lote_ainda_tem_linha_processando(lote.id) is False  # as 2 saíram de "processando"

    caminho_saida = tmp_path / "resultado.xlsx"
    concluido = marcar_lote_concluido(lote.id, caminho_saida)

    assert concluido.status == "concluido"
    assert concluido.linhas_sucesso == 1
    assert concluido.linhas_erro == 1
    assert concluido.linhas_atrasadas == 0
    assert concluido.finalizado_em is not None
    assert concluido.caminho_planilha_saida == str(caminho_saida)

    assert obter_lote(lote.id).status == "concluido"


def test_marcar_analise_atrasada(usuario_teste):
    """Henrique, coordenador, 2026-09-14: linha com 2+ dias de atraso
    nunca vai pra IA — vira status="atrasado", excluída de propósito."""
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", _linhas_fake(1))
    pendente = listar_pendentes_de_despacho(lote.id)[0]

    marcada = marcar_analise_atrasada(pendente.id, "Publicado há 3 dias. Prazo de 2 dias estourado, encaminhado para tratamento manual.")

    assert marcada.status == "atrasado"
    assert "tratamento manual" in marcada.erro_mensagem


def test_marcar_analise_descartada_sem_custo_de_triagem(usuario_teste):
    """Camada 1 (regra grátis) — não passou por IA nenhuma."""
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", _linhas_fake(1))
    pendente = listar_pendentes_de_despacho(lote.id)[0]

    marcada = marcar_analise_descartada(pendente.id, "Conteúdo muito curto ou inválido para análise.")

    assert marcada.status == "descartado"
    assert marcada.erro_mensagem == "Conteúdo muito curto ou inválido para análise."
    assert marcada.custo_triagem_usd is None


def test_marcar_analise_descartada_com_custo_de_triagem(usuario_teste):
    """Camada 2 (pré-análise de IA) — o custo da triagem precisa ficar
    registrado mesmo quando a linha é descartada em seguida."""
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", _linhas_fake(1))
    pendente = listar_pendentes_de_despacho(lote.id)[0]

    marcada = marcar_analise_descartada(pendente.id, "Teor vago demais.", custo_triagem_usd=0.0017)

    assert marcada.status == "descartado"
    assert marcada.custo_triagem_usd == 0.0017


def test_registrar_custo_triagem_nao_muda_status(usuario_teste):
    """Linha aprovada na triagem segue pendente (sem batch_id, sem mudar
    status) — só o custo da pré-análise é gravado."""
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", _linhas_fake(1))
    pendente = listar_pendentes_de_despacho(lote.id)[0]

    registrar_custo_triagem(pendente.id, 0.0021)

    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, pendente.id)

    assert analise.status == "processando"
    assert analise.batch_id is None
    assert analise.custo_triagem_usd == 0.0021


def test_marcar_lote_concluido_conta_os_4_baldes_separados(usuario_teste, tmp_path):
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", _linhas_fake(4))
    pendentes = listar_pendentes_de_despacho(lote.id)

    dados_ia, uso_ia = _dados_ia_fake()
    concluir_analise_de_lote(pendentes[0].id, dados_ia, uso_ia)
    marcar_analise_de_lote_com_erro(pendentes[1].id, "erro de teste")
    marcar_analise_atrasada(pendentes[2].id, "atrasado de teste")
    marcar_analise_descartada(pendentes[3].id, "descartado de teste")

    concluido = marcar_lote_concluido(lote.id, tmp_path / "resultado.xlsx")

    assert concluido.linhas_sucesso == 1
    assert concluido.linhas_erro == 1
    assert concluido.linhas_atrasadas == 1
    assert concluido.linhas_descartadas == 1
