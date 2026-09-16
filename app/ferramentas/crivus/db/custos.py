from datetime import datetime, timedelta

from sqlmodel import func, select

from app.ferramentas.crivus.core.ia_cliente import MODELO_TRIAGEM
from app.ferramentas.crivus.db.models import AnalisePublicacao
from app.plataforma.db.session import obter_sessao


# Henrique, diretoria, 2026-09-16: "criar a tela de custos do Crivus...
# da mesma forma das outras ferramentas" — mesmas queries/formato de
# app/ferramentas/nucleo_relatorios/db/jobs.py, adaptadas pro modelo
# próprio do Crivus (AnalisePublicacao). 2 diferenças reais:
# - Sem "Robô automático": AnalisePublicacao.usuario_id NUNCA é None
#   (todo caso, individual ou de lote, tem um dono — quem processou ou
#   quem subiu a planilha), então não existe o balde "sem usuário" que
#   Job tem.
# - Custo tem 2 colunas, não 1: custo_estimado_usd (análise completa) e
#   custo_triagem_usd (pré-triagem barata do Processamento em Lote, ver
#   lote_batch.py). Uma linha "descartada" por qualidade só tem a
#   segunda (a análise completa nunca rodou) — CUSTO_TOTAL soma as duas
#   (COALESCE null->0) em toda conta abaixo, pra nenhum gasto real ficar
#   invisível.
CUSTO_TOTAL = func.coalesce(AnalisePublicacao.custo_estimado_usd, 0.0) + func.coalesce(AnalisePublicacao.custo_triagem_usd, 0.0)

STATUS_VALIDOS = ("processando", "aguardando_revisao", "concluido", "erro", "atrasado", "descartado")

# Rótulo sintético pra separar, no "Por modelo de IA", o gasto que foi
# só da pré-triagem (nunca chega a setar AnalisePublicacao.modelo_ia,
# que só é preenchido pela análise completa) — sem isso, esse custo real
# ficaria escondido debaixo de "Desconhecido".
ROTULO_TRIAGEM = f"Triagem ({MODELO_TRIAGEM})"


def listar_analises_para_custos(limite=200):
    with obter_sessao() as sessao:
        consulta = (
            select(AnalisePublicacao)
            .order_by(AnalisePublicacao.criado_em.desc())
            .limit(limite)
        )

        return sessao.exec(consulta).all()


def somar_custo_por_usuario():
    """Soma o custo total (estimado + triagem) por usuário — pra tela de
    custos do admin. Só soma quem tem custo > 0, mesmo critério já usado
    em nucleo_relatorios/db/jobs.py."""
    with obter_sessao() as sessao:
        linhas = sessao.exec(
            select(AnalisePublicacao.usuario_id, func.sum(CUSTO_TOTAL))
            .where(CUSTO_TOTAL > 0)
            .group_by(AnalisePublicacao.usuario_id)
        ).all()

    return {usuario_id: total for usuario_id, total in linhas}


def _mes_menos(ano, mes, quantidade):
    """Ver docstring equivalente em nucleo_relatorios/db/jobs.py — mesma
    aritmética de mês sem depender de datetime.replace."""
    indice = (ano * 12 + (mes - 1)) - quantidade
    return indice // 12, indice % 12 + 1


def resumo_mes_atual():
    agora = datetime.now()
    inicio_mes_atual = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ano_anterior, mes_anterior = _mes_menos(inicio_mes_atual.year, inicio_mes_atual.month, 1)
    inicio_mes_anterior = inicio_mes_atual.replace(year=ano_anterior, month=mes_anterior)

    with obter_sessao() as sessao:
        quantidade_atual, custo_atual = sessao.exec(
            select(func.count(), func.sum(CUSTO_TOTAL))
            .where(CUSTO_TOTAL > 0, AnalisePublicacao.criado_em >= inicio_mes_atual)
        ).first()

        quantidade_anterior, custo_anterior = sessao.exec(
            select(func.count(), func.sum(CUSTO_TOTAL))
            .where(
                CUSTO_TOTAL > 0,
                AnalisePublicacao.criado_em >= inicio_mes_anterior,
                AnalisePublicacao.criado_em < inicio_mes_atual,
            )
        ).first()

    quantidade_atual = quantidade_atual or 0
    quantidade_anterior = quantidade_anterior or 0
    custo_atual = custo_atual or 0.0
    custo_anterior = custo_anterior or 0.0

    return {
        "custo_mes": custo_atual,
        "quantidade_mes": quantidade_atual,
        "custo_medio_mes": (custo_atual / quantidade_atual) if quantidade_atual else 0.0,
        "custo_mes_anterior": custo_anterior,
        "quantidade_mes_anterior": quantidade_anterior,
        "custo_medio_mes_anterior": (custo_anterior / quantidade_anterior) if quantidade_anterior else 0.0,
    }


