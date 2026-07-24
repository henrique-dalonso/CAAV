from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.plataforma.auth import verificar_senha
from app.plataforma.db.usuarios import buscar_usuario_por_nome_usuario


router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/login")
def pagina_login(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"erro": None},
    )


@router.post("/login")
def processar_login(
    request: Request,
    usuario_login: str = Form(...),
    senha: str = Form(...),
):
    usuario = buscar_usuario_por_nome_usuario(usuario_login.strip().lower())

    if not usuario or not verificar_senha(senha, usuario.senha_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"erro": "E-mail ou senha incorretos."},
            status_code=401,
        )

    request.session["usuario_id"] = usuario.id
    request.session["usuario_nome"] = usuario.nome

    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
