from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from app.ferramentas.extratus.core import config_manager as _config_extratus
from app.ferramentas.extratus.core import prompt_manager as _prompt_extratus
from app.ferramentas.extratus.db.lotes import (
    listar_itens_do_lote as _listar_itens_do_lote_extratus,
    listar_lotes_em_andamento as _listar_lotes_em_andamento_extratus,
)
from app.ferramentas.extratus_aburesi.core import config_manager as _config_aburesi
from app.ferramentas.extratus_aburesi.core import prompt_manager as _prompt_aburesi
from app.ferramentas.extratus_aburesi.db.lotes import (
    listar_itens_do_lote as _listar_itens_do_lote_aburesi,
    listar_lotes_em_andamento as _listar_lotes_em_andamento_aburesi,
)
from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import listar_todas_ferramentas, listar_todos_usuarios
from app.plataforma.paths import PROJECT_ROOT
from app.plataforma.web.auth import exigir_admin
from app.plataforma.web.chaves_ferramentas import CHAVE_POR_SLUG
from app.plataforma.web.templates_util import criar_templates


# Henrique, diretoria, 2026-08-24: "Configurações do Robô" saiu de dentro
# de cada ferramenta (engrenagem própria, acessível a coordenador com
# admin_ferramenta) e virou parte do admin — configurar uma ferramenta
# agora exige ser admin da plataforma, sem meio-termo ("área extremamente
# sensível"). admin_ferramenta foi removido por completo (ver docstring
# de UsuarioFerramenta, db/models.py). Registro manual de qual ferramenta
# tem essa tela — mesmo padrão de CUSTOS_POR_CHAVE em admin_custos.py.
CONFIGURACOES_POR_CHAVE = {
    "extratus-relatorios": {
        "nome": "Extratus - Relatórios",
        "config_manager": _config_extratus,
        "prompt_manager": _prompt_extratus,
        "listar_lotes_em_andamento": _listar_lotes_em_andamento_extratus,
        "listar_itens_do_lote": _listar_itens_do_lote_extratus,
    },
    "extratus-aburesi": {
        "nome": "Extratus - Aburesi",
        "config_manager": _config_aburesi,
        "prompt_manager": _prompt_aburesi,
        "listar_lotes_em_andamento": _listar_lotes_em_andamento_aburesi,
        "listar_itens_do_lote": _listar_itens_do_lote_aburesi,
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


def _entrada_ou_404(chave):
    entrada = CONFIGURACOES_POR_CHAVE.get(chave)
    if entrada is None:
        raise HTTPException(status_code=404, detail="Essa ferramenta não tem configuração própria.")
    return entrada


@router.get("/admin/ferramentas")
def pagina_ferramentas_grade(request: Request, usuario: Usuario = Depends(exigir_admin)):
    ferramentas = listar_todas_ferramentas()

    robo_ativo_por_chave = {
        chave: entrada["config_manager"].carregar_config().get("robo_ativo", False)
        for chave, entrada in CONFIGURACOES_POR_CHAVE.items()
    }

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            **_contexto_base(usuario),
            "aba_ativa": "ferramentas",
            "ferramentas": ferramentas,
            "chave_por_slug": CHAVE_POR_SLUG,
            "configuracoes_por_chave": CONFIGURACOES_POR_CHAVE,
            "robo_ativo_por_chave": robo_ativo_por_chave,
        },
    )


@router.get("/admin/ferramentas/{chave}")
def pagina_ferramenta_detalhe(chave: str, request: Request, usuario: Usuario = Depends(exigir_admin), sucesso: str | None = None, erro: str | None = None):
    entrada = _entrada_ou_404(chave)

    config = entrada["config_manager"].carregar_config()
    config_form = entrada["config_manager"].carregar_config_bruto()

    lotes_em_andamento = [
        {"lote": lote, "total_itens": len(entrada["listar_itens_do_lote"](lote.id))}
        for lote in entrada["listar_lotes_em_andamento"]()
    ]

    return templates.TemplateResponse(
        request,
        "admin_ferramentas_detalhe.html",
        {
            "usuario": usuario,
            "chave": chave,
            "nome_ferramenta": entrada["nome"],
            "robo_ativo": config.get("robo_ativo", False),
            "config": config_form,
            "provedores_ia": entrada["config_manager"].PROVEDORES_IA_VALIDOS,
            "lotes_em_andamento": lotes_em_andamento,
            "extensao_prompt": entrada["prompt_manager"].extensao_esperada_prompt(),
            "sucesso": sucesso,
            "erro": erro,
        },
    )


@router.post("/admin/ferramentas/{chave}/alternar")
def alternar_robo_route(chave: str):
    entrada = _entrada_ou_404(chave)

    config = entrada["config_manager"].carregar_config()
    novo_estado = entrada["config_manager"].definir_robo_ativo(not config.get("robo_ativo", False))

    mensagem = "Robô ligado." if novo_estado else "Robô desligado."

    return RedirectResponse(
        url=f"/admin/ferramentas/{chave}?sucesso={quote(mensagem)}", status_code=303
    )


@router.get("/admin/ferramentas/{chave}/pastas")
def listar_pastas_route(chave: str, caminho: str | None = None):
    _entrada_ou_404(chave)

    base = Path(caminho) if caminho else PROJECT_ROOT

    if not base.exists() or not base.is_dir():
        base = PROJECT_ROOT

    try:
        pastas = sorted(
            p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")
        )
    except OSError:
        pastas = []

    pai = str(base.parent) if base.parent != base else None

    return {"caminho": str(base), "pai": pai, "pastas": pastas}


@router.post("/admin/ferramentas/{chave}/config")
def atualizar_config_robo_route(
    chave: str,
    pasta_entrada: str = Form(...),
    ia_provider: str = Form(...),
):
    entrada = _entrada_ou_404(chave)

    try:
        entrada["config_manager"].atualizar_config_robo(pasta_entrada=pasta_entrada, ia_provider=ia_provider)
    except ValueError as erro:
        return RedirectResponse(
            url=f"/admin/ferramentas/{chave}?erro={quote(str(erro))}", status_code=303
        )

    return RedirectResponse(
        url=f"/admin/ferramentas/{chave}?sucesso=" + quote("Configurações do Robô salvas."),
        status_code=303,
    )


@router.post("/admin/ferramentas/{chave}/prompt")
async def atualizar_prompt_robo_route(chave: str, arquivo: UploadFile = File(...)):
    entrada = _entrada_ou_404(chave)

    extensao_esperada = entrada["prompt_manager"].extensao_esperada_prompt()
    nome_seguro = Path(arquivo.filename).name

    if not nome_seguro.lower().endswith(extensao_esperada):
        return RedirectResponse(
            url=f"/admin/ferramentas/{chave}?erro=" + quote(
                f'"{nome_seguro}" não é um arquivo {extensao_esperada} — '
                f"só é permitido enviar o prompt nesse formato."
            ),
            status_code=303,
        )

    conteudo = await arquivo.read()

    try:
        entrada["prompt_manager"].substituir_instrucoes_relatorio(conteudo)
    except ValueError as erro:
        return RedirectResponse(
            url=f"/admin/ferramentas/{chave}?erro={quote(str(erro))}", status_code=303
        )

    return RedirectResponse(
        url=f"/admin/ferramentas/{chave}?sucesso=" + quote("Prompt de instruções atualizado."),
        status_code=303,
    )
