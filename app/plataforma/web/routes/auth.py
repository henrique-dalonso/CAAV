from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.plataforma.auth import verificar_senha
from app.plataforma.db.tentativas_login import ip_esta_bloqueado, registrar_tentativa_falha
from app.plataforma.db.usuarios import (
    bloquear_usuario_por_tentativas,
    buscar_usuario_por_nome_usuario,
    incrementar_tentativas_falhas,
    resetar_tentativas_falhas,
)
from app.plataforma.web.templates_util import criar_templates


router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = criar_templates(TEMPLATES_DIR)

# 3 senhas erradas SEGUIDAS pro mesmo usuário bloqueia a conta (só um
# admin desbloqueia depois, na tela de Usuários) — trava independente da
# trava por IP em tentativas_login.py.
LIMITE_TENTATIVAS_USUARIO = 3

MENSAGEM_CONTA_BLOQUEADA = (
    "Esta conta foi bloqueada por excesso de tentativas erradas. "
    "Peça a um administrador para desbloquear."
)
MENSAGEM_REDE_BLOQUEADA = (
    "Muitas tentativas de login vindas desta rede. Tente novamente em alguns minutos."
)


def _ip_da_requisicao(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def _erro_login(request: Request, mensagem: str):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"erro": mensagem},
        status_code=401,
    )


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
    ip = _ip_da_requisicao(request)

    if ip_esta_bloqueado(ip):
        return _erro_login(request, MENSAGEM_REDE_BLOQUEADA)

    nome_login = usuario_login.strip().lower()
    usuario = buscar_usuario_por_nome_usuario(nome_login)

    # Bloqueado por tentativas: recusa mesmo que a senha digitada agora
    # esteja certa — só desbloqueio de admin reabre (ver desbloquear_usuario).
    if usuario and usuario.bloqueado:
        return _erro_login(request, MENSAGEM_CONTA_BLOQUEADA)

    if not usuario or not verificar_senha(senha, usuario.senha_hash):
        registrar_tentativa_falha(ip, nome_login)

        if usuario:
            total_falhas = incrementar_tentativas_falhas(usuario.id)
            if total_falhas >= LIMITE_TENTATIVAS_USUARIO:
                bloquear_usuario_por_tentativas(usuario.id)
                return _erro_login(request, MENSAGEM_CONTA_BLOQUEADA)

        if ip_esta_bloqueado(ip):
            return _erro_login(request, MENSAGEM_REDE_BLOQUEADA)

        return _erro_login(request, "Usuário ou senha incorretos.")

    resetar_tentativas_falhas(usuario.id)

    request.session["usuario_id"] = usuario.id
    request.session["usuario_nome"] = usuario.nome

    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
