from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class Job(SQLModel, table=True):
    """Um registro de processamento de PDF — sucesso ou erro.

    Substitui os antigos historico_producao.json e relatorio_erros.json:
    um único lugar guardando o que aconteceu com cada PDF processado.

    Tabela própria (sufixo `_aburesi`) — mesmo banco compartilhado
    (`banco/plataforma.db`) que o resto da plataforma, mas isolada do
    `Job` do Extratus - Relatórios, que tem seu próprio módulo/pasta
    completamente separado.
    """

    __tablename__ = "job_aburesi"

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


class LoteMotor(SQLModel, table=True):
    """Um lote enviado ao Batch API da Anthropic pelo Motor — cada lote
    pode conter vários PDFs (um item por PDF, ver `ItemLoteMotor`). Só o
    Motor usa Batch API; a fila manual continua em tempo real.

    Tabela própria (sufixo `_aburesi`), isolada do Motor do Extratus -
    Relatórios — cada módulo tem seu próprio Motor, rodando em paralelo.
    """

    __tablename__ = "lotemotor_aburesi"

    id: Optional[int] = Field(default=None, primary_key=True)

    batch_id: str  # id do lote devolvido pela Anthropic (ex: "msgbatch_...")
    status: str  # "enviado" ou "concluido"

    criado_em: datetime = Field(default_factory=datetime.now)
    finalizado_em: Optional[datetime] = None


class ItemLoteMotor(SQLModel, table=True):
    """Um PDF dentro de um lote do Motor — liga o `custom_id` usado na
    chamada ao Batch API de volta ao arquivo/detecção original, pra quando
    o resultado do lote chegar (segundos, minutos ou até 24h depois) dar
    pra terminar o processamento (gerar .docx, mover PDF, registrar Job)."""

    __tablename__ = "itemlotemotor_aburesi"

    id: Optional[int] = Field(default=None, primary_key=True)

    lote_id: int = Field(foreign_key="lotemotor_aburesi.id")
    custom_id: str

    arquivo_pdf: str  # nome do arquivo em motor_pasta_entrada
    processo_detectado: Optional[str] = None
    confianca_nivel: Optional[str] = None
    confianca_motivo: Optional[str] = None

    status: str = "pendente"  # "pendente", "sucesso" ou "erro"

    criado_em: datetime = Field(default_factory=datetime.now)


class ArquivoPendente(SQLModel, table=True):
    """Rastreia quem enviou cada PDF que está esperando na fila manual
    (pasta_entrada) — a pasta em si é uma única compartilhada no disco,
    mas cada usuário só deve ver/processar os PDFs que ele mesmo enviou
    ali (fila "individual"). Não tem relação com a fila do motor
    (motor_pasta_entrada), que é universal e não é filtrada por dono.
    """

    __tablename__ = "arquivopendente_aburesi"

    id: Optional[int] = Field(default=None, primary_key=True)

    nome_arquivo: str
    usuario_id: int = Field(foreign_key="usuario.id")

    enviado_em: datetime = Field(default_factory=datetime.now)
