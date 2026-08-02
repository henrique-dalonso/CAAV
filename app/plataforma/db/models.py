from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


CARGO_COORDENADOR = "coordenador"
CARGO_COLABORADOR = "colaborador"
CARGOS_VALIDOS = (CARGO_COORDENADOR, CARGO_COLABORADOR)


class Usuario(SQLModel, table=True):
    """Um colaborador com acesso ao Centro de Experiência do Colaborador.

    eh_admin dá acesso automático a todas as ferramentas e à área
    administrativa (custos, criação de usuário, etc.) — nível supremo,
    reservado pra dev/diretoria. Não tem relação com "cargo" abaixo.

    cargo é a hierarquia normal do escritório, só relevante quando
    eh_admin é False:
    - "coordenador": todas as ferramentas liberadas por padrão (ainda
      ajustável por ferramenta), mas SEM acesso a custo — isso é só de
      admin. Mais permissões de coordenador vêm depois.
    - "colaborador": sem nenhuma ferramenta liberada por padrão, precisa
      que um coordenador (ou admin) libere.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    nome: str
    nome_usuario: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    senha_hash: str

    eh_admin: bool = False
    cargo: str = Field(default=CARGO_COLABORADOR)
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
    """Liga um usuário a uma ferramenta que ele tem permissão de usar.

    admin_ferramenta é um nível extra, só relevante pra coordenador (admin
    já vê tudo por causa de eh_admin, colaborador não deveria ter isso
    marcado) — dá acesso às abas administrativas DENTRO daquela ferramenta
    específica (ex: Custos e Motor no Extratus), sem dar acesso à área de
    Administração da plataforma inteira.

    fila_motor é outro nível extra, independente de admin_ferramenta —
    diferente dele, faz sentido pra colaborador também (ex: um estagiário
    responsável só por alimentar a fila do motor). Dá acesso à aba de fila
    (upload em lote pra pasta universal do motor), sem dar acesso a
    ligar/desligar o motor nem às configurações dele.
    """

    usuario_id: Optional[int] = Field(
        default=None, foreign_key="usuario.id", primary_key=True
    )
    ferramenta_id: Optional[int] = Field(
        default=None, foreign_key="ferramenta.id", primary_key=True
    )
    admin_ferramenta: bool = Field(default=False)
    fila_motor: bool = Field(default=False)
