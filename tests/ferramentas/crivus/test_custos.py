from datetime import datetime, timedelta

import pytest
from sqlmodel import delete, select

from app.ferramentas.crivus.db.custos import (
    ROTULO_TRIAGEM,
    detalhar_custo_e_quantidade_por_usuario,
    listar_analises_para_custos,
    resumo_mes_atual,
    resumo_por_modelo,
    resumo_por_status_com_custo,
    serie_temporal_custo,
    somar_custo_por_usuario,
)
from app.ferramentas.crivus.db.models import AnalisePublicacao
from app.plataforma.db.models import CARGO_COLABORADOR
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario, excluir_usuario


NOME_USUARIO_TESTE = "teste_crivus_custos"
NPJUR_PREFIXO = "teste_custos_"


@pytest.fixture
def usuario_teste():
    with obter_sessao() as sessao:
        sessao.exec(delete(AnalisePublicacao).where(AnalisePublicacao.npjur.like(f"{NPJUR_PREFIXO}%")))
        sessao.commit()

    usuario = criar_usuario(
        nome="Teste Crivus Custos",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_crivus_custos@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COLABORADOR,
    )

    yield usuario

    with obter_sessao() as sessao:
        sessao.exec(delete(AnalisePublicacao).where(AnalisePublicacao.npjur.like(f"{NPJUR_PREFIXO}%")))
        sessao.commit()

    excluir_usuario(usuario.id)


def _criar_analise(usuario_id, npjur, status="concluido", custo_estimado_usd=None, custo_triagem_usd=None,
                    modelo_ia=None, criado_em=None):
    with obter_sessao() as sessao:
        analise = AnalisePublicacao(
            usuario_id=usuario_id,
            origem="lote",
            teor_publicacao="teor de teste",
            npjur=npjur,
            status=status,
            custo_estimado_usd=custo_estimado_usd,
            custo_triagem_usd=custo_triagem_usd,
            modelo_ia=modelo_ia,
        )
        if criado_em is not None:
            analise.criado_em = criado_em
        sessao.add(analise)
        sessao.commit()
        sessao.refresh(analise)
        return analise


def test_somar_custo_por_usuario_soma_estimado_e_triagem(usuario_teste):
    # Henrique, diretoria, 2026-09-16: diferente de Job (1 coluna de
    # custo), AnalisePublicacao tem 2 — custo_estimado_usd (análise
    # completa) e custo_triagem_usd (pré-triagem do Processamento em
    # Lote, ver lote_batch.py). Uma linha "descartada" por qualidade só
    # tem a segunda; o total precisa somar as duas.
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}1", status="concluido", custo_estimado_usd=0.10)
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}2", status="descartado", custo_triagem_usd=0.01)
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}3", status="atrasado")  # sem custo nenhum

    total = somar_custo_por_usuario()

    assert round(total[usuario_teste.id], 4) == 0.11


def test_somar_custo_por_usuario_ignora_quem_nao_tem_custo_real(usuario_teste):
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}4", status="atrasado")

    assert usuario_teste.id not in somar_custo_por_usuario()


def test_detalhar_custo_e_quantidade_por_usuario(usuario_teste):
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}5", status="concluido", custo_estimado_usd=0.10)
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}6", status="concluido", custo_estimado_usd=0.30)

    detalhe = detalhar_custo_e_quantidade_por_usuario()[usuario_teste.id]

    assert detalhe["quantidade"] == 2
    assert round(detalhe["custo"], 4) == 0.40
    assert round(detalhe["custo_medio"], 4) == 0.20


def test_resumo_mes_atual_conta_so_quem_tem_custo_no_mes(usuario_teste):
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}7", status="concluido", custo_estimado_usd=0.05)
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}8", status="atrasado")  # sem custo, não deveria contar

    resumo = resumo_mes_atual()

    assert resumo["quantidade_mes"] >= 1
    assert resumo["custo_mes"] >= 0.05


def test_resumo_por_status_com_custo_cobre_os_6_status(usuario_teste):
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}9", status="concluido", custo_estimado_usd=0.10)
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}10", status="descartado", custo_triagem_usd=0.01)
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}11", status="atrasado")

    resumo = resumo_por_status_com_custo()

    assert set(resumo.keys()) == {"processando", "aguardando_revisao", "concluido", "erro", "atrasado", "descartado"}
    assert resumo["concluido"]["quantidade"] >= 1
    assert resumo["descartado"]["quantidade"] >= 1
    assert round(resumo["descartado"]["custo"], 4) >= 0.01
    assert resumo["atrasado"]["quantidade"] >= 1


def test_resumo_por_modelo_separa_triagem_de_analise_completa(usuario_teste):
    # Uma linha "descartada" nunca seta modelo_ia (só a análise completa
    # seta) — sem tratamento especial, esse custo real ficaria escondido
    # debaixo de "Desconhecido". resumo_por_modelo cria um balde
    # sintético só pra isso (ROTULO_TRIAGEM).
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}12", status="concluido",
                    custo_estimado_usd=0.10, modelo_ia="claude-sonnet-5")
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}13", status="descartado", custo_triagem_usd=0.02)

    resultado = resumo_por_modelo()
    por_modelo = {item["modelo"]: item for item in resultado}

    assert "claude-sonnet-5" in por_modelo
    assert round(por_modelo["claude-sonnet-5"]["custo"], 4) == 0.10
    assert ROTULO_TRIAGEM in por_modelo
    assert round(por_modelo[ROTULO_TRIAGEM]["custo"], 4) == 0.02


def test_serie_temporal_custo_inclui_hoje(usuario_teste):
    _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}14", status="concluido", custo_estimado_usd=0.07)

    pontos = serie_temporal_custo("7d")

    assert len(pontos) == 7
    assert round(sum(p["custo"] for p in pontos), 4) >= 0.07


def test_serie_temporal_custo_periodo_invalido_levanta_erro():
    with pytest.raises(ValueError):
        serie_temporal_custo("2 semanas")


def test_listar_analises_para_custos_ordena_mais_recente_primeiro(usuario_teste):
    mais_antiga = _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}15", criado_em=datetime.now() - timedelta(days=5))
    mais_recente = _criar_analise(usuario_teste.id, f"{NPJUR_PREFIXO}16", criado_em=datetime.now())

    ids = [a.id for a in listar_analises_para_custos(limite=1000)]

    assert ids.index(mais_recente.id) < ids.index(mais_antiga.id)
