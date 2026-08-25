from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from app.ferramentas.extratus.db.jobs import (
    listar_jobs as _listar_jobs_extratus,
    somar_custo_por_usuario as _somar_custo_por_usuario_extratus,
)
from app.ferramentas.extratus.web.rotulos import (
    rotulo_erro as _rotulo_erro_extratus,
    rotulo_status as _rotulo_status_extratus,
)
from app.ferramentas.extratus_aburesi.db.jobs import (
    listar_jobs as _listar_jobs_aburesi,
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


# Henrique, diretoria, 2026-08-24: a tela de custos de cada ferramenta
# morava (por engano de indexação, não de intenção) dentro da pasta de
# rotas da própria ferramenta, em /extratus/custos e
# /extratus-aburesi/custos — mesmo sendo 100% admin-only. Realocada pra
# valer dentro do admin de verdade, em /admin/custos/<chave>. Só entram
# aqui ferramentas que de fato têm custo de IA rastreado hoje — uma
# ferramenta nova sem isso ainda (ex: Leitor de Publicações) não aparece
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
        "rotulo_status": _rotulo_status_extratus,
        "rotulo_erro": _rotulo_erro_extratus,
    },
    "extratus-aburesi": {
        "nome": "Extratus - Aburesi",
        "slug_ferramenta": "extratus-aburesi",
        "url_base": "/extratus-aburesi",
        "listar_jobs": _listar_jobs_aburesi,
        "somar_custo_por_usuario": _somar_custo_por_usuario_aburesi,
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


@router.get("/admin/custos/{chave}")
def pagina_custos_detalhe(chave: str, request: Request, usuario: Usuario = Depends(exigir_admin)):
    entrada = CUSTOS_POR_CHAVE.get(chave)
    if entrada is None:
        raise HTTPException(status_code=404, detail="Essa ferramenta não tem tela de custos.")

    jobs = entrada["listar_jobs"]()
    info_por_id = {u.id: {"nome": u.nome, "login": u.nome_usuario} for u in listar_todos_usuarios()}
    custo_por_usuario = entrada["somar_custo_por_usuario"]()

    custo_robo = custo_por_usuario.get(None, 0.0)
    custo_colaboradores = sum(
        custo for usuario_id, custo in custo_por_usuario.items() if usuario_id is not None
    )
    custo_total = custo_robo + custo_colaboradores

    colaboradores = sorted(
        (
            {
                "id": usuario_id,
                "nome": info_por_id.get(usuario_id, {}).get("nome", f"Usuário #{usuario_id}"),
                "login": info_por_id.get(usuario_id, {}).get("login", ""),
                "custo": custo,
            }
            for usuario_id, custo in custo_por_usuario.items()
            if usuario_id is not None
        ),
        key=lambda item: item["nome"].lower(),
    )

    return templates.TemplateResponse(
        request,
        "admin_custos_detalhe.html",
        {
            "usuario": usuario,
            "chave": chave,
            "nome_ferramenta": entrada["nome"],
            "url_base": entrada["url_base"],
            "jobs": jobs,
            "info_por_id": info_por_id,
            "colaboradores": colaboradores,
            "custo_colaboradores": custo_colaboradores,
            "custo_robo": custo_robo,
            "custo_total": custo_total,
            # Passados como valores de contexto (chamáveis no template),
            # não registrados em templates.env.filters — esse Jinja2Templates
            # é uma instância COMPARTILHADA por todo o router (módulo
            # inteiro), então mutar env.filters aqui misturaria o rótulo de
            # um módulo com uma requisição concorrente renderizando o outro.
            "rotulo_status": entrada["rotulo_status"],
            "rotulo_erro": entrada["rotulo_erro"],
            "cotacao": obter_cotacao_usd_brl(),
        },
    )
