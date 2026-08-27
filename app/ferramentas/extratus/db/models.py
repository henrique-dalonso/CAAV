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

    # Uso de IA — vazio em Job com erro (nunca chegou a chamar a IA de
    # verdade), preenchido em todo Job de sucesso.
    modelo_ia: Optional[str] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None
    custo_estimado_usd: Optional[float] = None

    # Só é usado em Jobs de erro (status "erro") do Robô (usuario_id
    # None) — controla se esse erro ainda deve aparecer no sininho de
    # notificações. Marcado True na futura tela dedicada de Erros (ainda
    # não construída); até lá fica sempre False e o erro permanece
    # visível, de propósito — ver web/notificacoes.py.
    notificacao_resolvida: bool = Field(default=False)

    criado_em: datetime = Field(default_factory=datetime.now)


class LoteRobo(SQLModel, table=True):
    """Um lote enviado ao Batch API da Anthropic pelo Robô — cada lote
    pode conter vários PDFs (um item por PDF, ver `ItemLoteRobo`). Só o
    Robô usa Batch API; a fila manual continua em tempo real."""

    id: Optional[int] = Field(default=None, primary_key=True)

    batch_id: str  # id do lote devolvido pela Anthropic (ex: "msgbatch_...")
    status: str  # "enviado" ou "concluido"

    criado_em: datetime = Field(default_factory=datetime.now)
    finalizado_em: Optional[datetime] = None


class ItemLoteRobo(SQLModel, table=True):
    """Um PDF dentro de um lote do Robô — liga o `custom_id` usado na
    chamada ao Batch API de volta ao arquivo/detecção original, pra quando
    o resultado do lote chegar (segundos, minutos ou até 24h depois) dar
    pra terminar o processamento (gerar .docx, mover PDF, registrar Job)."""

    id: Optional[int] = Field(default=None, primary_key=True)

    lote_id: int = Field(foreign_key="loterobo.id")
    custom_id: str

    arquivo_pdf: str  # nome do arquivo em robo_pasta_entrada
    processo_detectado: Optional[str] = None
    confianca_nivel: Optional[str] = None
    confianca_motivo: Optional[str] = None

    status: str = "pendente"  # "pendente", "sucesso" ou "erro"

    # Custo (USD) do resgate de páginas problemáticas por transcrição (ver
    # ia_cliente.montar_diagnostico_com_triagem / transcricao_paginas.py),
    # já pago ANTES do lote ser submetido ao Batch API — precisa ficar
    # guardado aqui pra não se perder até o resultado do lote voltar
    # (minutos ou até 24h depois), quando o custo final é somado ao da
    # chamada principal (ver robo_lote._coletar_lotes_pendentes). Henrique,
    # diretoria, 2026-08-26.
    custo_transcricao_usd: float = 0.0

    criado_em: datetime = Field(default_factory=datetime.now)


class ChecagemFila(SQLModel, table=True):
    """Checagem de duplicidade (nome+processo) de cada PDF na Fila do
    Robô, ANTES dele virar elegível pro Robô reivindicar — é a
    "triagem" que Henrique pediu (2026-08-06). NÃO confundir com
    `ia_cliente.montar_diagnostico_com_triagem`, que é outra coisa (o
    filtro de anexo de listagem de terceiros), só compartilha o nome.

    Uma linha por nome_arquivo, criada assim que ele aparece em
    robo_pasta_entrada (seja por upload no site ou qualquer outro jeito
    de o arquivo cair ali) e apagada quando ele sai da pasta (removido
    manualmente, ou já reivindicado por um lote). status começa
    "pendente" e vira um dos outros valores depois da checagem rodar —
    ver STATUS_* em db/checagem_fila.py.

    IMPORTANTE: hoje, qualquer status diferente de "aprovado" trava o
    arquivo pra sempre (o Robô nunca reivindica) — inclusive
    "processo_nao_encontrado". O jeito de resolver isso (painel de
    Conferências, com "Prosseguir" ou "Descartar") é trabalho futuro,
    ainda não construído — combinado assim de propósito com Henrique.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    nome_arquivo: str = Field(unique=True, index=True)
    status: str = Field(default="pendente")

    processo_detectado: Optional[str] = None
    confianca_nivel: Optional[str] = None
    confianca_motivo: Optional[str] = None

    criado_em: datetime = Field(default_factory=datetime.now)
    atualizado_em: datetime = Field(default_factory=datetime.now)


class RegistroConferencia(SQLModel, table=True):
    """Registro PERMANENTE de cada decisão tomada no painel de
    Conferências (2026-08-07) — quem decidiu, o quê, e quando. Existe
    como tabela própria (não um campo a mais em `ChecagemFila` ou em
    `Job`) de propósito: a linha de `ChecagemFila` de um arquivo some
    assim que ele sai de `robo_pasta_entrada` (aprovado e reivindicado,
    ou descartado) — guardar a decisão só ali significaria perdê-la
    exatamente quando mais importaria (auditoria). E `Job.usuario_id` já
    tem um significado diferente que o sininho de notificações depende
    (usuario_id None = erro do Robô automático, ver
    web/notificacoes.py) — reaproveitar esse campo pra "quem aprovou"
    quebraria esse filtro silenciosamente. Ver [[feedback-verificar-base-antes-de-construir]].

    Nunca é apagado nem editado depois de criado — puro histórico.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    nome_arquivo: str
    tipo_inconsistencia: str  # o status que o ChecagemFila tinha (DUPLICADO_RELATORIO etc)
    decisao: str  # "aprovado" ou "descartado"

    usuario_id: int = Field(foreign_key="usuario.id")

    # Só preenchido quando a inconsistência era "processo não encontrado"
    # e a pessoa digitou o número na hora de aprovar.
    processo_informado: Optional[str] = None

    decidido_em: datetime = Field(default_factory=datetime.now)


