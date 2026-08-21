from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.ferramentas.extratus.db.jobs import excluir_job, listar_jobs_robo, marcar_notificacao_resolvida_robo
from app.ferramentas.extratus.web.rotulos import (
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


# "Relatórios do Robô" — repositório universal do que o ROBÔ já
# processou (pronto, em revisão ou com erro), separado da tela "Seus
# Relatórios" (só manuais) desde 2026-08-08. Henrique, 2026-08-11: acesso
# de VER esse acervo é do mesmo nível que "Seus Relatórios" (qualquer um
# com a ferramenta liberada, é acervo do escritório) — não precisa mais
# de acesso à Fila do Robô pra isso; Fila do Robô continua restrita,
# essa é só a permissão de alimentar/operar o Robô, não de ver o que
# ele já produziu.
router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("extratus"))])

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
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus")),
    processo: str | None = None,
    erro: str | None = None,
    sucesso: str | None = None,
):
    jobs = listar_jobs_robo()

    # Renderiza PRIMEIRO, marca como visto DEPOIS — mesmo motivo de
    # gerar_relatorio.py (senão o badge dessa própria visita nunca apareceria).
    resposta = templates.TemplateResponse(
        request,
        "relatorios_robo.html",
        {
            "usuario": usuario,
            "jobs": jobs,
            # Deep-link vindo do botão "Ir ao relatório" (Conferências
            # manuais, web/routes/gerar_relatorio.py, quando o duplicado é do
            # Robô) — pré-preenche a busca, troca pra aba certa
            # (Sucesso/Revisão/Erro) e dá scroll/destaque, ver
            # relatorios_robo.js.
            "processo_busca": processo,
            "erro": erro,
            "sucesso": sucesso,
        },
    )
    marcar_aba_vista(usuario.id, FERRAMENTA_SLUG, ABA_RELATORIOS_ROBO)

    return resposta


def _redirecionar(erro=None, sucesso=None):
    partes = []

    if erro:
        partes.append(f"erro={quote(erro)}")

    if sucesso:
        partes.append(f"sucesso={quote(sucesso)}")

    query = f"?{'&'.join(partes)}" if partes else ""

    return RedirectResponse(url=f"/extratus/relatorios-robo{query}", status_code=303)


@router.post("/relatorios-robo/{job_id}/excluir")
def excluir_relatorio_robo_route(job_id: int, usuario: Usuario = Depends(exigir_admin)):
    """Mesma regra do equivalente manual (relatorios_manuais.py): só
    admin da plataforma exclui de verdade."""
    if not excluir_job(job_id):
        return _redirecionar(erro="Esse relatório não existe mais.")

    return _redirecionar(sucesso="Relatório excluído permanentemente.")


@router.post("/relatorios-robo/{job_id}/marcar-notificacao-resolvida")
def marcar_notificacao_resolvida_robo_route(
    job_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus")),
):
    """X do "sucesso" do Robô na aba "Ferramentas" do sino — diferente
    do equivalente manual (relatorios_manuais.py), não tem dono: qualquer
    um com acesso à ferramenta pode dispensar (Henrique, diretoria,
    2026-08-19). "Revisão" e "erro" do Robô não têm esse botão de
    propósito, mesma exigência de "não pode sumir sozinho" que erro já
    tinha."""
    if not marcar_notificacao_resolvida_robo(job_id):
        raise HTTPException(status_code=404, detail="Esse relatório não existe mais.")

    return {"ok": True}
