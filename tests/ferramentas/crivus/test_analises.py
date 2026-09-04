from datetime import date, timedelta

import pytest
from sqlmodel import delete, select

from app.ferramentas.crivus.config.taxonomia import NAO_IDENTIFICADO
from app.ferramentas.crivus.db.analises import (
    concluir_analise,
    criar_agendamento_manual,
    criar_analise_a_partir_da_ia,
    descartar_alteracoes,
    listar_itens,
    marcar_ciente_alerta_critico,
    marcar_item_desnecessario,
    marcar_item_pronto,
    obter_analise,
    salvar_edicao_item,
)
from app.ferramentas.crivus.db.models import AnalisePublicacao, AnexoAnalise, ItemAcompanhamento, ItemAgendamento
from app.plataforma.db.models import CARGO_COLABORADOR
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario, excluir_usuario

NOME_USUARIO_TESTE = "teste_crivus_analises"


def _dados_ia_simples(tipo_acomp="AGUARDANDO AUDIÊNCIA DE CONCILIAÇÃO", tipo_agend="AUDIÊNCIA DE CONCILIAÇÃO",
                       tem_alerta_critico=False, agendamentos=None):
    return {
        "processo": "0000000-00.0000.0.00.0000",
        "carteira": "OUTRA",
        "leitura_publicacao": "leitura de teste",
        "conclusao_operacional": "conclusão de teste",
        "nivel_confianca": "ALTO",
        "tem_alerta_critico": tem_alerta_critico,
        "texto_alerta_critico": "providência urgente de teste" if tem_alerta_critico else None,
        "acompanhamentos": [{"tipo": tipo_acomp}],
        "agendamentos": agendamentos if agendamentos is not None else [{"tipo": tipo_agend, "dias_inicio": 5, "dias_fim": 5}],
    }


def _uso_fake():
    return {"modelo": "claude-sonnet-5", "tokens_entrada": 1000, "tokens_saida": 200, "custo_estimado_usd": 0.05}


@pytest.fixture
def usuario_teste():
    usuario = criar_usuario(
        nome="Teste Crivus Analises",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_crivus_analises@example.com",
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
        sessao.commit()

    excluir_usuario(usuario.id)


def test_criar_analise_calcula_datas_a_partir_de_dias(usuario_teste):
    dados = _dados_ia_simples()
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor colado", dados, _uso_fake())

    assert analise.status == "aguardando_revisao"
    assert analise.processo == "0000000-00.0000.0.00.0000"
    assert analise.nivel_confianca == "ALTO"

    acompanhamentos, agendamentos = listar_itens(analise.id)
    assert len(acompanhamentos) == 1
    assert acompanhamentos[0].tipo == acompanhamentos[0].tipo_sugerido == "AGUARDANDO AUDIÊNCIA DE CONCILIAÇÃO"
    assert acompanhamentos[0].status == "sugerido"

    assert len(agendamentos) == 1
    esperado = date.today() + timedelta(days=5)
    assert agendamentos[0].data_inicio == agendamentos[0].data_fim == esperado
    assert agendamentos[0].data_inicio_sugerida == esperado


def test_agendamentos_pode_ser_vazio_quando_nao_ha_providencia(usuario_teste):
    dados = _dados_ia_simples(tipo_acomp="LIMINAR DEFERIDA", agendamentos=[])
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor colado", dados, _uso_fake())

    _, agendamentos = listar_itens(analise.id)
    assert agendamentos == []


def test_marcar_item_pronto_preserva_sugestao_original(usuario_teste):
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())
    acompanhamentos, _ = listar_itens(analise.id)
    item = acompanhamentos[0]

    atualizado = marcar_item_pronto(analise.id, "acompanhamento", item.id, novo_tipo=NAO_IDENTIFICADO)

    assert atualizado.status == "pronto"
    assert atualizado.tipo == NAO_IDENTIFICADO
    assert atualizado.tipo_sugerido == "AGUARDANDO AUDIÊNCIA DE CONCILIAÇÃO"


