import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.ferramentas.extratus.core.config_manager import (
    atualizar_parametros_economia as _atualizar_parametros_economia_extratus,
    carregar_config as _carregar_config_extratus,
)
from app.ferramentas.extratus.db.checagem_fila import (
    resolver_solicitantes as _resolver_solicitantes_extratus,
)
from app.ferramentas.extratus.db.jobs import (
    detalhar_custo_e_quantidade_por_usuario as _detalhar_custo_e_quantidade_por_usuario_extratus,
    listar_jobs as _listar_jobs_extratus,
    resumo_mes_atual as _resumo_mes_atual_extratus,
    resumo_por_modelo as _resumo_por_modelo_extratus,
    resumo_por_status_com_custo as _resumo_por_status_com_custo_extratus,
    serie_temporal_custo as _serie_temporal_custo_extratus,
    somar_custo_por_usuario as _somar_custo_por_usuario_extratus,
)
from app.ferramentas.extratus.web.rotulos import (
    rotulo_erro as _rotulo_erro_extratus,
    rotulo_status as _rotulo_status_extratus,
)
from app.ferramentas.extratus_aburesi.core.config_manager import (
    atualizar_parametros_economia as _atualizar_parametros_economia_aburesi,
    carregar_config as _carregar_config_aburesi,
)
from app.ferramentas.extratus_aburesi.db.checagem_fila import (
    resolver_solicitantes as _resolver_solicitantes_aburesi,
)
from app.ferramentas.extratus_aburesi.db.jobs import (
    detalhar_custo_e_quantidade_por_usuario as _detalhar_custo_e_quantidade_por_usuario_aburesi,
    listar_jobs as _listar_jobs_aburesi,
    resumo_mes_atual as _resumo_mes_atual_aburesi,
    resumo_por_modelo as _resumo_por_modelo_aburesi,
    resumo_por_status_com_custo as _resumo_por_status_com_custo_aburesi,
    serie_temporal_custo as _serie_temporal_custo_aburesi,
    somar_custo_por_usuario as _somar_custo_por_usuario_aburesi,
)
from app.ferramentas.extratus_aburesi.web.rotulos import (
    rotulo_erro as _rotulo_erro_aburesi,
    rotulo_status as _rotulo_status_aburesi,
)
from app.plataforma.cambio import obter_cotacao_usd_brl
from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import listar_todas_ferramentas, listar_todos_usuarios
from app.plataforma.web.auth import exigir_admin
from app.plataforma.web.chaves_ferramentas import CHAVE_POR_SLUG
from app.plataforma.web.templates_util import criar_templates


PERIODOS_GRAFICO_VALIDOS = ("7d", "15d", "30d", "1a")


# Henrique, diretoria, 2026-08-24: a tela de custos de cada ferramenta
# morava (por engano de indexação, não de intenção) dentro da pasta de
# rotas da própria ferramenta, em /extratus/custos e
# /extratus-aburesi/custos — mesmo sendo 100% admin-only. Realocada pra
# valer dentro do admin de verdade, em /admin/custos/<chave>. Só entram
# aqui ferramentas que de fato têm custo de IA rastreado hoje — uma
# ferramenta nova sem isso ainda (ex: Crivus) não aparece
# na lista, mas também não quebra nada (ver CUSTOS_POR_CHAVE.get abaixo).
CUSTOS_POR_CHAVE = {
    "extratus-relatorios": {
        "nome": "Extratus - Relatórios",
        "slug_ferramenta": "extratus",
        # Prefixo real de URL da ferramenta (onde /download/{arquivo}
        # de fato mora, ver gerar_relatorio.py) — diferente da "chave"
        # usada nas URLs do admin (essa é a raiz travada em seed.py,
        # nunca pode mudar, ver [[extratus-duas-frentes]]).
        "url_base": "/extratus",
        "listar_jobs": _listar_jobs_extratus,
        "somar_custo_por_usuario": _somar_custo_por_usuario_extratus,
        "resumo_mes_atual": _resumo_mes_atual_extratus,
        "serie_temporal_custo": _serie_temporal_custo_extratus,
        "detalhar_custo_e_quantidade_por_usuario": _detalhar_custo_e_quantidade_por_usuario_extratus,
        "resumo_por_status_com_custo": _resumo_por_status_com_custo_extratus,
        "resumo_por_modelo": _resumo_por_modelo_extratus,
        "carregar_config": _carregar_config_extratus,
        "atualizar_parametros_economia": _atualizar_parametros_economia_extratus,
        "resolver_solicitantes": _resolver_solicitantes_extratus,
        "rotulo_status": _rotulo_status_extratus,
        "rotulo_erro": _rotulo_erro_extratus,
    },
    "extratus-aburesi": {
        "nome": "Extratus - Aburesi",
        "slug_ferramenta": "extratus-aburesi",
        "url_base": "/extratus-aburesi",
        "listar_jobs": _listar_jobs_aburesi,
        "somar_custo_por_usuario": _somar_custo_por_usuario_aburesi,
        "resumo_mes_atual": _resumo_mes_atual_aburesi,
        "serie_temporal_custo": _serie_temporal_custo_aburesi,
        "detalhar_custo_e_quantidade_por_usuario": _detalhar_custo_e_quantidade_por_usuario_aburesi,
        "resumo_por_status_com_custo": _resumo_por_status_com_custo_aburesi,
        "resumo_por_modelo": _resumo_por_modelo_aburesi,
        "carregar_config": _carregar_config_aburesi,
        "atualizar_parametros_economia": _atualizar_parametros_economia_aburesi,
        "resolver_solicitantes": _resolver_solicitantes_aburesi,
        "rotulo_status": _rotulo_status_aburesi,
        "rotulo_erro": _rotulo_erro_aburesi,
    },
}


