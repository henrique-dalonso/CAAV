from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.ferramentas.crivus.config.taxonomia import confianca_feminino
from app.ferramentas.crivus.db.analises import contar_analises, listar_analises
from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import listar_todos_usuarios
from app.plataforma.web.auth import exigir_acesso_ferramenta
from app.plataforma.web.templates_util import criar_templates


router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("leitor-publicacoes"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])
templates.env.filters["confianca_feminino"] = confianca_feminino

ABAS_VALIDAS = {"individuais", "lotes"}
FILTROS_VALIDOS = {"pendentes", "concluidos"}
STATUS_POR_FILTRO = {"pendentes": "aguardando_revisao", "concluidos": "concluido"}

# Henrique, 2026-09-12: sem restrição de visualização no Crivus — o acervo
# é do escritório inteiro. 50 por página é um tamanho confortável hoje
# (volume real ainda é pequeno); "Lotes" pode crescer bastante quando o
# Processamento em Lote existir, mas isso é um problema pra quando essa
# aba de fato tiver dados.
POR_PAGINA = 50


@router.get("/producao")
def pagina_producao(
    request: Request,
    aba: str = "individuais",
    filtro: str = "pendentes",
    pagina: int = 1,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    if aba not in ABAS_VALIDAS:
        aba = "individuais"
    if filtro not in FILTROS_VALIDOS:
        filtro = "pendentes"
    if pagina < 1:
        pagina = 1

    status = STATUS_POR_FILTRO[filtro]
    origem = "lote" if aba == "lotes" else "individual"
    offset = (pagina - 1) * POR_PAGINA

    analises = listar_analises(origem, status, limite=POR_PAGINA, offset=offset)
    total = contar_analises(origem, status)

    nomes_por_usuario_id = {u.id: u.nome for u in listar_todos_usuarios()}

    return templates.TemplateResponse(
        request,
        "producao.html",
        {
            "usuario": usuario,
            "aba": aba,
            "filtro": filtro,
            "analises": analises,
            "nomes_por_usuario_id": nomes_por_usuario_id,
            "pagina": pagina,
            "total": total,
            "tem_proxima_pagina": offset + POR_PAGINA < total,
            "eh_lotes": aba == "lotes",
        },
    )
