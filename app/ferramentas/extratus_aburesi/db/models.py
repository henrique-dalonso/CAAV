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

    # Uso de IA — vazio em Job com erro (nunca chegou a chamar a IA de
    # verdade), preenchido em todo Job de sucesso.
    modelo_ia: Optional[str] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None
    custo_estimado_usd: Optional[float] = None

    # Só é usado em Jobs de erro (status "erro") do Motor (usuario_id
    # None) — controla se esse erro ainda deve aparecer no sininho de
    # notificações. Marcado True na futura tela dedicada de Erros (ainda
    # não construída); até lá fica sempre False e o erro permanece
    # visível, de propósito — ver web/notificacoes.py.
    notificacao_resolvida: bool = Field(default=False)

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


class ChecagemFila(SQLModel, table=True):
    """Checagem de duplicidade (nome+processo) de cada PDF na Fila do
    Motor, ANTES dele virar elegível pro Motor reivindicar — é a
    "triagem" que Henrique pediu (2026-08-06). NÃO confundir com
    `ia_cliente.montar_diagnostico_com_triagem`, que é outra coisa (o
    filtro de anexo de listagem de terceiros), só compartilha o nome.

    Uma linha por nome_arquivo, criada assim que ele aparece em
    motor_pasta_entrada (seja por upload no site ou qualquer outro jeito
    de o arquivo cair ali) e apagada quando ele sai da pasta (removido
    manualmente, ou já reivindicado por um lote). status começa
    "pendente" e vira um dos outros valores depois da checagem rodar —
    ver STATUS_* em db/checagem_fila.py.

    IMPORTANTE: hoje, qualquer status diferente de "aprovado" trava o
    arquivo pra sempre (o Motor nunca reivindica) — inclusive
    "processo_nao_encontrado". O jeito de resolver isso (painel de
    Conferências, com "Prosseguir" ou "Descartar") é trabalho futuro,
    ainda não construído — combinado assim de propósito com Henrique.

    Tabela própria (sufixo `_aburesi`), isolada da checagem do Extratus
    - Relatórios.
    """

    __tablename__ = "checagemfila_aburesi"

    id: Optional[int] = Field(default=None, primary_key=True)

    nome_arquivo: str = Field(unique=True, index=True)
    status: str = Field(default="pendente")

    processo_detectado: Optional[str] = None
    confianca_nivel: Optional[str] = None
    confianca_motivo: Optional[str] = None

    criado_em: datetime = Field(default_factory=datetime.now)
    atualizado_em: datetime = Field(default_factory=datetime.now)


class RegistroConferencia(SQLModel, table=True):
    """Ver docstring equivalente em app/ferramentas/extratus/db/models.py
    (Extratus - Relatórios) — mesma lógica, tabela própria (`_aburesi`)."""

    __tablename__ = "registroconferencia_aburesi"

    id: Optional[int] = Field(default=None, primary_key=True)

    nome_arquivo: str
    tipo_inconsistencia: str
    decisao: str

    usuario_id: int = Field(foreign_key="usuario.id")

    processo_informado: Optional[str] = None

    decidido_em: datetime = Field(default_factory=datetime.now)


class UploadFilaMotor(SQLModel, table=True):
    """Ver docstring equivalente em app/ferramentas/extratus/db/models.py
    (Extratus - Relatórios) — mesma lógica, tabela própria (`_aburesi`)."""

    __tablename__ = "uploadfilamotor_aburesi"

    id: Optional[int] = Field(default=None, primary_key=True)

    nome_arquivo: str = Field(index=True)
    usuario_id: int = Field(foreign_key="usuario.id")

    enviado_em: datetime = Field(default_factory=datetime.now)


class TriagemManual(SQLModel, table=True):
    """Ver docstring equivalente em app/ferramentas/extratus/db/models.py
    (Extratus - Relatórios) — mesma lógica, tabela própria (`_aburesi`)."""

    __tablename__ = "triagemmanual_aburesi"

    id: Optional[int] = Field(default=None, primary_key=True)

    usuario_id: int = Field(foreign_key="usuario.id")
    nome_arquivo: str
    caminho_pdf: str

    status: str = Field(default="pendente")

    processo_detectado: Optional[str] = None
    confianca_nivel: Optional[str] = None
    confianca_motivo: Optional[str] = None

    origem_duplicado: Optional[str] = None

    job_id: Optional[int] = Field(default=None, foreign_key="job_aburesi.id")
    erro_mensagem: Optional[str] = None

    criado_em: datetime = Field(default_factory=datetime.now)
    atualizado_em: datetime = Field(default_factory=datetime.now)
