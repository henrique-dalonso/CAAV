from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.db.models import Usuario
from app.db.usuarios import listar_ferramentas_do_usuario
from app.web.auth import exigir_login


router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/")
def pagina_inicial(request: Request, usuario: Usuario = Depends(exigir_login)):
    ferramentas = listar_ferramentas_do_usuario(usuario)

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "usuario": usuario,
            "ferramentas": ferramentas,
        },
    )
