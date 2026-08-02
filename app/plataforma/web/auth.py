from fastapi import Depends, HTTPException, Request

from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import (
    buscar_usuario_por_id,
    usuario_eh_admin_da_ferramenta,
    usuario_tem_acesso,
    usuario_tem_acesso_fila_motor,
)


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


def exigir_admin_ferramenta(slug_ferramenta: str):
    """Abas administrativas DENTRO de uma ferramenta (custos, motor...) —
    admin da plataforma sempre passa; coordenador só se foi liberado pra
    essa ferramenta específica (ver Usuario.eh_admin vs admin_ferramenta
    em UsuarioFerramenta)."""

    def dependencia(usuario: Usuario = Depends(exigir_login)) -> Usuario:
        if not usuario_eh_admin_da_ferramenta(usuario, slug_ferramenta):
            raise HTTPException(
                status_code=403,
                detail="Acesso restrito a administradores desta ferramenta.",
            )

        return usuario

    return dependencia


def exigir_acesso_fila_motor(slug_ferramenta: str):
    """Aba de Fila do motor — upload em lote pra pasta universal do
    motor. Mais frouxo que exigir_admin_ferramenta: colaborador também
    pode ter (ex: estagiário só alimentando a fila), sem dar acesso a
    ligar/desligar o motor nem às configs dele."""

    def dependencia(usuario: Usuario = Depends(exigir_login)) -> Usuario:
        if not usuario_tem_acesso_fila_motor(usuario, slug_ferramenta):
            raise HTTPException(
                status_code=403,
                detail="Acesso restrito a quem pode alimentar a fila do motor.",
            )

        return usuario

    return dependencia
