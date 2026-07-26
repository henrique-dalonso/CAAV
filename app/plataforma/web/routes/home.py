from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import listar_ferramentas_do_usuario
from app.plataforma.web.auth import exigir_login


router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def obter_saudacao():
    hora = datetime.now().hour

    if hora < 12:
        return "Bom dia"

    if hora < 18:
        return "Boa tarde"

    return "Boa noite"


@router.get("/")
def pagina_inicial(request: Request, usuario: Usuario = Depends(exigir_login)):
    ferramentas = listar_ferramentas_do_usuario(usuario)
    primeiro_nome = usuario.nome.split(" ")[0]

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "usuario": usuario,
            "primeiro_nome": primeiro_nome,
            "saudacao": obter_saudacao(),
            "ferramentas": ferramentas,
        },
    )
