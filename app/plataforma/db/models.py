from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class Usuario(SQLModel, table=True):
    """Um colaborador com acesso ao Centro de Experiência do Colaborador.

    eh_admin dá acesso automático a todas as ferramentas e (mais pra
    frente) à área administrativa — não precisa liberar ferramenta por
    ferramenta pra um admin.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    nome: str
    nome_usuario: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    senha_hash: str

    eh_admin: bool = False
    ativo: bool = True

    criado_em: datetime = Field(default_factory=datetime.now)


class Ferramenta(SQLModel, table=True):
    """Uma ferramenta disponível no Centro de Experiência (ex: Extratus)."""

    id: Optional[int] = Field(default=None, primary_key=True)

    nome: str
    slug: str = Field(unique=True, index=True)
    descricao: Optional[str] = None
    url: str


class UsuarioFerramenta(SQLModel, table=True):
    """Liga um usuário a uma ferramenta que ele tem permissão de usar."""

    usuario_id: Optional[int] = Field(
        default=None, foreign_key="usuario.id", primary_key=True
    )
    ferramenta_id: Optional[int] = Field(
        default=None, foreign_key="ferramenta.id", primary_key=True
    )
