from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.ferramentas.extratus.db.jobs import listar_jobs_motor
from app.ferramentas.extratus.web.rotulos import (
    contagem_nav_pendentes,
    contagem_nav_relatorios,
    rotulo_erro,
    rotulo_status,
)
from app.plataforma.db.models import Usuario
from app.plataforma.web.auth import exigir_acesso_ferramenta
from app.plataforma.web.templates_util import criar_templates


# "Relatórios do Motor" — repositório universal do que o MOTOR já
# processou (pronto, em revisão ou com erro), separado da tela "Seus
# Relatórios" (só manuais) desde 2026-08-08. Henrique, 2026-08-11: acesso
# de VER esse acervo é do mesmo nível que "Seus Relatórios" (qualquer um
# com a ferramenta liberada, é acervo do escritório) — não precisa mais
# de acesso à Fila do Motor pra isso; Fila do Motor continua restrita,
# essa é só a permissão de alimentar/operar o Motor, não de ver o que
# ele já produziu.
router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("extratus"))])

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
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus")),
    processo: str | None = None,
):
    jobs = listar_jobs_motor()

    return templates.TemplateResponse(
        request,
        "relatorios_motor.html",
        {
            "usuario": usuario,
            "jobs": jobs,
            # Deep-link vindo do botão "Ir ao relatório" (Conferências
            # manuais, web/routes/inbox.py, quando o duplicado é do
            # Motor) — pré-preenche a busca, troca pra aba certa
            # (Sucesso/Revisão/Erro) e dá scroll/destaque, ver
            # relatorios_motor.js.
            "processo_busca": processo,
        },
    )
