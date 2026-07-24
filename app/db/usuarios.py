from typing import Optional

from sqlmodel import select

from app.core.auth import gerar_hash_senha
from app.db.models import Ferramenta, Usuario, UsuarioFerramenta
from app.db.session import obter_sessao


def buscar_usuario_por_nome_usuario(nome_usuario: str) -> Optional[Usuario]:
    with obter_sessao() as sessao:
        consulta = select(Usuario).where(
            Usuario.nome_usuario == nome_usuario,
            Usuario.ativo == True,  # noqa: E712
        )
        return sessao.exec(consulta).first()


def buscar_usuario_por_id(usuario_id: int) -> Optional[Usuario]:
    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)

        if usuario and not usuario.ativo:
            return None

        return usuario


def usuario_tem_acesso(usuario: Usuario, slug_ferramenta: str) -> bool:
    if usuario.eh_admin:
        return True

    with obter_sessao() as sessao:
        consulta = (
            select(UsuarioFerramenta)
            .join(Ferramenta, Ferramenta.id == UsuarioFerramenta.ferramenta_id)
            .where(
                UsuarioFerramenta.usuario_id == usuario.id,
                Ferramenta.slug == slug_ferramenta,
            )
        )
        return sessao.exec(consulta).first() is not None


def listar_ferramentas_do_usuario(usuario: Usuario):
    with obter_sessao() as sessao:
        if usuario.eh_admin:
            return sessao.exec(select(Ferramenta)).all()

        consulta = (
            select(Ferramenta)
            .join(UsuarioFerramenta, UsuarioFerramenta.ferramenta_id == Ferramenta.id)
            .where(UsuarioFerramenta.usuario_id == usuario.id)
        )
        return sessao.exec(consulta).all()


def listar_todos_usuarios():
    with obter_sessao() as sessao:
        return sessao.exec(select(Usuario).order_by(Usuario.nome)).all()


def listar_ferramentas_liberadas_ids(usuario_id: int):
    with obter_sessao() as sessao:
        consulta = select(UsuarioFerramenta.ferramenta_id).where(
            UsuarioFerramenta.usuario_id == usuario_id
        )
        return set(sessao.exec(consulta).all())


def criar_usuario(nome, nome_usuario, email, senha, eh_admin, ferramenta_ids=None):
    with obter_sessao() as sessao:
        ja_existe = sessao.exec(
            select(Usuario).where(
                (Usuario.nome_usuario == nome_usuario) | (Usuario.email == email)
            )
        ).first()

        if ja_existe:
            raise ValueError("Já existe um usuário com esse nome de usuário ou e-mail.")

        usuario = Usuario(
            nome=nome,
            nome_usuario=nome_usuario,
            email=email,
            senha_hash=gerar_hash_senha(senha),
            eh_admin=eh_admin,
        )
        sessao.add(usuario)
        sessao.commit()
        sessao.refresh(usuario)

        for ferramenta_id in (ferramenta_ids or []):
            sessao.add(
                UsuarioFerramenta(usuario_id=usuario.id, ferramenta_id=ferramenta_id)
            )
        sessao.commit()

        return usuario


def definir_ferramentas(usuario_id, ferramenta_ids):
    with obter_sessao() as sessao:
        atuais = sessao.exec(
            select(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_id)
        ).all()

        for vinculo in atuais:
            sessao.delete(vinculo)

        for ferramenta_id in ferramenta_ids:
            sessao.add(
                UsuarioFerramenta(usuario_id=usuario_id, ferramenta_id=ferramenta_id)
            )

        sessao.commit()


def alternar_ativo(usuario_id):
    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)
        usuario.ativo = not usuario.ativo
        sessao.add(usuario)
        sessao.commit()
        return usuario.ativo


def alternar_admin(usuario_id):
    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)
        usuario.eh_admin = not usuario.eh_admin
        sessao.add(usuario)
        sessao.commit()
        return usuario.eh_admin
