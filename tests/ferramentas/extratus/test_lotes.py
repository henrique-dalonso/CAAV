import pytest
from sqlmodel import delete

from app.ferramentas.extratus.db.lotes import (
    criar_lote,
    listar_arquivos_ja_reivindicados,
    listar_itens_do_lote,
    listar_lotes_em_andamento,
    marcar_item_concluido,
    marcar_lote_concluido,
    obter_estatisticas_lotes,
)
from app.ferramentas.extratus.db.models import ItemLoteRobo, LoteRobo
from app.plataforma.db.session import obter_sessao


BATCH_ID_TESTE = "teste_batch_lotes_9101"


@pytest.fixture
def limpar_lotes_teste():
    yield
    with obter_sessao() as sessao:
        lote = sessao.exec(
            delete(LoteRobo).where(LoteRobo.batch_id == BATCH_ID_TESTE)
        )
        sessao.commit()
        sessao.exec(
            delete(ItemLoteRobo).where(ItemLoteRobo.arquivo_pdf.like("teste_lote_%"))
        )
        sessao.commit()


def _itens_exemplo():
    return [
        {
            "custom_id": "custom-a",
            "arquivo_pdf": "teste_lote_a.pdf",
            "processo_detectado": "0000000-00.2026.8.00.0000",
            "confianca_nivel": "alta",
            "confianca_motivo": "teste",
        },
        {
            "custom_id": "custom-b",
            "arquivo_pdf": "teste_lote_b.pdf",
            "processo_detectado": None,
            "confianca_nivel": "revisao",
            "confianca_motivo": "teste",
        },
    ]


def test_criar_lote_grava_lote_e_itens(limpar_lotes_teste):
    lote = criar_lote(BATCH_ID_TESTE, _itens_exemplo())

    assert lote.status == "enviado"

    itens = listar_itens_do_lote(lote.id)
    assert {item.arquivo_pdf for item in itens} == {"teste_lote_a.pdf", "teste_lote_b.pdf"}
    assert all(item.status == "pendente" for item in itens)


def test_lote_recem_criado_aparece_em_andamento(limpar_lotes_teste):
    lote = criar_lote(BATCH_ID_TESTE, _itens_exemplo())

    em_andamento = [l.id for l in listar_lotes_em_andamento()]
    assert lote.id in em_andamento


def test_marcar_lote_concluido_tira_da_listagem_em_andamento(limpar_lotes_teste):
    lote = criar_lote(BATCH_ID_TESTE, _itens_exemplo())
    marcar_lote_concluido(lote.id)

    em_andamento = [l.id for l in listar_lotes_em_andamento()]
    assert lote.id not in em_andamento


def test_marcar_item_concluido_atualiza_status(limpar_lotes_teste):
    lote = criar_lote(BATCH_ID_TESTE, _itens_exemplo())
    item = listar_itens_do_lote(lote.id)[0]

    marcar_item_concluido(item.id, "sucesso")

    itens_atualizados = listar_itens_do_lote(lote.id)
    atualizado = next(i for i in itens_atualizados if i.id == item.id)
    assert atualizado.status == "sucesso"


def test_arquivos_reivindicados_inclui_itens_de_qualquer_lote(limpar_lotes_teste):
    criar_lote(BATCH_ID_TESTE, _itens_exemplo())

    reivindicados = listar_arquivos_ja_reivindicados()
    assert "teste_lote_a.pdf" in reivindicados
    assert "teste_lote_b.pdf" in reivindicados
    assert "teste_lote_nunca_enviado.pdf" not in reivindicados


def test_estatisticas_lotes_conta_so_concluidos_e_pega_o_mais_recente(limpar_lotes_teste):
    antes = obter_estatisticas_lotes()

    lote = criar_lote(BATCH_ID_TESTE, _itens_exemplo())
    # Ainda "enviado" (em voo) — não deve contar como concluído.
    assert obter_estatisticas_lotes()["total_concluidos"] == antes["total_concluidos"]

    marcar_lote_concluido(lote.id)
    depois = obter_estatisticas_lotes()

    assert depois["total_concluidos"] == antes["total_concluidos"] + 1
    assert depois["ultimo_concluido_em"] is not None
