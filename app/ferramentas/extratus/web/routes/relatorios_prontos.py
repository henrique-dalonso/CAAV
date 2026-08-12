from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.ferramentas.extratus.db.jobs import listar_jobs_manuais
from app.ferramentas.extratus.web.rotulos import (
    contagem_nav_pendentes,
    contagem_nav_relatorios,
    rotulo_erro,
    rotulo_status,
)
from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import listar_todos_usuarios
from app.plataforma.web.auth import exigir_acesso_ferramenta
from app.plataforma.web.templates_util import criar_templates


router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("extratus"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])
templates.env.filters["rotulo_status"] = rotulo_status
templates.env.filters["rotulo_erro"] = rotulo_erro
# Contagem da aba "Gerar relatórios"/"Relatórios" — ver mesmo comentário
# em inbox.py.
templates.env.globals["contagem_nav_pendentes"] = contagem_nav_pendentes
templates.env.globals["contagem_nav_relatorios"] = contagem_nav_relatorios


@router.get("/relatorios")
def pagina_relatorios_prontos(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus")),
    processo: str | None = None,
):
    jobs = listar_jobs_manuais()
    nomes_por_id = {u.id: u.nome for u in listar_todos_usuarios()}

    return templates.TemplateResponse(
        request,
        "relatorios_prontos.html",
        {
            "usuario": usuario,
            "jobs": jobs,
            "aba_ativa": "relatorios",
            "nomes_por_id": nomes_por_id,
            # Deep-link vindo do botão "Ir ao relatório" (Conferências
            # manuais, web/routes/inbox.py) — pré-preenche a busca e dá
            # scroll/destaque no item certo, ver relatorios_prontos.js.
            "processo_busca": processo,
        },
    )
