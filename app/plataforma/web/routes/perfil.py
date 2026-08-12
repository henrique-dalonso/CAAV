from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.plataforma.auth import gerar_hash_senha, verificar_senha
from app.plataforma.db.models import CORES_PERFIL_VALIDAS, TEMAS_VALIDOS, Usuario
from app.plataforma.db.usuarios import atualizar_cor_perfil, atualizar_senha, atualizar_tema
from app.plataforma.web.auth import exigir_login
from app.plataforma.web.templates_util import criar_templates


router = APIRouter(dependencies=[Depends(exigir_login)])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = criar_templates(TEMPLATES_DIR)

TAMANHO_MINIMO_SENHA = 6


def _redirecionar_senha(erro=None, sucesso=None):
    partes = []

    if erro:
        partes.append(f"erro={quote(erro)}")

    if sucesso:
        partes.append(f"sucesso={quote(sucesso)}")

    query = f"?{'&'.join(partes)}" if partes else ""

    return RedirectResponse(url=f"/perfil/senha{query}", status_code=303)


@router.get("/perfil")
def perfil_raiz():
    return RedirectResponse(url="/perfil/dados", status_code=303)


@router.get("/perfil/dados")
def pagina_dados(request: Request, usuario: Usuario = Depends(exigir_login)):
    return templates.TemplateResponse(
        request,
        "perfil.html",
        {"usuario": usuario, "aba_ativa": "dados"},
    )


@router.get("/perfil/senha")
def pagina_senha(
    request: Request,
    usuario: Usuario = Depends(exigir_login),
    erro: str | None = None,
    sucesso: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "perfil.html",
        {"usuario": usuario, "aba_ativa": "senha", "erro": erro, "sucesso": sucesso},
    )


@router.post("/perfil/senha")
def processar_senha(
    usuario: Usuario = Depends(exigir_login),
    senha_atual: str = Form(...),
    nova_senha: str = Form(...),
    confirmar_senha: str = Form(...),
):
    if not verificar_senha(senha_atual, usuario.senha_hash):
        return _redirecionar_senha(erro="Senha atual incorreta.")

    if nova_senha != confirmar_senha:
        return _redirecionar_senha(erro="A nova senha e a confirmação não são iguais.")

    if len(nova_senha) < TAMANHO_MINIMO_SENHA:
        return _redirecionar_senha(
            erro=f"A nova senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres."
        )

    atualizar_senha(usuario.id, gerar_hash_senha(nova_senha))

    return _redirecionar_senha(sucesso="Senha alterada com sucesso.")


@router.get("/perfil/preferencias")
def pagina_preferencias(request: Request, usuario: Usuario = Depends(exigir_login)):
    return templates.TemplateResponse(
        request,
        "perfil.html",
        {
            "usuario": usuario,
            "aba_ativa": "preferencias",
            "cores_perfil": CORES_PERFIL_VALIDAS,
        },
    )


@router.post("/perfil/preferencias/tema")
def processar_tema(
    usuario: Usuario = Depends(exigir_login),
    tema: str = Form(...),
):
    if tema not in TEMAS_VALIDOS:
        return RedirectResponse(url="/perfil/preferencias", status_code=303)

    atualizar_tema(usuario.id, tema)

    return RedirectResponse(url="/perfil/preferencias", status_code=303)


@router.post("/perfil/preferencias/cor")
def processar_cor_perfil(
    usuario: Usuario = Depends(exigir_login),
    cor: str = Form(...),
):
    if cor not in CORES_PERFIL_VALIDAS:
        return RedirectResponse(url="/perfil/preferencias", status_code=303)

    atualizar_cor_perfil(usuario.id, cor)

    return RedirectResponse(url="/perfil/preferencias", status_code=303)