def test_marcar_desnecessario_e_reverter(usuario_teste):
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())
    _, agendamentos = listar_itens(analise.id)
    item = agendamentos[0]

    marcar_item_desnecessario(analise.id, "agendamento", item.id, desnecessario=True)
    acompanhamentos, agendamentos = listar_itens(analise.id)
    assert agendamentos[0].status == "desnecessario"

    marcar_item_desnecessario(analise.id, "agendamento", item.id, desnecessario=False)
    _, agendamentos = listar_itens(analise.id)
    assert agendamentos[0].status == "sugerido"


def test_concluir_falha_com_item_pendente(usuario_teste):
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())

    with pytest.raises(ValueError):
        concluir_analise(analise.id)


def test_concluir_funciona_quando_todos_revisados(usuario_teste):
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())
    acompanhamentos, agendamentos = listar_itens(analise.id)

    marcar_item_pronto(analise.id, "acompanhamento", acompanhamentos[0].id)
    marcar_item_desnecessario(analise.id, "agendamento", agendamentos[0].id, desnecessario=True)

    concluida = concluir_analise(analise.id)
    assert concluida.status == "concluido"
    assert concluida.concluido_em is not None


def test_alerta_critico_trava_conclusao_ate_ciencia_marcada(usuario_teste):
    dados = _dados_ia_simples(tem_alerta_critico=True)
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", dados, _uso_fake())
    acompanhamentos, agendamentos = listar_itens(analise.id)
    marcar_item_pronto(analise.id, "acompanhamento", acompanhamentos[0].id)
    marcar_item_pronto(analise.id, "agendamento", agendamentos[0].id)

    with pytest.raises(ValueError):
        concluir_analise(analise.id)

    marcar_ciente_alerta_critico(analise.id)
    concluida = concluir_analise(analise.id)
    assert concluida.status == "concluido"


def test_nao_permite_corrigir_item_apos_caso_concluido(usuario_teste):
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())
    acompanhamentos, agendamentos = listar_itens(analise.id)
    marcar_item_pronto(analise.id, "acompanhamento", acompanhamentos[0].id)
    marcar_item_pronto(analise.id, "agendamento", agendamentos[0].id)
    concluir_analise(analise.id)

    with pytest.raises(ValueError):
        marcar_item_pronto(analise.id, "acompanhamento", acompanhamentos[0].id, novo_tipo="OUTRO")

    with pytest.raises(ValueError):
        marcar_item_desnecessario(analise.id, "agendamento", agendamentos[0].id, desnecessario=True)


def test_salvar_edicao_nao_confirma_o_item(usuario_teste):
    """Henrique, 2026-09-04: "Salvar Alterações" (modo edição) aplica a
    correção mas NÃO marca pronto — volta pro estado "aguardando
    confirmação", mesmo que já estivesse "pronto" antes de reabrir."""
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())
    acompanhamentos, agendamentos = listar_itens(analise.id)

    marcar_item_pronto(analise.id, "agendamento", agendamentos[0].id)
    atualizado = salvar_edicao_item(
        analise.id, "agendamento", agendamentos[0].id,
        "MANIFESTAÇÃO", nova_data_inicio=date.today(), nova_data_fim=date.today() + timedelta(days=3),
    )

    assert atualizado.status == "sugerido"
    assert atualizado.tipo == "MANIFESTAÇÃO"
    # sugestão original da IA preservada, não sobrescrita pela edição
    assert atualizado.tipo_sugerido == "AUDIÊNCIA DE CONCILIAÇÃO"


def test_salvar_edicao_sem_mudanca_nao_desfaz_pronto(usuario_teste):
    """Henrique, 2026-09-06: abrir o lápis, não mudar nada de verdade e
    clicar no check não pode desfazer um "Pronto" já dado — só uma
    edição real (tipo ou data diferente) volta o item pra "sugerido"."""
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())
    acompanhamentos, agendamentos = listar_itens(analise.id)

    marcar_item_pronto(analise.id, "acompanhamento", acompanhamentos[0].id)
    atualizado = salvar_edicao_item(analise.id, "acompanhamento", acompanhamentos[0].id, acompanhamentos[0].tipo)
    assert atualizado.status == "pronto"

    marcar_item_pronto(analise.id, "agendamento", agendamentos[0].id)
    item = agendamentos[0]
    atualizado = salvar_edicao_item(
        analise.id, "agendamento", item.id, item.tipo,
        nova_data_inicio=item.data_inicio, nova_data_fim=item.data_fim,
    )
    assert atualizado.status == "pronto"