PERIODOS_SERIE_TEMPORAL = {"7d": 7, "15d": 15, "30d": 30, "1a": 365}


def serie_temporal_custo(periodo):
    if periodo not in PERIODOS_SERIE_TEMPORAL:
        raise ValueError(f"Período inválido: {periodo!r}")

    agora = datetime.now()
    granularidade_mensal = periodo == "1a"

    if granularidade_mensal:
        inicio_mes_atual = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ano_corte, mes_corte = _mes_menos(inicio_mes_atual.year, inicio_mes_atual.month, 11)
        corte = inicio_mes_atual.replace(year=ano_corte, month=mes_corte)
    else:
        dias = PERIODOS_SERIE_TEMPORAL[periodo]
        corte = (agora - timedelta(days=dias - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    with obter_sessao() as sessao:
        linhas = sessao.exec(
            select(AnalisePublicacao.criado_em, CUSTO_TOTAL)
            .where(CUSTO_TOTAL > 0, AnalisePublicacao.criado_em >= corte)
        ).all()

    agregados = {}
    for criado_em, custo in linhas:
        chave = criado_em.strftime("%Y-%m") if granularidade_mensal else criado_em.strftime("%Y-%m-%d")
        agregados[chave] = agregados.get(chave, 0.0) + custo

    pontos = []
    if granularidade_mensal:
        for i in range(11, -1, -1):
            ano, mes = _mes_menos(agora.year, agora.month, i)
            chave = f"{ano:04d}-{mes:02d}"
            pontos.append({"rotulo": f"{mes:02d}/{ano}", "custo": round(agregados.get(chave, 0.0), 4)})
    else:
        for i in range(PERIODOS_SERIE_TEMPORAL[periodo] - 1, -1, -1):
            dia = agora - timedelta(days=i)
            chave = dia.strftime("%Y-%m-%d")
            pontos.append({"rotulo": dia.strftime("%d/%m"), "custo": round(agregados.get(chave, 0.0), 4)})

    return pontos


def detalhar_custo_e_quantidade_por_usuario():
    with obter_sessao() as sessao:
        linhas = sessao.exec(
            select(AnalisePublicacao.usuario_id, func.count(), func.sum(CUSTO_TOTAL))
            .where(CUSTO_TOTAL > 0)
            .group_by(AnalisePublicacao.usuario_id)
        ).all()

    return {
        usuario_id: {
            "quantidade": quantidade,
            "custo": custo,
            "custo_medio": (custo / quantidade) if quantidade else 0.0,
        }
        for usuario_id, quantidade, custo in linhas
    }


def resumo_por_status_com_custo():
    resultado = {status: {"quantidade": 0, "custo": 0.0} for status in STATUS_VALIDOS}

    with obter_sessao() as sessao:
        linhas = sessao.exec(
            select(AnalisePublicacao.status, func.count(), func.sum(CUSTO_TOTAL))
            .group_by(AnalisePublicacao.status)
        ).all()

    for status, quantidade, custo in linhas:
        if status in resultado:
            resultado[status] = {"quantidade": quantidade, "custo": custo or 0.0}

    return resultado


def resumo_por_modelo():
    """Diferente de Job (1 coluna de custo, 1 modelo por linha): uma
    linha "descartada" pela triagem paga custo_triagem_usd mas nunca
    chega a rodar a análise completa, então `modelo_ia` (só preenchido
    por ela) fica None — conta os dois separadamente: análise completa
    por modelo_ia (like jobs.py) + uma linha própria somando todo
    custo_triagem_usd > 0, não importa o status da linha."""
    with obter_sessao() as sessao:
        linhas_analise = sessao.exec(
            select(AnalisePublicacao.modelo_ia, func.count(), func.sum(AnalisePublicacao.custo_estimado_usd))
            .where(AnalisePublicacao.custo_estimado_usd > 0)
            .group_by(AnalisePublicacao.modelo_ia)
        ).all()

        quantidade_triagem, custo_triagem = sessao.exec(
            select(func.count(), func.sum(AnalisePublicacao.custo_triagem_usd))
            .where(AnalisePublicacao.custo_triagem_usd > 0)
        ).first()

    resultado = [
        {"modelo": modelo or "Desconhecido", "quantidade": quantidade, "custo": custo}
        for modelo, quantidade, custo in linhas_analise
    ]

    if quantidade_triagem:
        resultado.append({"modelo": ROTULO_TRIAGEM, "quantidade": quantidade_triagem, "custo": custo_triagem or 0.0})

    return resultado
