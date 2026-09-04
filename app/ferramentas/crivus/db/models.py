from datetime import date, datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class AnalisePublicacao(SQLModel, table=True):
    """Uma publicação analisada no Crivus (Leitor de Publicação) — 1
    registro por teor enviado à IA. `origem` distingue "individual" (colado
    à mão + anexos, aba Leitor de Publicação) de "lote" (planilha do
    NPJUR, sem anexos, aba Processamento em Lote — ainda não construída);
    o mesmo model e o mesmo motor de análise servem os dois, só muda como
    o caso chega até aqui.

    `resumo_ia`/`nivel_confianca` são informativos (a "leitura" da seção 1
    do prompt mestre) — não são campos corrigíveis nem entram no double
    check, ao contrário dos itens de Acompanhamento/Agendamento (ver
    ItemAcompanhamento/ItemAgendamento abaixo). Henrique, 2026-09-03.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    usuario_id: int = Field(foreign_key="usuario.id")
    origem: str = Field(default="individual")  # "individual" ou "lote"

    teor_publicacao: str

    # Henrique, 2026-09-04: informados pela pessoa no formulário (ela já
    # vê os dois na fila do NPJUR antes de copiar o teor) — mais
    # confiável que depender só da IA adivinhar o processo lendo o texto.
    npjur: Optional[str] = None
    processo: Optional[str] = None  # nº CNJ, informado pela pessoa

    carteira: Optional[str] = None  # ITAÚ / VOLKSWAGEN / OUTRA — identificado pela IA

    resumo_ia: Optional[str] = None
    nivel_confianca: Optional[str] = None  # "ALTO" / "MÉDIO" / "BAIXO"

    # Alerta crítico (pagamento/art.523/impugnação) — trava obrigatória
    # antes de concluir o caso, ver ciente_alerta_critico. Henrique,
    # 2026-09-03: "ISSO É FUNDAMENTAL".
    tem_alerta_critico: bool = Field(default=False)
    texto_alerta_critico: Optional[str] = None
    ciente_alerta_critico: bool = Field(default=False)

    # "processando" -> "aguardando_revisao" -> "concluido" (ou "erro" se a
    # chamada à IA falhar antes de gerar qualquer item).
    status: str = Field(default="processando")
    erro_mensagem: Optional[str] = None

    # Uso de IA — mesmo padrão de Job (Extratus), ver db/models.py lá.
    modelo_ia: Optional[str] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None
    custo_estimado_usd: Optional[float] = None

    criado_em: datetime = Field(default_factory=datetime.now)
    concluido_em: Optional[datetime] = None


class ItemAcompanhamento(SQLModel, table=True):
    """Um ACOMPANHAMENTO sugerido pela IA dentro de uma AnalisePublicacao —
    o que aconteceu no processo. Uma análise pode gerar mais de um.

    `tipo_sugerido` NUNCA é sobrescrito — preserva a sugestão original da
    IA lado a lado com `tipo` (o valor atual, igual ao sugerido até
    alguém corrigir) pra alimentar o double-check (comparar depois com o
    que a pessoa realmente lançou no NPJUR). Mesma estrutura em
    ItemAgendamento abaixo.

    status: "sugerido" (estado inicial, ainda não revisado) ->
    "desnecessario" (marcado, reversível, aparece riscado em vermelho na
    tela) ou "pronto" (revisado e confirmado pela pessoa). O caso só pode
    ser concluído quando TODOS os itens (dos dois tipos) estiverem
    "pronto". Henrique, 2026-09-03.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    analise_id: int = Field(foreign_key="analisepublicacao.id")

    tipo_sugerido: str
    tipo: str

    status: str = Field(default="sugerido")

    criado_em: datetime = Field(default_factory=datetime.now)


class ItemAgendamento(SQLModel, table=True):
    """Um AGENDAMENTO sugerido pela IA — o que o escritório deve fazer.
    Uma análise pode gerar vários (ex: combo recursal = 3+ itens
    simultâneos). Mesma mecânica de revisão de ItemAcompanhamento, com
    duas datas a mais (o NPJUR exige início/fim por agendamento — ver
    SLA_AGENDAMENTO em config/taxonomia.py)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    analise_id: int = Field(foreign_key="analisepublicacao.id")

    tipo_sugerido: str
    tipo: str

    data_inicio_sugerida: Optional[date] = None
    data_fim_sugerida: Optional[date] = None
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None

    status: str = Field(default="sugerido")

    criado_em: datetime = Field(default_factory=datetime.now)


class AnexoAnalise(SQLModel, table=True):
    """Um documento de apoio anexado pelo usuário numa AnalisePublicacao
    (sentença, petição etc.) — só existe no modo individual; casos de
    origem "lote" nunca têm anexo (Henrique, 2026-09-03: análise em massa
    é só o teor, sem documento de apoio)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    analise_id: int = Field(foreign_key="analisepublicacao.id")

    usuario_id: int = Field(foreign_key="usuario.id")
    nome_arquivo: str
    caminho: str
    tipo_mime: str
    tamanho_bytes: int

    criado_em: datetime = Field(default_factory=datetime.now)