def test_nao_permite_marcar_pronto_sem_tipo(usuario_teste):
    """Henrique, 2026-09-06: mesmo que o "required" do HTML e o
    interruptor em crivus.js barrem isso na tela, o servidor não pode
    confiar só neles — POST direto com tipo vazio tem que falhar."""
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())
    novo = criar_agendamento_manual(analise.id)

    with pytest.raises(ValueError):
        marcar_item_pronto(analise.id, "agendamento", novo.id)


def test_criar_agendamento_manual_nasce_em_branco(usuario_teste):
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())

    novo = criar_agendamento_manual(analise.id)

    assert novo.tipo == ""
    assert novo.tipo_sugerido == ""
    assert novo.criado_manualmente is True
    assert novo.status == "sugerido"
    assert novo.data_inicio == date.today()

    _, agendamentos = listar_itens(analise.id)
    assert len(agendamentos) == 2  # o original da IA + o manual


def test_nao_permite_adicionar_agendamento_apos_concluido(usuario_teste):
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())
    acompanhamentos, agendamentos = listar_itens(analise.id)
    marcar_item_pronto(analise.id, "acompanhamento", acompanhamentos[0].id)
    marcar_item_pronto(analise.id, "agendamento", agendamentos[0].id)
    concluir_analise(analise.id)

    with pytest.raises(ValueError):
        criar_agendamento_manual(analise.id)


def test_descartar_alteracoes_reverte_edicoes_ja_confirmadas(usuario_teste):
    """Henrique, 2026-09-06: "Descartar alterações e Voltar" precisa
    REALMENTE desfazer o que já foi gravado (marcar_item_pronto já
    confirma no banco na hora, não existe rascunho) — não pode ser só um
    link de volta."""
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())
    acompanhamentos, agendamentos = listar_itens(analise.id)

    marcar_item_pronto(analise.id, "acompanhamento", acompanhamentos[0].id, novo_tipo="OUTRO TIPO QUALQUER")
    marcar_item_pronto(
        analise.id, "agendamento", agendamentos[0].id,
        novo_tipo="MANIFESTAÇÃO", nova_data_inicio=date.today(), nova_data_fim=date.today() + timedelta(days=1),
    )
    marcar_ciente_alerta_critico(analise.id)

    descartar_alteracoes(analise.id)

    acompanhamentos, agendamentos = listar_itens(analise.id)
    assert acompanhamentos[0].tipo == acompanhamentos[0].tipo_sugerido == "AGUARDANDO AUDIÊNCIA DE CONCILIAÇÃO"
    assert acompanhamentos[0].status == "sugerido"
    assert agendamentos[0].tipo == agendamentos[0].tipo_sugerido == "AUDIÊNCIA DE CONCILIAÇÃO"
    assert agendamentos[0].data_inicio == agendamentos[0].data_inicio_sugerida
    assert agendamentos[0].data_fim == agendamentos[0].data_fim_sugerida
    assert agendamentos[0].status == "sugerido"

    analise_atualizada = obter_analise(analise.id)
    assert analise_atualizada.ciente_alerta_critico is False


def test_descartar_alteracoes_remove_agendamento_criado_manualmente(usuario_teste):
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())
    criar_agendamento_manual(analise.id)

    _, agendamentos = listar_itens(analise.id)
    assert len(agendamentos) == 2

    descartar_alteracoes(analise.id)

    _, agendamentos = listar_itens(analise.id)
    assert len(agendamentos) == 1
    assert agendamentos[0].criado_manualmente is not True


def test_nao_permite_descartar_apos_concluido(usuario_teste):
    analise = criar_analise_a_partir_da_ia(usuario_teste.id, "teor", _dados_ia_simples(), _uso_fake())
    acompanhamentos, agendamentos = listar_itens(analise.id)
    marcar_item_pronto(analise.id, "acompanhamento", acompanhamentos[0].id)
    marcar_item_pronto(analise.id, "agendamento", agendamentos[0].id)
    concluir_analise(analise.id)

    with pytest.raises(ValueError):
        descartar_alteracoes(analise.id)
