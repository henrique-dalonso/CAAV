from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

from app.ferramentas.extratus.db.jobs import excluir_job, listar_jobs_manuais, marcar_notificacao_resolvida, obter_job
from app.ferramentas.extratus.web.rotulos import (
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
from app.plataforma.web.auth import exigir_acesso_manual, exigir_admin
from app.plataforma.web.templates_util import criar_templates


router = APIRouter(dependencies=[Depends(exigir_acesso_manual("extratus"))])

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


@router.get("/relatorios-urgentes")
def pagina_relatorios_manuais(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_manual("extratus")),
    processo: str | None = None,
    erro: str | None = None,
    sucesso: str | None = None,
):
    jobs = listar_jobs_manuais()
    nomes_por_id = {u.id: u.nome for u in listar_todos_usuarios()}

    # Renderiza PRIMEIRO, marca como visto DEPOIS — mesmo motivo de
    # gerar_relatorio.py (senão o badge dessa própria visita nunca apareceria).
    resposta = templates.TemplateResponse(
        request,
        "relatorios_manuais.html",
        {
            "usuario": usuario,
            "jobs": jobs,
            "nomes_por_id": nomes_por_id,
            # Deep-link vindo do botão "Ir ao relatório" (Conferências
            # manuais, web/routes/gerar_relatorio.py) — pré-preenche a busca e dá
            # scroll/destaque no item certo, ver relatorios_manuais.js.
            "processo_busca": processo,
            "erro": erro,
            "sucesso": sucesso,
        },
    )
    marcar_aba_vista(usuario.id, FERRAMENTA_SLUG, ABA_RELATORIOS)

    return resposta


@router.get("/relatorios-urgentes/{job_id}/pdf")
def ver_pdf_relatorio_route(job_id: int):
    """Abre o PDF original que gerou esse relatório, numa aba nova
    (Henrique, 2026-08-21: "de onde saiu o relatório, de que pdf de
    processo") — mesma ideia do "ver PDF" que Conferências já tem
    (gerar_relatorio.py), mas sem exigir ser o dono: essa tela é acervo
    compartilhado do escritório, diferente da fila pessoal de
    Conferências."""
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

    return RedirectResponse(url=f"/extratus/relatorios-urgentes{query}", status_code=303)


@router.post("/relatorios-urgentes/{job_id}/excluir")
def excluir_relatorio_route(job_id: int, usuario: Usuario = Depends(exigir_admin)):
    """Henrique, diretoria, 2026-08-21: só admin da plataforma exclui
    relatório de verdade (arquivo físico + PDF de origem + linha no
    banco) — coordenador com admin_ferramenta não conta, de propósito."""
    if not excluir_job(job_id):
        return _redirecionar(erro="Esse relatório não existe mais.")

    return _redirecionar(sucesso="Relatório excluído permanentemente.")


@router.post("/relatorios-urgentes/{job_id}/marcar-notificacao-resolvida")
def marcar_notificacao_resolvida_route(
    job_id: int,
    usuario: Usuario = Depends(exigir_acesso_manual("extratus")),
):
    """X (relatório "pronto" no sino) ou botão "Marcar como revisado"
    (card em revisão, aqui na tela) — os dois dispensam a mesma
    notificação por baixo (Job.notificacao_resolvida). Só o dono do
    relatório pode; 404 se não existir ou não for dele, mesmo padrão de
    dispensar_processamento_finalizado (gerar_relatorio.py)."""
    if not marcar_notificacao_resolvida(job_id, usuario.id):
        raise HTTPException(status_code=404, detail="Esse relatório não existe mais.")

    return {"ok": True}
