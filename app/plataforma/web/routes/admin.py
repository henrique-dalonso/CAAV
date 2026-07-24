from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

# A tela de admin ainda mostra métricas/config específicas do Extratus
# diretamente, por ser a única ferramenta hoje. Quando existir uma segunda
# ferramenta, isso deve virar algo genérico (cada ferramenta expõe suas
# próprias métricas), em vez de importar direto de um app.ferramentas.X.
from app.ferramentas.extratus.core.config_manager import carregar_config
from app.ferramentas.extratus.db.jobs import contar_por_status
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.models import Ferramenta
from app.plataforma.db.usuarios import (
    alternar_admin,
    alternar_ativo,
    criar_usuario,
    definir_ferramentas,
    listar_ferramentas_liberadas_ids,
    listar_todos_usuarios,
)
from app.plataforma.web.auth import exigir_admin
from sqlmodel import select


router = APIRouter(dependencies=[Depends(exigir_admin)])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _listar_ferramentas():
    with obter_sessao() as sessao:
        return sessao.exec(select(Ferramenta)).all()


@router.get("/admin")
def pagina_admin(request: Request, erro: str | None = None):
    usuarios = listar_todos_usuarios()
    ferramentas = _listar_ferramentas()

    ferramentas_por_usuario = {
        usuario.id: listar_ferramentas_liberadas_ids(usuario.id)
        for usuario in usuarios
    }

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "usuarios": usuarios,
            "ferramentas": ferramentas,
            "ferramentas_por_usuario": ferramentas_por_usuario,
            "metricas": contar_por_status(),
            "config": carregar_config(),
            "erro": erro,
        },
    )


@router.post("/admin/usuarios")
def criar_usuario_route(
    nome: str = Form(...),
    nome_usuario: str = Form(...),
    email: str = Form(...),
    senha: str = Form(...),
    eh_admin: bool = Form(False),
    ferramenta_ids: list[int] = Form([]),
):
    try:
        criar_usuario(
            nome=nome.strip(),
            nome_usuario=nome_usuario.strip().lower(),
            email=email.strip().lower(),
            senha=senha,
            eh_admin=eh_admin,
            ferramenta_ids=ferramenta_ids,
        )
    except ValueError as erro:
        return RedirectResponse(url=f"/admin?erro={erro}", status_code=303)

    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/usuarios/{usuario_id}/ferramentas")
def atualizar_ferramentas_route(usuario_id: int, ferramenta_ids: list[int] = Form([])):
    definir_ferramentas(usuario_id, ferramenta_ids)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/usuarios/{usuario_id}/alternar-ativo")
def alternar_ativo_route(usuario_id: int):
    alternar_ativo(usuario_id)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/usuarios/{usuario_id}/alternar-admin")
def alternar_admin_route(usuario_id: int):
    alternar_admin(usuario_id)
    return RedirectResponse(url="/admin", status_code=303)
