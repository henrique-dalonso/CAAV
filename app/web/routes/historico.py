from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.db.jobs import listar_jobs
from app.web.auth import exigir_acesso_ferramenta


router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("extratus"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/historico")
def pagina_historico(request: Request):
    jobs = listar_jobs()

    return templates.TemplateResponse(
        request,
        "historico.html",
        {"jobs": jobs},
    )
