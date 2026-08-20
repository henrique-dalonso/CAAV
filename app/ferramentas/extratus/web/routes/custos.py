from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.ferramentas.extratus.db.jobs import listar_jobs, somar_custo_por_usuario
from app.ferramentas.extratus.web.rotulos import rotulo_erro, rotulo_status
from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import listar_todos_usuarios
from app.plataforma.web.auth import exigir_admin
from app.plataforma.web.templates_util import criar_templates


# Henrique, 2026-08-11: Custos deixou de ser uma aba dentro do Extratus —
# só é alcançável pelo painel de Administração (/admin/ferramentas), que
# já exige admin da PLATAFORMA inteira. "Admin da ferramenta" (um
# coordenador liberado só numa ferramenta específica) não abre mais essa
# porta — só continua valendo pra Configurações do Robô (ver robô.py).
router = APIRouter(dependencies=[Depends(exigir_admin)])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])
templates.env.filters["rotulo_status"] = rotulo_status
templates.env.filters["rotulo_erro"] = rotulo_erro


@router.get("/custos")
def pagina_custos(
    request: Request,
    usuario: Usuario = Depends(exigir_admin),
):
    jobs = listar_jobs()
    info_por_id = {u.id: {"nome": u.nome, "login": u.nome_usuario} for u in listar_todos_usuarios()}
    custo_por_usuario = somar_custo_por_usuario()

    custo_robo = custo_por_usuario.get(None, 0.0)
    custo_colaboradores = sum(
        custo for usuario_id, custo in custo_por_usuario.items() if usuario_id is not None
    )
    custo_total = custo_robo + custo_colaboradores

    colaboradores = sorted(
        (
            {
                "id": usuario_id,
                "nome": info_por_id.get(usuario_id, {}).get("nome", f"Usuário #{usuario_id}"),
                "login": info_por_id.get(usuario_id, {}).get("login", ""),
                "custo": custo,
            }
            for usuario_id, custo in custo_por_usuario.items()
            if usuario_id is not None
        ),
        key=lambda item: item["nome"].lower(),
    )

    return templates.TemplateResponse(
        request,
        "custos.html",
        {
            "usuario": usuario,
            "jobs": jobs,
            "info_por_id": info_por_id,
            "colaboradores": colaboradores,
            "custo_colaboradores": custo_colaboradores,
            "custo_robo": custo_robo,
            "custo_total": custo_total,
        },
    )
