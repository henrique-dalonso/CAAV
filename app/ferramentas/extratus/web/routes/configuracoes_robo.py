from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from app.ferramentas.extratus.core.config_manager import (
    PROVEDORES_IA_VALIDOS,
    atualizar_config_robo,
    carregar_config,
    carregar_config_bruto,
    definir_robo_ativo,
)
from app.ferramentas.extratus.core.prompt_manager import (
    extensao_esperada_prompt,
    substituir_instrucoes_relatorio,
)
from app.ferramentas.extratus.db.lotes import listar_itens_do_lote, listar_lotes_em_andamento
from app.ferramentas.extratus.web.rotulos import (
    contagem_nav_conferencias_fila,
    contagem_nav_conferencias_manual,
    contagem_nav_relatorios,
    contagem_nav_relatorios_robo,
)
from app.plataforma.db.models import Usuario
from app.plataforma.paths import PROJECT_ROOT
from app.plataforma.web.auth import exigir_admin_ferramenta
from app.plataforma.web.templates_util import criar_templates


router = APIRouter(dependencies=[Depends(exigir_admin_ferramenta("extratus"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])
# Badges "+N" da navegação — ver mesmo comentário em gerar_relatorio.py.
templates.env.globals["contagem_nav_conferencias_manual"] = contagem_nav_conferencias_manual
templates.env.globals["contagem_nav_conferencias_fila"] = contagem_nav_conferencias_fila
templates.env.globals["contagem_nav_relatorios"] = contagem_nav_relatorios
templates.env.globals["contagem_nav_relatorios_robo"] = contagem_nav_relatorios_robo


@router.get("/configuracoes-robo")
def pagina_configuracoes_robo(
    request: Request,
    usuario: Usuario = Depends(exigir_admin_ferramenta("extratus")),
    sucesso: str | None = None,
    erro: str | None = None,
):
    config = carregar_config()
    config_form = carregar_config_bruto()

    lotes_em_andamento = [
        {"lote": lote, "total_itens": len(listar_itens_do_lote(lote.id))}
        for lote in listar_lotes_em_andamento()
    ]

    return templates.TemplateResponse(
        request,
        "configuracoes_robo.html",
        {
            "usuario": usuario,
            "robo_ativo": config.get("robo_ativo", False),
            "config": config_form,
            "provedores_ia": PROVEDORES_IA_VALIDOS,
            "lotes_em_andamento": lotes_em_andamento,
            "extensao_prompt": extensao_esperada_prompt(),
            "sucesso": sucesso,
            "erro": erro,
        },
    )


@router.post("/configuracoes-robo/alternar")
def alternar_robo_route():
    config = carregar_config()
    novo_estado = definir_robo_ativo(not config.get("robo_ativo", False))

    mensagem = "Robô ligado." if novo_estado else "Robô desligado."

    return RedirectResponse(
        url=f"/extratus/configuracoes-robo?sucesso={quote(mensagem)}", status_code=303
    )


@router.get("/configuracoes-robo/pastas")
def listar_pastas_route(
    caminho: str | None = None,
    usuario: Usuario = Depends(exigir_admin_ferramenta("extratus")),
):
    # Editar a pasta do robô é coisa de admin da plataforma — coordenador
    # com acesso ao Robô só liga/desliga, não escolhe a pasta.
    if not usuario.eh_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")

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


@router.post("/configuracoes-robo/config")
def atualizar_config_robo_route(
    pasta_entrada: str = Form(...),
    ia_provider: str = Form(...),
    usuario: Usuario = Depends(exigir_admin_ferramenta("extratus")),
):
    if not usuario.eh_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")

    try:
        atualizar_config_robo(pasta_entrada=pasta_entrada, ia_provider=ia_provider)
    except ValueError as erro:
        return RedirectResponse(
            url=f"/extratus/configuracoes-robo?erro={quote(str(erro))}", status_code=303
        )

    return RedirectResponse(
        url="/extratus/configuracoes-robo?sucesso=" + quote("Configurações do Robô salvas."),
        status_code=303,
    )


@router.post("/configuracoes-robo/prompt")
async def atualizar_prompt_robo_route(
    arquivo: UploadFile = File(...),
    usuario: Usuario = Depends(exigir_admin_ferramenta("extratus")),
):
    # Mesma regra das outras configs do robô (pasta, modo de IA): só
    # admin da plataforma, mesmo que o coordenador tenha acesso à página.
    if not usuario.eh_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")

    extensao_esperada = extensao_esperada_prompt()
    nome_seguro = Path(arquivo.filename).name

    if not nome_seguro.lower().endswith(extensao_esperada):
        return RedirectResponse(
            url="/extratus/configuracoes-robo?erro=" + quote(
                f'"{nome_seguro}" não é um arquivo {extensao_esperada} — '
                f"só é permitido enviar o prompt nesse formato."
            ),
            status_code=303,
        )

    conteudo = await arquivo.read()

    try:
        substituir_instrucoes_relatorio(conteudo)
    except ValueError as erro:
        return RedirectResponse(
            url=f"/extratus/configuracoes-robo?erro={quote(str(erro))}", status_code=303
        )

    return RedirectResponse(
        url="/extratus/configuracoes-robo?sucesso=" + quote("Prompt de instruções atualizado."),
        status_code=303,
    )
