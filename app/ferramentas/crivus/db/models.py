from datetime import date, datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class LoteCrivus(SQLModel, table=True):
    """1 upload de planilha do NPJUR = 1 lote. Agrupa N AnalisePublicacao
    (uma por linha da planilha, origem="lote") — não existe model de
    "linha crua" separado: cada linha já nasce como uma AnalisePublicacao
    de verdade (status="processando") na hora do upload, e é preenchida
    depois pelo lote_batch.py, reaproveitando 100% da tela de revisão e
    da listagem de Produção que já existem pro modo individual.

    status: "processando" (pelo menos 1 linha ainda não terminou, seja
    pelo caminho síncrono/urgente ou pela API de Lote da Anthropic) ->
    "concluido" (todas as linhas saíram de "processando"; a planilha de
    saída já foi gerada). Henrique, 2026-09-14."""

    id: Optional[int] = Field(default=None, primary_key=True)

    criado_por: int = Field(foreign_key="usuario.id")
    nome_arquivo: str
    criado_em: datetime = Field(default_factory=datetime.now)
    finalizado_em: Optional[datetime] = None

    status: str = Field(default="processando")

    total_linhas: int = Field(default=0)
    linhas_sucesso: int = Field(default=0)
    linhas_erro: int = Field(default=0)

    caminho_planilha_saida: Optional[str] = None


class AnalisePublicacao(SQLModel, table=True):
    """Uma publicação analisada no Crivus (Leitor de Publicação) — 1
    registro por teor enviado à IA. `origem` distingue "individual" (colado
    à mão + anexos, aba Leitor de Publicação) de "lote" (planilha do
    NPJUR, sem anexos, aba Processamento em Lote); o mesmo model e o
    mesmo motor de análise servem os dois, só muda como o caso chega até
    aqui.

    `resumo_ia`/`nivel_confianca` são informativos (a "leitura" da seção 1
    do prompt mestre) — não são campos corrigíveis nem entram no double
    check, ao contrário dos itens de Acompanhamento/Agendamento (ver
    ItemAcompanhamento/ItemAgendamento abaixo). Henrique, 2026-09-03.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    usuario_id: int = Field(foreign_key="usuario.id")
    origem: str = Field(default="individual")  # "individual" ou "lote"

    # Preenchidos só pra origem="lote" (ver LoteCrivus abaixo) — Henrique,
    # 2026-09-14: alimentam o "harness" de roteamento por urgência
    # (lote_batch.py). `lote_id` liga a linha ao upload que a originou;
    # `batch_id` é o id físico do lote na Anthropic quando essa linha
    # específica foi pelo caminho barato/lento (fica None se foi
    # despachada na hora, pelo caminho urgente/síncrono).
    lote_id: Optional[int] = Field(default=None, foreign_key="lotecrivus.id")
    batch_id: Optional[str] = None
    data_publicacao_original: Optional[date] = None
    data_importacao_original: Optional[date] = None

    teor_publicacao: str

    # Henrique, 2026-09-04: informados pela pessoa no formulário (ela já
    # vê os dois na fila do NPJUR antes de copiar o teor) — mais
    # confiável que depender só da IA adivinhar o processo lendo o texto.
    npjur: Optional[str] = None
    processo: Optional[str] = None  # nº CNJ, informado pela pessoa

    carteira: Optional[str] = None  # ITAÚ / VOLKSWAGEN / OUTRA — identificado pela IA

    # Henrique, 2026-09-04: leitura (seção 1 do prompt mestre) em campos
    # separados em vez de um texto único — a tela monta cada linha
    # (RÓTULO: valor;) de forma sempre consistente, sem depender da IA
    # formatar direito toda vez. Nenhum é corrigível/auditado (só
    # informativo), ao contrário dos itens de Acompanhamento/Agendamento.
    orgao_julgador: Optional[str] = None
    carteira_detalhe: Optional[str] = None
    fase_processual: Optional[str] = None
    posicao_parte: Optional[str] = None
    natureza_ato: Optional[str] = None
    quem_foi_intimado: Optional[str] = None
    resumo_objetivo: Optional[str] = None
    comando_judicial: Optional[str] = None
    resultado_parte: Optional[str] = None

    # Nome do campo ficou de quando a leitura inteira era um texto único
    # (2026-09-03) — hoje guarda a CONCLUSÃO OPERACIONAL (seção 8 do
    # prompt mestre), não a leitura (que virou os campos acima). Manter o
    # nome da coluna evita uma migração de rename só por causa disso.
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

    # Henrique, 2026-09-04: botão "+" pra acrescentar agendamento que a
    # IA não sugeriu — nasce em branco (tipo NAO_IDENTIFICADO, datas de
    # hoje) e já abre em modo edição. Distingue de um item real da IA
    # pra tela não mostrar uma "sugestão original" que nunca existiu, e
    # pra auditoria futura (quantos agendamentos a IA deixou passar).
    criado_manualmente: bool = Field(default=False)

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
