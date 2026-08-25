from fastapi import Depends, HTTPException, Request

from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import (
    buscar_usuario_por_id,
    usuario_tem_acesso,
    usuario_tem_acesso_manual,
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

    # Reatribuir a mesma chave marca a sessão como "modificada" (ver
    # Session.__setitem__ do Starlette, que marca modified=True em
    # qualquer __setitem__, mesmo reatribuindo o mesmo valor) — isso faz
    # o SessionMiddleware reenviar o cookie com Max-Age novo a cada
    # requisição autenticada, "resetando o relógio" da expiração. Sem
    # isso, a sessão expiraria num prazo FIXO a partir do login, nunca
    # renovado pelo uso (ver SESSAO_MAX_IDADE_SEGUNDOS em main.py).
    # usuario_logado é chamado (via exigir_login) por praticamente toda
    # rota protegida do site — único lugar por onde passa qualquer
    # requisição de alguém logado, então basta tocar aqui.
    request.session["usuario_id"] = usuario_id

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


def exigir_acesso_manual(slug_ferramenta: str):
    """Fluxo Manual/URGENTE (Gerar Relatório URGENTE, Relatórios
    URGENTES) — Henrique, diretoria, 2026-08-19: restrito a quem tem
    acesso_manual (na prática, coordenadores), já que o Robô virou o
    modo padrão pra todo mundo com acesso à ferramenta. A Fila do Robô
    em si não tem mais um "exigir" próprio — usa exigir_acesso_ferramenta
    normal, igual Relatórios do Robô já fazia."""

    def dependencia(usuario: Usuario = Depends(exigir_login)) -> Usuario:
        if not usuario_tem_acesso_manual(usuario, slug_ferramenta):
            raise HTTPException(
                status_code=403,
                detail="Acesso restrito ao modo Manual/URGENTE.",
            )

        return usuario

    return dependencia
