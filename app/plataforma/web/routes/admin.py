from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

# A tela de admin ainda soma métricas direto das 2 ferramentas que já têm
# Job/custo hoje, em vez de algo genérico onde cada ferramenta expõe suas
# próprias métricas (não existe esse contrato ainda). Rodada 12,
# 2026-08-13: a tela de Custos ficava cega ao Aburesi (só importava do
# Extratus) — os dois entram aqui agora.
from app.ferramentas.extratus.db.jobs import (
    contar_por_status as _contar_por_status_extratus,
    somar_custo_por_usuario as _somar_custo_por_usuario_extratus,
)
from app.ferramentas.extratus_aburesi.db.jobs import (
    contar_por_status as _contar_por_status_aburesi,
    somar_custo_por_usuario as _somar_custo_por_usuario_aburesi,
)
from app.plataforma.auth import gerar_hash_senha
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.models import CARGO_COLABORADOR, CARGOS_VALIDOS, Ferramenta, Usuario
from app.plataforma.db.usuarios import (
    alternar_admin,
    alternar_ativo,
    atualizar_senha,
    criar_usuario,
    definir_cargo,
    definir_ferramentas,
    desbloquear_usuario,
    excluir_usuario,
    listar_ferramentas_admin_ids_por_usuario,
    listar_ferramentas_fila_ids_por_usuario,
    listar_ferramentas_liberadas_ids_por_usuario,
    listar_todos_usuarios,
)
from app.plataforma.web.auth import exigir_admin
from app.plataforma.web.templates_util import criar_templates
from sqlmodel import select


router = APIRouter(dependencies=[Depends(exigir_admin)])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = criar_templates(TEMPLATES_DIR)

TAMANHO_MINIMO_SENHA = 6


def _listar_ferramentas():
    with obter_sessao() as sessao:
        return sessao.exec(select(Ferramenta)).all()


def _redirecionar(destino, erro=None, sucesso=None):
    partes = []

    if erro:
        partes.append(f"erro={quote(erro)}")

    if sucesso:
        partes.append(f"sucesso={quote(sucesso)}")

    query = f"?{'&'.join(partes)}" if partes else ""

    return RedirectResponse(url=f"{destino}{query}", status_code=303)


def _contexto_base(usuario):
    """Dados que a barra lateral usa em toda aba (contagem de usuários e
    ferramentas nos emblemas) — computados sempre, independente de qual
    aba está ativa, mesmo padrão das abas do Extratus."""
    return {
        "usuario": usuario,
        "total_usuarios": len(listar_todos_usuarios()),
        "total_ferramentas": len(_listar_ferramentas()),
    }


@router.get("/admin")
def admin_raiz():
    return RedirectResponse(url="/admin/custos", status_code=303)


@router.get("/admin/custos")
def pagina_custos(
    request: Request,
    usuario: Usuario = Depends(exigir_admin),
    erro: str | None = None,
    sucesso: str | None = None,
):
    usuarios = listar_todos_usuarios()

    metricas_extratus = _contar_por_status_extratus()
    metricas_aburesi = _contar_por_status_aburesi()
    metricas = {
        chave: metricas_extratus.get(chave, 0) + metricas_aburesi.get(chave, 0)
        for chave in set(metricas_extratus) | set(metricas_aburesi)
    }

    custo_total = (
        sum(_somar_custo_por_usuario_extratus().values())
        + sum(_somar_custo_por_usuario_aburesi().values())
    )

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            **_contexto_base(usuario),
            "aba_ativa": "custos",
            "total_usuarios_ativos": sum(1 for u in usuarios if u.ativo),
            "metricas": metricas,
            "custo_total": custo_total,
            "erro": erro,
            "sucesso": sucesso,
        },
    )


# Henrique, 2026-08-11: "Custos" deixou de ser uma aba dentro de cada
# ferramenta — agora só se chega lá por aqui. Registro manual de quem
# tem uma tela própria e onde fica (mesmo padrão do
# REGISTRO_NOTIFICACOES em app/plataforma/web/notificacoes.py) — nem
# toda ferramenta tem uma ainda (ex: Leitor de Publicações), então só
# entram aqui as que já têm de verdade.
URL_CUSTOS_POR_FERRAMENTA = {
    "extratus": "/extratus/custos",
    "extratus-aburesi": "/extratus-aburesi/custos",
}


@router.get("/admin/ferramentas")
def pagina_ferramentas(request: Request, usuario: Usuario = Depends(exigir_admin)):
    ferramentas = _listar_ferramentas()

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            **_contexto_base(usuario),
            "aba_ativa": "ferramentas",
            "ferramentas_com_custos": [f for f in ferramentas if f.slug in URL_CUSTOS_POR_FERRAMENTA],
            "url_custos_por_ferramenta": URL_CUSTOS_POR_FERRAMENTA,
        },
    )


@router.get("/admin/usuarios/novo")
def pagina_novo_usuario(
    request: Request,
    usuario: Usuario = Depends(exigir_admin),
    erro: str | None = None,
):
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            **_contexto_base(usuario),
            "aba_ativa": "novo-usuario",
            "ferramentas": _listar_ferramentas(),
            "erro": erro,
        },
    )