class UploadFilaRobo(SQLModel, table=True):
    """Registro PERMANENTE de quem enviou cada arquivo pela tela da Fila
    do Robô (POST /fila/upload) — só isso, não decide nada e não é lido
    por nenhum watcher. Existe porque, diferente de Aprovar/Descartar em
    Conferências (RegistroConferencia acima), o upload em si nunca
    guardava quem mandou o arquivo (achado de auditoria, Rodada 12,
    2026-08-13). ChecagemFila é criada depois, por um scan de disco
    (checagem_fila.sincronizar_registros) que não sabe de onde o arquivo
    veio — por isso esse é um registro à parte, não um campo a mais lá."""

    id: Optional[int] = Field(default=None, primary_key=True)

    nome_arquivo: str = Field(index=True)
    usuario_id: int = Field(foreign_key="usuario.id")

    enviado_em: datetime = Field(default_factory=datetime.now)


class TriagemManual(SQLModel, table=True):
    """Checagem de duplicidade + acompanhamento de geração de cada PDF
    enviado pelo fluxo manual ("Gerar seu Relatório", 2026-08-11) — o
    equivalente pessoal/por-usuário de `ChecagemFila`, com um passo a
    mais: aqui não existe Robô/Batch API pegando os aprovados depois,
    então esta mesma linha também acompanha a geração do relatório em si
    (`job_id`/`erro_mensagem`), coisa que `ChecagemFila` nunca precisou
    guardar (isso vivia em `LoteRobo`/`ItemLoteRobo`, que não existem
    aqui).

    Uma linha por upload. `usuario_id` é sempre preenchido (diferente de
    `Job.usuario_id`, que usa None pra distinguir origem Robô — aqui só
    existe origem manual, não há ambiguidade pra resolver). Conferências
    manuais são pessoais: sempre filtradas por `usuario_id` nas consultas
    (web/routes/gerar_relatorio.py), nunca compartilhadas entre usuários como a
    Fila do Robô é.

    status: "pendente" (triagem rodando) -> "processando" (IA rodando,
    só depois da triagem aprovar) -> "concluido"/"erro"; ou, se a triagem
    travar, um dos mesmos 3 tipos de inconsistência de `ChecagemFila`
    (DUPLICADO_RELATORIO/DUPLICADO_EM_ANDAMENTO/NAO_ENCONTRADO — ver
    STATUS_* em db/triagem_manual.py), esperando decisão em Conferências.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    usuario_id: int = Field(foreign_key="usuario.id")
    nome_arquivo: str
    caminho_pdf: str

    status: str = Field(default="pendente")

    processo_detectado: Optional[str] = None
    confianca_nivel: Optional[str] = None
    confianca_motivo: Optional[str] = None

    # Só preenchido quando status é DUPLICADO_RELATORIO — "robô" ou
    # "manual", pra saber pra ONDE mandar o botão "Ir ao relatório"
    # (Henrique, 2026-08-12: ele sempre mandava pra "Seus Relatórios",
    # mesmo quando o duplicado era do Robô — lá ele nunca existe. Ver
    # db/jobs.py::obter_relatorio_existente_para_processo).
    origem_duplicado: Optional[str] = None

    job_id: Optional[int] = Field(default=None, foreign_key="job.id")
    erro_mensagem: Optional[str] = None

    criado_em: datetime = Field(default_factory=datetime.now)
    atualizado_em: datetime = Field(default_factory=datetime.now)
