"""O harness de urgência + submissão/coleta da API de Lote — a Anthropic
é SEMPRE mockada aqui, nunca uma chamada de rede de verdade."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import delete, select

from app.ferramentas.crivus.core import lote_batch
from app.ferramentas.crivus.db.lotes_crivus import criar_lote, listar_pendentes_de_despacho, obter_lote
from app.ferramentas.crivus.db.models import AnalisePublicacao, AnexoAnalise, ItemAcompanhamento, ItemAgendamento, LoteCrivus
from app.plataforma.db.models import CARGO_COLABORADOR
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario, excluir_usuario

NOME_USUARIO_TESTE = "teste_crivus_lote_batch"


def _linha(dias_desde_publicacao=0, adiantado=False, npjur="0100000", teor="teor de teste"):
    data_publicacao = date.today() - timedelta(days=dias_desde_publicacao)
    data_importacao = data_publicacao - timedelta(days=1) if adiantado else data_publicacao + timedelta(days=1)
    return {"npjur": npjur, "data_publicacao": data_publicacao, "data_importacao": data_importacao, "teor": teor}


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


class _ClienteFake:
    """Substitui anthropic.Anthropic por completo — nenhum teste aqui
    bate na rede de verdade."""

    def __init__(self, resultados_por_batch=None):
        self.chamadas_create = []
        self._proximo_batch_id = 1
        self._resultados_por_batch = resultados_por_batch or {}
        self.messages = SimpleNamespace(
            batches=SimpleNamespace(
                create=self._create,
                retrieve=self._retrieve,
                results=self._results,
            )
        )

    def _create(self, requests):
        batch_id = f"msgbatch_{self._proximo_batch_id}"
        self._proximo_batch_id += 1
        self.chamadas_create.append({"batch_id": batch_id, "requests": requests})
        return SimpleNamespace(id=batch_id)

    def _retrieve(self, batch_id):
        return SimpleNamespace(processing_status="ended")

    def _results(self, batch_id):
        return self._resultados_por_batch.get(batch_id, [])


def _resultado_sucesso(custom_id, dados_ferramenta):
    bloco = SimpleNamespace(type="tool_use", input=dados_ferramenta)
    usage = SimpleNamespace(
        input_tokens=1000, output_tokens=200,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
        cache_creation=None,
    )
    mensagem = SimpleNamespace(content=[bloco], usage=usage, model="claude-sonnet-5")
    return SimpleNamespace(custom_id=custom_id, result=SimpleNamespace(type="succeeded", message=mensagem))


def _resultado_erro(custom_id, tipo="errored"):
    return SimpleNamespace(custom_id=custom_id, result=SimpleNamespace(type=tipo, error=None))


@pytest.fixture
def usuario_teste():
    usuario = criar_usuario(
        nome="Teste Crivus Lote Batch",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_crivus_lote_batch@example.com",
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


# --- eh_urgente / eh_adiantado --------------------------------------------

def test_eh_urgente_com_datas_de_exemplo():
    hoje = date(2026, 9, 12)

    def _analise(dias):
        return SimpleNamespace(data_publicacao_original=hoje - timedelta(days=dias))

    assert lote_batch.eh_urgente(_analise(0), hoje=hoje) is False
    assert lote_batch.eh_urgente(_analise(1), hoje=hoje) is False
    # confirmado com Henrique: publicado 10/09, hoje 12/09 (2 dias) já é urgente
    assert lote_batch.eh_urgente(_analise(2), hoje=hoje) is True
    assert lote_batch.eh_urgente(_analise(3), hoje=hoje) is True


def test_eh_urgente_sem_data_e_falso_por_seguranca():
    analise = SimpleNamespace(data_publicacao_original=None)
    assert lote_batch.eh_urgente(analise) is False


def test_eh_adiantado():
    publicacao = date(2026, 9, 10)

    adiantado = SimpleNamespace(data_publicacao_original=publicacao, data_importacao_original=publicacao - timedelta(days=1))
    normal = SimpleNamespace(data_publicacao_original=publicacao, data_importacao_original=publicacao + timedelta(days=1))
    igual = SimpleNamespace(data_publicacao_original=publicacao, data_importacao_original=publicacao)

    assert lote_batch.eh_adiantado(adiantado) is True
    assert lote_batch.eh_adiantado(normal) is False
    assert lote_batch.eh_adiantado(igual) is False


# --- ciclo completo --------------------------------------------------------

def test_linha_urgente_e_processada_na_hora(usuario_teste, monkeypatch, tmp_path):
    monkeypatch.setattr(lote_batch, "PASTA_SAIDA_LOTES", tmp_path)
    dados_ia, uso_ia = _dados_ia_fake()
    monkeypatch.setattr(lote_batch, "analisar_publicacao", lambda teor, anexos=None: (dados_ia, uso_ia))

    cliente_fake = _ClienteFake()
    monkeypatch.setattr(lote_batch, "_obter_cliente", lambda: cliente_fake)

    lote = criar_lote(usuario_teste.id, "planilha.xlsx", [_linha(dias_desde_publicacao=3)])

    lote_batch.rodar_ciclo_lote({"lote_ativo": True})

    with obter_sessao() as sessao:
        analise = sessao.exec(select(AnalisePublicacao).where(AnalisePublicacao.lote_id == lote.id)).first()

    assert analise.status == "aguardando_revisao"
    assert analise.batch_id is None  # nunca passou pela API de Lote
    assert cliente_fake.chamadas_create == []  # nada sobrou pra submeter

    lote_atualizado = obter_lote(lote.id)
    assert lote_atualizado.status == "concluido"
    assert lote_atualizado.caminho_planilha_saida is not None


def test_linha_nao_urgente_vai_para_api_de_lote(usuario_teste, monkeypatch):
    cliente_fake = _ClienteFake()
    monkeypatch.setattr(lote_batch, "_obter_cliente", lambda: cliente_fake)

    lote = criar_lote(usuario_teste.id, "planilha.xlsx", [_linha(dias_desde_publicacao=0)])

    lote_batch.rodar_ciclo_lote({"lote_ativo": True})

    with obter_sessao() as sessao:
        analise = sessao.exec(select(AnalisePublicacao).where(AnalisePublicacao.lote_id == lote.id)).first()

    assert analise.status == "processando"  # ainda esperando o resultado do batch
    assert analise.batch_id is not None
    assert len(cliente_fake.chamadas_create) == 1
    assert cliente_fake.chamadas_create[0]["requests"][0]["custom_id"] == str(analise.id)


def test_adiantado_entra_na_frente_da_fila_de_submissao(usuario_teste, monkeypatch):
    cliente_fake = _ClienteFake()
    monkeypatch.setattr(lote_batch, "_obter_cliente", lambda: cliente_fake)

    # a linha "normal" é criada primeiro (mais antiga), a "adiantada" depois —
    # sem a priorização, ela apareceria em 2º na ordem de submissão.
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", [
        _linha(dias_desde_publicacao=0, adiantado=False, npjur="0111111"),
        _linha(dias_desde_publicacao=0, adiantado=True, npjur="0222222"),
    ])

    lote_batch.rodar_ciclo_lote({"lote_ativo": True})

    with obter_sessao() as sessao:
        analise_adiantada = sessao.exec(
            select(AnalisePublicacao).where(AnalisePublicacao.lote_id == lote.id, AnalisePublicacao.npjur == "0222222")
        ).first()

    requests_enviadas = cliente_fake.chamadas_create[0]["requests"]
    ids_na_ordem_enviada = [r["custom_id"] for r in requests_enviadas]
    assert ids_na_ordem_enviada[0] == str(analise_adiantada.id)


def test_reconciliacao_de_resultado_sucesso(usuario_teste, monkeypatch, tmp_path):
    monkeypatch.setattr(lote_batch, "PASTA_SAIDA_LOTES", tmp_path)
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", [_linha(dias_desde_publicacao=0)])
    pendente = listar_pendentes_de_despacho(lote.id)[0]

    dados_ia, _ = _dados_ia_fake()
    cliente_fake = _ClienteFake(resultados_por_batch={
        "msgbatch_1": [_resultado_sucesso(str(pendente.id), dados_ia)],
    })
    monkeypatch.setattr(lote_batch, "_obter_cliente", lambda: cliente_fake)

    from app.ferramentas.crivus.db.lotes_crivus import marcar_batch_id
    marcar_batch_id([pendente.id], "msgbatch_1")

    lote_batch.rodar_ciclo_lote({"lote_ativo": False})  # só coleta, não submete nada novo

    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, pendente.id)
    assert analise.status == "aguardando_revisao"
    assert analise.processo == "0000000-00.0000.0.00.0000"

    assert obter_lote(lote.id).status == "concluido"


def test_reconciliacao_de_resultado_com_erro(usuario_teste, monkeypatch, tmp_path):
    monkeypatch.setattr(lote_batch, "PASTA_SAIDA_LOTES", tmp_path)
    lote = criar_lote(usuario_teste.id, "planilha.xlsx", [_linha(dias_desde_publicacao=0)])
    pendente = listar_pendentes_de_despacho(lote.id)[0]

    cliente_fake = _ClienteFake(resultados_por_batch={
        "msgbatch_1": [_resultado_erro(str(pendente.id), tipo="expired")],
    })
    monkeypatch.setattr(lote_batch, "_obter_cliente", lambda: cliente_fake)

    from app.ferramentas.crivus.db.lotes_crivus import marcar_batch_id
    marcar_batch_id([pendente.id], "msgbatch_1")

    lote_batch.rodar_ciclo_lote({"lote_ativo": False})

    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, pendente.id)
    assert analise.status == "erro"
    assert "expired" in analise.erro_mensagem


def test_uma_falha_local_nunca_bloqueia_o_resto_do_grupo(usuario_teste, monkeypatch):
    """Uma linha cujo teor quebra na hora de montar os parâmetros (ex:
    erro inesperado) não pode impedir as outras linhas do mesmo grupo de
    serem submetidas."""
    cliente_fake = _ClienteFake()
    monkeypatch.setattr(lote_batch, "_obter_cliente", lambda: cliente_fake)

    def _montar_parametros_com_falha_na_primeira(teor, anexos=None):
        if "quebra" in teor:
            raise RuntimeError("erro simulado")
        return {"model": "claude-sonnet-5", "messages": []}

    monkeypatch.setattr(lote_batch, "montar_parametros_mensagem", _montar_parametros_com_falha_na_primeira)

    lote = criar_lote(usuario_teste.id, "planilha.xlsx", [
        _linha(dias_desde_publicacao=0, npjur="0111111", teor="teor que quebra"),
        _linha(dias_desde_publicacao=0, npjur="0222222", teor="teor normal"),
    ])

    lote_batch.rodar_ciclo_lote({"lote_ativo": True})

    with obter_sessao() as sessao:
        quebrada = sessao.exec(
            select(AnalisePublicacao).where(AnalisePublicacao.lote_id == lote.id, AnalisePublicacao.npjur == "0111111")
        ).first()
        normal = sessao.exec(
            select(AnalisePublicacao).where(AnalisePublicacao.lote_id == lote.id, AnalisePublicacao.npjur == "0222222")
        ).first()

    assert quebrada.status == "erro"
    assert normal.status == "processando"
    assert normal.batch_id is not None
    assert len(cliente_fake.chamadas_create[0]["requests"]) == 1
