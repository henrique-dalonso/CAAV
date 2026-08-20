from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from app.ferramentas.extratus_aburesi.db.jobs import listar_jobs_manuais, marcar_notificacao_resolvida
from app.ferramentas.extratus_aburesi.web.rotulos import (
    ABA_RELATORIOS,
    FERRAMENTA_SLUG,
    contagem_nav_conferencias_fila,
    contagem_nav_conferencias_manual,
    contagem_nav_relatorios,
    contagem_nav_relatorios_robo,
    rotulo_erro,
    rotulo_status,
)
from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import listar_todos_usuarios, marcar_aba_vista
from app.plataforma.web.auth import exigir_acesso_manual
from app.plataforma.web.templates_util import criar_templates


router = APIRouter(dependencies=[Depends(exigir_acesso_manual("extratus-aburesi"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])
templates.env.filters["rotulo_status"] = rotulo_status
templates.env.filters["rotulo_erro"] = rotulo_erro
# Badges "+N" da navegação — ver mesmo comentário em gerar_relatorio.py.
templates.env.globals["contagem_nav_conferencias_manual"] = contagem_nav_conferencias_manual
templates.env.globals["contagem_nav_conferencias_fila"] = contagem_nav_conferencias_fila
templates.env.globals["contagem_nav_relatorios"] = contagem_nav_relatorios
templates.env.globals["contagem_nav_relatorios_robo"] = contagem_nav_relatorios_robo


@router.get("/relatorios")
def pagina_relatorios_manuais(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_manual("extratus-aburesi")),
    processo: str | None = None,
):
    jobs = listar_jobs_manuais()
    nomes_por_id = {u.id: u.nome for u in listar_todos_usuarios()}

    # Renderiza PRIMEIRO, marca como visto DEPOIS — ver comentário
    # equivalente em app/ferramentas/extratus/web/routes/relatorios_manuais.py.
    resposta = templates.TemplateResponse(
        request,
        "relatorios_manuais.html",
        {
            "usuario": usuario,
            "jobs": jobs,
            "nomes_por_id": nomes_por_id,
            "processo_busca": processo,
        },
    )
    marcar_aba_vista(usuario.id, FERRAMENTA_SLUG, ABA_RELATORIOS)

    return resposta


@router.post("/relatorios/{job_id}/marcar-notificacao-resolvida")
def marcar_notificacao_resolvida_route(
    job_id: int,
    usuario: Usuario = Depends(exigir_acesso_manual("extratus-aburesi")),
):
    """Ver docstring equivalente em app/ferramentas/extratus/web/routes/
    relatorios_manuais.py (Extratus - Relatórios) — mesma lógica."""
    if not marcar_notificacao_resolvida(job_id, usuario.id):
        raise HTTPException(status_code=404, detail="Esse relatório não existe mais.")

    return {"ok": True}
