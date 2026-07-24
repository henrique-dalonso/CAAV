from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class Job(SQLModel, table=True):
    """Um registro de processamento de PDF — sucesso ou erro.

    Substitui os antigos historico_producao.json e relatorio_erros.json:
    um único lugar guardando o que aconteceu com cada PDF processado.
    Colunas de uso de IA (modelo, tokens, custo) entram quando a chamada
    real de IA for implementada — não faz sentido criá-las vazias agora.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    arquivo_pdf: str
    processo: Optional[str] = None

    status: str  # "sucesso", "revisao" ou "erro"
    confianca: Optional[str] = None  # "alta", "media" ou "revisao" — nível de confiança da detecção
    motivo_confianca: Optional[str] = None

    tipo_erro: Optional[str] = None
    erro_mensagem: Optional[str] = None

    relatorio_path: Optional[str] = None
    destino_pdf: Optional[str] = None

    criado_em: datetime = Field(default_factory=datetime.now)


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