router = APIRouter(dependencies=[Depends(exigir_admin)])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = criar_templates(TEMPLATES_DIR)


def _contexto_base(usuario):
    return {
        "usuario": usuario,
        "total_usuarios": len(listar_todos_usuarios()),
        "total_ferramentas": len(listar_todas_ferramentas()),
    }


@router.get("/admin/custos")
def pagina_custos_grade(request: Request, usuario: Usuario = Depends(exigir_admin)):
    ferramentas = listar_todas_ferramentas()

    custo_total_por_chave = {}
    for chave, entrada in CUSTOS_POR_CHAVE.items():
        custo_total_por_chave[chave] = sum(entrada["somar_custo_por_usuario"]().values())

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            **_contexto_base(usuario),
            "aba_ativa": "custos",
            "ferramentas": ferramentas,
            "chave_por_slug": CHAVE_POR_SLUG,
            "custos_por_chave": CUSTOS_POR_CHAVE,
            "custo_total_por_chave": custo_total_por_chave,
            "custo_total_geral": sum(custo_total_por_chave.values()),
            "cotacao": obter_cotacao_usd_brl(),
        },
    )


def _contexto_custos_detalhe(chave, entrada, usuario, erro_parametros_economia=None):
    """Monta o contexto inteiro da tela de Custos de UMA ferramenta —
    extraído da rota GET pra poder ser reaproveitado pela rota POST de
    parâmetros de economia (que precisa re-renderizar a mesma tela com
    um erro de validação, sem perder o resto do dashboard)."""
    jobs = entrada["listar_jobs"]()
    # Henrique, diretoria, 2026-08-27: "Robô automático" sozinho não diz
    # QUEM pediu aquele processo — `job.solicitante_id` já vem carregado
    # desde o upload na Fila do Robô pra relatório NOVO (ver
    # ChecagemFila.solicitante_id / checagem_fila.registrar_pendente,
    # repassado por toda a esteira). Relatório de ANTES dessa coluna
    # existir não tem como ter isso preenchido — `resolver_solicitantes`
    # cai pra dedução por nome+horário nesses casos (Henrique, mesmo dia:
    # "os relatórios que já estavam prontos agora estão como não
    # identificado... manter aquela solução de antes como fallback").
    info_por_id = {u.id: {"nome": u.nome, "login": u.nome_usuario} for u in listar_todos_usuarios()}
    solicitante_por_job_id = entrada["resolver_solicitantes"](jobs)
    detalhe_por_usuario = entrada["detalhar_custo_e_quantidade_por_usuario"]()

    dados_robo = detalhe_por_usuario.get(None, {"quantidade": 0, "custo": 0.0})
    custo_robo = dados_robo["custo"]
    custo_colaboradores = sum(
        dados["custo"] for usuario_id, dados in detalhe_por_usuario.items() if usuario_id is not None
    )
    custo_total = custo_robo + custo_colaboradores

    colaboradores = sorted(
        (
            {
                "id": usuario_id,
                "nome": info_por_id.get(usuario_id, {}).get("nome", f"Usuário #{usuario_id}"),
                "login": info_por_id.get(usuario_id, {}).get("login", ""),
                "custo": dados["custo"],
                "quantidade": dados["quantidade"],
                "custo_medio": dados["custo_medio"],
            }
            for usuario_id, dados in detalhe_por_usuario.items()
            if usuario_id is not None
        ),
        key=lambda item: item["custo"],
        reverse=True,
    )

    series_por_periodo = {
        periodo: entrada["serie_temporal_custo"](periodo) for periodo in PERIODOS_GRAFICO_VALIDOS
    }

    config = entrada["carregar_config"]()
    horas_estimadas_por_caso = config["horas_estimadas_por_caso"]
    valor_hora_profissional = config["valor_hora_profissional"]

    cotacao = obter_cotacao_usd_brl()

    resumo_mes = entrada["resumo_mes_atual"]()
    # horas_estimadas_por_caso/valor_hora_profissional já são em R$ (é
    # assim que o admin preenche o formulário) — custo_mes vem do banco
    # em US$ (mesma moeda de custo_estimado_usd). Precisa converter ANTES
    # de subtrair, senão mistura moeda (achado ao conferir a tela ao
    # vivo, 2026-08-26: a economia mostrada estava multiplicando por
    # cotação DUAS vezes de propósito nenhum, inflando o número).
    custo_manual_estimado_mes_reais = resumo_mes["quantidade_mes"] * horas_estimadas_por_caso * valor_hora_profissional
    custo_ia_mes_reais = resumo_mes["custo_mes"] * cotacao
    economia_estimada_mes_reais = custo_manual_estimado_mes_reais - custo_ia_mes_reais

    return {
        "usuario": usuario,
        "chave": chave,
        "nome_ferramenta": entrada["nome"],
        "url_base": entrada["url_base"],
        "jobs": jobs,
        "info_por_id": info_por_id,
        "solicitante_por_job_id": solicitante_por_job_id,
        "colaboradores": colaboradores,
        "custo_colaboradores": custo_colaboradores,
        "custo_robo": custo_robo,
        "custo_total": custo_total,
        "resumo_mes": resumo_mes,
        "series_por_periodo": series_por_periodo,
        "series_json": json.dumps({"series": series_por_periodo, "cotacao": cotacao}),
        "resumo_por_status": entrada["resumo_por_status_com_custo"](),
        "resumo_por_modelo": entrada["resumo_por_modelo"](),
        "horas_estimadas_por_caso": horas_estimadas_por_caso,
        "valor_hora_profissional": valor_hora_profissional,
        "economia_estimada_mes_reais": economia_estimada_mes_reais,
        "erro_parametros_economia": erro_parametros_economia,
        # Passados como valores de contexto (chamáveis no template),
        # não registrados em templates.env.filters — esse Jinja2Templates
        # é uma instância COMPARTILHADA por todo o router (módulo
        # inteiro), então mutar env.filters aqui misturaria o rótulo de
        # um módulo com uma requisição concorrente renderizando o outro.
        "rotulo_status": entrada["rotulo_status"],
        "rotulo_erro": entrada["rotulo_erro"],
        "cotacao": cotacao,
    }


