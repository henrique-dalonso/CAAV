from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.ferramentas.extratus.db.jobs import listar_jobs
from app.plataforma.db.models import Usuario
from app.plataforma.web.auth import exigir_acesso_ferramenta


router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("extratus"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = Jinja2Templates(directory=[TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])


@router.get("/historico")
def pagina_historico(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus")),
):
    jobs = listar_jobs()

    return templates.TemplateResponse(
        request,
        "historico.html",
        {"usuario": usuario, "jobs": jobs},
    )
