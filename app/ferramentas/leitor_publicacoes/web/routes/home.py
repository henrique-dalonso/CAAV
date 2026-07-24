from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.plataforma.web.auth import exigir_acesso_ferramenta


router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("leitor-publicacoes"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/")
def pagina_inicial(request: Request):
    return templates.TemplateResponse(
        request,
        "home.html",
        {},
    )