@router.get("/admin/usuarios")
def pagina_usuarios(
    request: Request,
    usuario: Usuario = Depends(exigir_admin),
    erro: str | None = None,
    sucesso: str | None = None,
):
    usuarios = listar_todos_usuarios()
    ferramentas = _listar_ferramentas()

    # 3 consultas no TOTAL (não 3 por usuário listado) — cada função já
    # devolve um dict usuario_id -> set(ferramenta_id) pronto; .get com
    # default vazio cobre o usuário sem nenhuma ferramenta liberada.
    liberadas_bulk = listar_ferramentas_liberadas_ids_por_usuario()
    admin_bulk = listar_ferramentas_admin_ids_por_usuario()
    fila_bulk = listar_ferramentas_fila_ids_por_usuario()

    ferramentas_por_usuario = {u.id: liberadas_bulk.get(u.id, set()) for u in usuarios}
    ferramentas_admin_por_usuario = {u.id: admin_bulk.get(u.id, set()) for u in usuarios}
    ferramentas_fila_por_usuario = {u.id: fila_bulk.get(u.id, set()) for u in usuarios}

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            **_contexto_base(usuario),
            "aba_ativa": "usuarios",
            "usuarios": usuarios,
            "ferramentas": ferramentas,
            "ferramentas_por_usuario": ferramentas_por_usuario,
            "ferramentas_admin_por_usuario": ferramentas_admin_por_usuario,
            "ferramentas_fila_por_usuario": ferramentas_fila_por_usuario,
            "erro": erro,
            "sucesso": sucesso,
        },
    )


@router.post("/admin/usuarios")
def criar_usuario_route(
    nome: str = Form(...),
    nome_usuario: str = Form(...),
    email: str = Form(...),
    senha: str = Form(...),
    eh_admin: bool = Form(False),
    cargo: str = Form(CARGO_COLABORADOR),
    ferramenta_ids: list[int] = Form([]),
    ferramentas_admin_ids: list[int] = Form([]),
    ferramentas_fila_ids: list[int] = Form([]),
):
    if len(senha) < TAMANHO_MINIMO_SENHA:
        return _redirecionar(
            "/admin/usuarios/novo",
            erro=f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres.",
        )

    try:
        criar_usuario(
            nome=nome.strip(),
            nome_usuario=nome_usuario.strip().lower(),
            email=email.strip().lower(),
            senha=senha,
            eh_admin=eh_admin,
            cargo=cargo,
            ferramenta_ids=ferramenta_ids,
            ferramentas_admin_ids=ferramentas_admin_ids,
            ferramentas_fila_ids=ferramentas_fila_ids,
        )
    except ValueError as erro:
        return _redirecionar("/admin/usuarios/novo", erro=str(erro))

    return _redirecionar("/admin/usuarios", sucesso=f'Usuário "{nome.strip()}" criado.')


@router.post("/admin/usuarios/{usuario_id}/cargo")
def definir_cargo_route(usuario_id: int, cargo: str = Form(...), usuario: Usuario = Depends(exigir_admin)):
    if usuario_id == usuario.id:
        return _redirecionar("/admin/usuarios", erro="Não é possível alterar o cargo do próprio usuário.")

    if cargo not in CARGOS_VALIDOS:
        return _redirecionar("/admin/usuarios", erro="Cargo inválido.")

    definir_cargo(usuario_id, cargo)
    return _redirecionar("/admin/usuarios", sucesso="Cargo atualizado.")


@router.post("/admin/usuarios/{usuario_id}/ferramentas")
def atualizar_ferramentas_route(
    usuario_id: int,
    ferramenta_ids: list[int] = Form([]),
    ferramentas_admin_ids: list[int] = Form([]),
    ferramentas_fila_ids: list[int] = Form([]),
):
    definir_ferramentas(usuario_id, ferramenta_ids, ferramentas_admin_ids, ferramentas_fila_ids)
    return _redirecionar("/admin/usuarios", sucesso="Ferramentas atualizadas.")


@router.post("/admin/usuarios/{usuario_id}/alternar-ativo")
def alternar_ativo_route(usuario_id: int, usuario: Usuario = Depends(exigir_admin)):
    if usuario_id == usuario.id:
        return _redirecionar("/admin/usuarios", erro="Não é possível desativar o próprio usuário.")

    alternar_ativo(usuario_id)
    return _redirecionar("/admin/usuarios")


@router.post("/admin/usuarios/{usuario_id}/alternar-admin")
def alternar_admin_route(usuario_id: int, usuario: Usuario = Depends(exigir_admin)):
    if usuario_id == usuario.id:
        return _redirecionar("/admin/usuarios", erro="Não é possível alterar o admin do próprio usuário.")

    alternar_admin(usuario_id)
    return _redirecionar("/admin/usuarios")


@router.post("/admin/usuarios/{usuario_id}/excluir")
def excluir_usuario_route(usuario_id: int, usuario: Usuario = Depends(exigir_admin)):
    if usuario_id == usuario.id:
        return _redirecionar("/admin/usuarios", erro="Não é possível excluir o próprio usuário.")

    excluir_usuario(usuario_id)
    return _redirecionar("/admin/usuarios", sucesso="Usuário excluído.")


@router.post("/admin/usuarios/{usuario_id}/desbloquear")
def desbloquear_usuario_route(usuario_id: int):
    desbloquear_usuario(usuario_id)
    return _redirecionar("/admin/usuarios", sucesso="Usuário desbloqueado.")


@router.post("/admin/usuarios/{usuario_id}/redefinir-senha")
def redefinir_senha_route(
    usuario_id: int,
    nova_senha: str = Form(...),
    confirmar_senha: str = Form(...),
):
    if len(nova_senha) < TAMANHO_MINIMO_SENHA:
        return _redirecionar(
            "/admin/usuarios",
            erro=f"A nova senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres.",
        )

    if nova_senha != confirmar_senha:
        return _redirecionar("/admin/usuarios", erro="As senhas não coincidem.")

    atualizar_senha(usuario_id, gerar_hash_senha(nova_senha))

    return _redirecionar("/admin/usuarios", sucesso="Senha redefinida.")
