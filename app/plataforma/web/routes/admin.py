from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

# A tela de admin ainda mostra métricas/config específicas do Extratus
# diretamente, por ser a única ferramenta hoje. Quando existir uma segunda
# ferramenta, isso deve virar algo genérico (cada ferramenta expõe suas
# próprias métricas), em vez de importar direto de um app.ferramentas.X.
from app.ferramentas.extratus.core.config_manager import carregar_config
from app.ferramentas.extratus.db.jobs import contar_por_status, somar_custo_por_usuario
from app.plataforma.auth import gerar_hash_senha
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.models import Ferramenta, Usuario
from app.plataforma.db.usuarios import (
    alternar_admin,
    alternar_ativo,
    atualizar_senha,
    criar_usuario,
    definir_ferramentas,
    listar_ferramentas_liberadas_ids,
    listar_todos_usuarios,
)
from app.plataforma.web.auth import exigir_admin
from app.plataforma.web.templates_util import criar_templates
from sqlmodel import select


router = APIRouter(dependencies=[Depends(exigir_admin)])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = criar_templates(TEMPLATES_DIR)

TAMANHO_MINIMO_SENHA = 8


def _listar_ferramentas():
    with obter_sessao() as sessao:
        return sessao.exec(select(Ferramenta)).all()


def _redirecionar_admin(erro=None, sucesso=None):
    partes = []

    if erro:
        partes.append(f"erro={quote(erro)}")

    if sucesso:
        partes.append(f"sucesso={quote(sucesso)}")

    query = f"?{'&'.join(partes)}" if partes else ""

    return RedirectResponse(url=f"/admin{query}", status_code=303)


@router.get("/admin")
def pagina_admin(
    request: Request,
    usuario: Usuario = Depends(exigir_admin),
    erro: str | None = None,
    sucesso: str | None = None,
):
    usuarios = listar_todos_usuarios()
    ferramentas = _listar_ferramentas()

    ferramentas_por_usuario = {
        usuario.id: listar_ferramentas_liberadas_ids(usuario.id)
        for usuario in usuarios
    }

    custo_por_usuario = somar_custo_por_usuario()
    custo_total = sum(custo_por_usuario.values())

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "usuario": usuario,
            "usuarios": usuarios,
            "ferramentas": ferramentas,
            "ferramentas_por_usuario": ferramentas_por_usuario,
            "total_usuarios_ativos": sum(1 for u in usuarios if u.ativo),
            "metricas": contar_por_status(),
            "custo_total": custo_total,
            "config": carregar_config(),
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
    ferramenta_ids: list[int] = Form([]),
):
    try:
        criar_usuario(
            nome=nome.strip(),
            nome_usuario=nome_usuario.strip().lower(),
            email=email.strip().lower(),
            senha=senha,
            eh_admin=eh_admin,
            ferramenta_ids=ferramenta_ids,
        )
    except ValueError as erro:
        return _redirecionar_admin(erro=str(erro))

    return _redirecionar_admin(sucesso=f'Usuário "{nome.strip()}" criado.')


@router.post("/admin/usuarios/{usuario_id}/ferramentas")
def atualizar_ferramentas_route(usuario_id: int, ferramenta_ids: list[int] = Form([])):
    definir_ferramentas(usuario_id, ferramenta_ids)
    return _redirecionar_admin(sucesso="Ferramentas atualizadas.")


@router.post("/admin/usuarios/{usuario_id}/alternar-ativo")
def alternar_ativo_route(usuario_id: int):
    alternar_ativo(usuario_id)
    return _redirecionar_admin()


@router.post("/admin/usuarios/{usuario_id}/alternar-admin")
def alternar_admin_route(usuario_id: int):
    alternar_admin(usuario_id)
    return _redirecionar_admin()


@router.post("/admin/usuarios/{usuario_id}/redefinir-senha")
def redefinir_senha_route(usuario_id: int, nova_senha: str = Form(...)):
    if len(nova_senha) < TAMANHO_MINIMO_SENHA:
        return _redirecionar_admin(
            erro=f"A nova senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres."
        )

    atualizar_senha(usuario_id, gerar_hash_senha(nova_senha))

    return _redirecionar_admin(sucesso="Senha redefinida.")
