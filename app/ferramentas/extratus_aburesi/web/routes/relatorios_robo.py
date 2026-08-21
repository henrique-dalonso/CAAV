from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

from app.ferramentas.extratus_aburesi.db.jobs import excluir_job, listar_jobs_robo, marcar_notificacao_resolvida_robo, obter_job
from app.ferramentas.extratus_aburesi.web.rotulos import (
    ABA_RELATORIOS_ROBO,
    FERRAMENTA_SLUG,
    contagem_nav_conferencias_fila,
    contagem_nav_conferencias_manual,
    contagem_nav_relatorios,
    contagem_nav_relatorios_robo,
    rotulo_erro,
    rotulo_status,
)
from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import marcar_aba_vista
from app.plataforma.web.auth import exigir_acesso_ferramenta, exigir_admin
from app.plataforma.web.templates_util import criar_templates


# Ver docstring equivalente em app/ferramentas/extratus/web/routes/
# relatorios_robo.py (Extratus - Relatórios) — mesma lógica.
router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("extratus-aburesi"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])
templates.env.filters["rotulo_status"] = rotulo_status
templates.env.filters["rotulo_erro"] = rotulo_erro
templates.env.globals["contagem_nav_conferencias_manual"] = contagem_nav_conferencias_manual
templates.env.globals["contagem_nav_conferencias_fila"] = contagem_nav_conferencias_fila
templates.env.globals["contagem_nav_relatorios"] = contagem_nav_relatorios
templates.env.globals["contagem_nav_relatorios_robo"] = contagem_nav_relatorios_robo


@router.get("/relatorios-robo")
def pagina_relatorios_robo(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus-aburesi")),
    processo: str | None = None,
    erro: str | None = None,
    sucesso: str | None = None,
):
    jobs = listar_jobs_robo()

    # Renderiza PRIMEIRO, marca como visto DEPOIS — ver comentário
    # equivalente em app/ferramentas/extratus/web/routes/relatorios_robo.py.
    resposta = templates.TemplateResponse(
        request,
        "relatorios_robo.html",
        {
            "usuario": usuario,
            "jobs": jobs,
            "processo_busca": processo,
            "erro": erro,
            "sucesso": sucesso,
        },
    )
    marcar_aba_vista(usuario.id, FERRAMENTA_SLUG, ABA_RELATORIOS_ROBO)

    return resposta


@router.get("/relatorios-robo/{job_id}/pdf")
def ver_pdf_relatorio_robo_route(job_id: int):
    """Ver docstring equivalente em app/ferramentas/extratus/web/routes/
    relatorios_robo.py (Extratus - Relatórios) — mesma lógica."""
    job = obter_job(job_id)

    if not job or not job.destino_pdf:
        raise HTTPException(status_code=404, detail="PDF de origem não encontrado.")

    caminho = Path(job.destino_pdf)

    if not caminho.exists():
        raise HTTPException(status_code=404, detail="PDF de origem não encontrado.")

    return FileResponse(caminho, media_type="application/pdf")


def _redirecionar(erro=None, sucesso=None):
    partes = []

    if erro:
        partes.append(f"erro={quote(erro)}")

    if sucesso:
        partes.append(f"sucesso={quote(sucesso)}")

    query = f"?{'&'.join(partes)}" if partes else ""

    return RedirectResponse(url=f"/extratus-aburesi/relatorios-robo{query}", status_code=303)


@router.post("/relatorios-robo/{job_id}/excluir")
def excluir_relatorio_robo_route(job_id: int, usuario: Usuario = Depends(exigir_admin)):
    """Ver docstring equivalente em app/ferramentas/extratus/web/routes/
    relatorios_robo.py (Extratus - Relatórios) — mesma lógica."""
    if not excluir_job(job_id):
        return _redirecionar(erro="Esse relatório não existe mais.")

    return _redirecionar(sucesso="Relatório excluído permanentemente.")


@router.post("/relatorios-robo/{job_id}/marcar-notificacao-resolvida")
def marcar_notificacao_resolvida_robo_route(
    job_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus-aburesi")),
):
    """Ver docstring equivalente em app/ferramentas/extratus/web/routes/
    relatorios_robo.py (Extratus - Relatórios) — mesma lógica."""
    if not marcar_notificacao_resolvida_robo(job_id):
        raise HTTPException(status_code=404, detail="Esse relatório não existe mais.")

    return {"ok": True}
