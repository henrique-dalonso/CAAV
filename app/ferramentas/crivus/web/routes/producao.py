from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.ferramentas.crivus.config.taxonomia import RÓTULO_CONFIANÇA_FEMININO, confianca_feminino
from app.ferramentas.crivus.db.analises import contar_analises, listar_analises, listar_solicitantes_ids
from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import listar_todos_usuarios, usuario_tem_acesso_lote
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
    aba: str = "lotes",
    filtro: str = "pendentes",
    pagina: int = 1,
    busca: str = "",
    # Henrique, diretoria, 2026-09-15: str, não `date | None`/`int | None`
    # direto no parâmetro — o <form> manda os campos vazios como string
    # vazia (""), não omitidos, e o FastAPI tenta converter "" num date/
    # int de verdade e quebra com 422 antes mesmo de chegar aqui (achado
    # testando de propósito na tela, não só com querystring válida
    # direto no teste automatizado). Conversão manual abaixo trata ""
    # como "sem filtro".
    data_de: str = "",
    data_ate: str = "",
    solicitante_id: str = "",
    nivel_confianca: str = "",
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    if aba not in ABAS_VALIDAS:
        aba = "lotes"
    if filtro not in FILTROS_VALIDOS:
        filtro = "pendentes"
    if pagina < 1:
        pagina = 1

    try:
        data_de = date.fromisoformat(data_de) if data_de else None
    except ValueError:
        data_de = None
    try:
        data_ate = date.fromisoformat(data_ate) if data_ate else None
    except ValueError:
        data_ate = None
    try:
        solicitante_id = int(solicitante_id) if solicitante_id else None
    except ValueError:
        solicitante_id = None
    # Henrique, diretoria, 2026-09-16: conjunto fechado (ALTO/MÉDIO/
    # BAIXO) — qualquer coisa fora disso é ignorada silenciosamente, sem
    # 422, mesmo espírito das outras conversões manuais acima.
    if nivel_confianca not in RÓTULO_CONFIANÇA_FEMININO:
        nivel_confianca = ""

    status = STATUS_POR_FILTRO[filtro]
    origem = "lote" if aba == "lotes" else "individual"
    offset = (pagina - 1) * POR_PAGINA

    analises = listar_analises(
        origem, status, limite=POR_PAGINA, offset=offset,
        busca=busca, data_de=data_de, data_ate=data_ate, solicitante_id=solicitante_id,
        nivel_confianca=nivel_confianca or None,
    )
    total = contar_analises(
        origem, status, busca=busca, data_de=data_de, data_ate=data_ate, solicitante_id=solicitante_id,
        nivel_confianca=nivel_confianca or None,
    )

    todos_usuarios = listar_todos_usuarios()
    nomes_por_usuario_id = {u.id: u.nome for u in todos_usuarios}

    # Henrique, diretoria, 2026-09-15: "mesmo comportamento do Extratus" —
    # dropdown só com quem de fato tem caso nessa aba+filtro, não a base
    # de usuários inteira.
    ids_com_caso = listar_solicitantes_ids(origem, status)
    usuarios_disponiveis = sorted(
        (u for u in todos_usuarios if u.id in ids_com_caso),
        key=lambda u: u.nome.lower(),
    )

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
            "pode_lote": usuario_tem_acesso_lote(usuario, "leitor-publicacoes"),
            "busca": busca,
            "data_de": data_de,
            "data_ate": data_ate,
            "solicitante_id": solicitante_id,
            "usuarios_disponiveis": usuarios_disponiveis,
            "nivel_confianca": nivel_confianca,
            "niveis_confianca_disponiveis": list(RÓTULO_CONFIANÇA_FEMININO.keys()),
        },
    )
