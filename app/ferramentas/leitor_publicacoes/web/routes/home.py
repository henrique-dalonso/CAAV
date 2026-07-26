from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.plataforma.db.models import Usuario
from app.plataforma.web.auth import exigir_acesso_ferramenta
from app.plataforma.web.templates_util import criar_templates


router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("leitor-publicacoes"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])


@router.get("/")
def pagina_inicial(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    return templates.TemplateResponse(
        request,
        "home.html",
        {"usuario": usuario},
    )