@router.get("/admin/custos/{chave}")
def pagina_custos_detalhe(chave: str, request: Request, usuario: Usuario = Depends(exigir_admin)):
    entrada = CUSTOS_POR_CHAVE.get(chave)
    if entrada is None:
        raise HTTPException(status_code=404, detail="Essa ferramenta não tem tela de custos.")

    return templates.TemplateResponse(
        request,
        "admin_custos_detalhe.html",
        _contexto_custos_detalhe(chave, entrada, usuario),
    )


@router.post("/admin/custos/{chave}/parametros-economia")
def salvar_parametros_economia(
    chave: str,
    request: Request,
    horas_estimadas_por_caso: float = Form(...),
    valor_hora_profissional: float = Form(...),
    usuario: Usuario = Depends(exigir_admin),
):
    entrada = CUSTOS_POR_CHAVE.get(chave)
    if entrada is None:
        raise HTTPException(status_code=404, detail="Essa ferramenta não tem tela de custos.")

    try:
        entrada["atualizar_parametros_economia"](horas_estimadas_por_caso, valor_hora_profissional)
    except ValueError as erro:
        return templates.TemplateResponse(
            request,
            "admin_custos_detalhe.html",
            _contexto_custos_detalhe(chave, entrada, usuario, erro_parametros_economia=str(erro)),
        )

    return RedirectResponse(f"/admin/custos/{chave}", status_code=303)
