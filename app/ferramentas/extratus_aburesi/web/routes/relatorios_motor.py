from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.ferramentas.extratus_aburesi.db.jobs import listar_jobs_motor
from app.ferramentas.extratus_aburesi.web.rotulos import (
    contagem_nav_pendentes,
    contagem_nav_relatorios,
    rotulo_erro,
    rotulo_status,
)
from app.plataforma.db.models import Usuario
from app.plataforma.web.auth import exigir_acesso_ferramenta
from app.plataforma.web.templates_util import criar_templates


# Ver docstring equivalente em app/ferramentas/extratus/web/routes/
# relatorios_motor.py (Extratus - Relatórios) — mesma lógica.
router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("extratus-aburesi"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])
templates.env.filters["rotulo_status"] = rotulo_status
templates.env.filters["rotulo_erro"] = rotulo_erro
templates.env.globals["contagem_nav_pendentes"] = contagem_nav_pendentes
templates.env.globals["contagem_nav_relatorios"] = contagem_nav_relatorios


@router.get("/relatorios-finalizados")
def pagina_relatorios_finalizados(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus-aburesi")),
    processo: str | None = None,
):
    jobs = listar_jobs_motor()

    return templates.TemplateResponse(
        request,
        "relatorios_motor.html",
        {
            "usuario": usuario,
            "jobs": jobs,
            "processo_busca": processo,
        },
    )
