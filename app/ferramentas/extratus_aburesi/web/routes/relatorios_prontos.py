from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.ferramentas.extratus_aburesi.core.config_manager import carregar_config
from app.ferramentas.extratus_aburesi.core.pdf_manager import listar_pdfs
from app.ferramentas.extratus_aburesi.db.jobs import listar_jobs
from app.ferramentas.extratus_aburesi.web.rotulos import rotulo_erro, rotulo_status
from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import listar_todos_usuarios
from app.plataforma.web.auth import exigir_acesso_ferramenta
from app.plataforma.web.templates_util import criar_templates


router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("extratus-aburesi"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])
templates.env.filters["rotulo_status"] = rotulo_status
templates.env.filters["rotulo_erro"] = rotulo_erro


@router.get("/relatorios")
def pagina_relatorios_prontos(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus-aburesi")),
):
    jobs = listar_jobs()
    config = carregar_config()
    total_pendentes = len(listar_pdfs(config.get("pasta_entrada", "entrada_pdfs")))
    nomes_por_id = {u.id: u.nome for u in listar_todos_usuarios()}

    return templates.TemplateResponse(
        request,
        "relatorios_prontos.html",
        {
            "usuario": usuario,
            "jobs": jobs,
            "aba_ativa": "relatorios",
            "total_pendentes": total_pendentes,
            "nomes_por_id": nomes_por_id,
        },
    )
