from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class Job(SQLModel, table=True):
    """Um registro de processamento de PDF — sucesso ou erro.

    Substitui os antigos historico_producao.json e relatorio_erros.json:
    um único lugar guardando o que aconteceu com cada PDF processado.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    usuario_id: Optional[int] = Field(default=None, foreign_key="usuario.id")

    arquivo_pdf: str
    processo: Optional[str] = None

    status: str  # "sucesso", "revisao" ou "erro"
    confianca: Optional[str] = None  # "alta", "media" ou "revisao" — nível de confiança da detecção
    motivo_confianca: Optional[str] = None

    tipo_erro: Optional[str] = None
    erro_mensagem: Optional[str] = None

    relatorio_path: Optional[str] = None
    destino_pdf: Optional[str] = None

    # Uso de IA — preenchido só quando ia_provider != "simulado"
    modelo_ia: Optional[str] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None
    custo_estimado_usd: Optional[float] = None

    criado_em: datetime = Field(default_factory=datetime.now)
