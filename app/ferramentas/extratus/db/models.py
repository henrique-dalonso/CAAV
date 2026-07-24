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
