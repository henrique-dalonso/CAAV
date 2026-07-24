from fastapi import Depends, HTTPException, Request

from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import buscar_usuario_por_id, usuario_tem_acesso


class NaoAutenticado(Exception):
    """Levantada quando uma rota protegida é acessada sem login.

    Um exception handler em app/web/main.py transforma isso num redirect
    pra tela de login.
    """


def usuario_logado(request: Request):
    usuario_id = request.session.get("usuario_id")

    if not usuario_id:
        return None

    return buscar_usuario_por_id(usuario_id)


def exigir_login(request: Request) -> Usuario:
    usuario = usuario_logado(request)

    if not usuario:
        raise NaoAutenticado()

    return usuario


def exigir_admin(usuario: Usuario = Depends(exigir_login)) -> Usuario:
    if not usuario.eh_admin:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito a administradores.",
        )

    return usuario


def exigir_acesso_ferramenta(slug_ferramenta: str):
    def dependencia(usuario: Usuario = Depends(exigir_login)) -> Usuario:
        if not usuario_tem_acesso(usuario, slug_ferramenta):
            raise HTTPException(
                status_code=403,
                detail="Você não tem permissão para usar esta ferramenta.",
            )

        return usuario

    return dependencia
