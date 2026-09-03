import re

from sqlalchemy import event
from sqlmodel import SQLModel, create_engine, Session

from app.plataforma.logger import registrar_log
from app.plataforma.paths import PROJECT_ROOT

# Garante que TODAS as tabelas (de todas as ferramentas) sejam registradas
# antes do create_all — sempre que uma ferramenta nova ganhar tabelas
# próprias, o models dela precisa ser importado aqui também.
from app.plataforma.db import models as _modelos_plataforma  # noqa: F401
from app.ferramentas.extratus.db import models as _modelos_extratus  # noqa: F401
from app.ferramentas.extratus_aburesi.db import models as _modelos_extratus_aburesi  # noqa: F401
from app.ferramentas.crivus.db import models as _modelos_crivus  # noqa: F401


DB_PATH = PROJECT_ROOT / "banco" / "plataforma.db"

# create_all() só CRIA tabela que ainda não existe — nunca adiciona
# coluna numa tabela já existente, e esse projeto não usa uma
# ferramenta de migração (Alembic ou parecido). Esse dicionário é o
# registro manual de "colunas que um model ganhou depois da tabela já
# existir de verdade": {tabela: {coluna: tipo_sql}}. _garantir_colunas
# roda toda vez que o servidor sobe e só faz algo (ALTER TABLE) se a
# coluna realmente ainda não existir — sem isso, todo campo novo em
# qualquer model precisaria de um ALTER TABLE manual, uma vez, lembrado
# por alguém (foi assim, sem registro nenhum, até esse ponto).
COLUNAS_PENDENTES = {
    "usuario": {
        "tentativas_login_falhas": "INTEGER DEFAULT 0",
        "bloqueado": "BOOLEAN DEFAULT 0",
        "bloqueado_em": "TIMESTAMP",
        # As 2 abaixo foram adicionadas ao modelo antes desse mecanismo de
        # migração existir (02-03/08) e nunca tinham sido registradas aqui —
        # sem efeito na base atual (já existem), mas restaurar um backup
        # anterior a essa data, ou subir um ambiente novo a partir de uma
        # cópia velha, quebrava sem elas. Valores batem com
        # TEMA_ESCURO/COR_PERFIL_PADRAO em db/models.py (Henrique,
        # 2026-09-02: era TEMA_SISTEMA, mudou o padrão pra escuro).
        "tema": "VARCHAR DEFAULT 'escuro'",
        "cor_perfil": "VARCHAR DEFAULT '#4f46e5'",
    },
    "ferramenta": {
        "cor_acento": "VARCHAR",
        "cor_acento_hover": "VARCHAR",
        "cor_acento_fraco": "VARCHAR",
        "cor_acento_escuro": "VARCHAR",
        "cor_acento_hover_escuro": "VARCHAR",
        "cor_acento_fraco_escuro": "VARCHAR",
        # Mesma retroatividade do usuario.tema/cor_perfil acima.
        "suporta_fila_robo": "BOOLEAN DEFAULT 0",
    },
    "job": {
        "notificacao_resolvida": "BOOLEAN DEFAULT 0",
        # Henrique, diretoria, 2026-08-27 — quem PEDIU esse processo, ver
        # docstring de Job.solicitante_id em db/models.py.
        "solicitante_id": "INTEGER",
    },
    "job_aburesi": {
        "notificacao_resolvida": "BOOLEAN DEFAULT 0",
        "solicitante_id": "INTEGER",
    },
    "triagemmanual": {
        "origem_duplicado": "VARCHAR",
    },
    "triagemmanual_aburesi": {
        "origem_duplicado": "VARCHAR",
    },
    "usuarioferramenta": {
        # Mesma retroatividade do usuario.tema/cor_perfil acima.
        "fila_robo": "BOOLEAN DEFAULT 0",
        # Henrique, diretoria, 2026-08-19: controla o fluxo Manual/URGENTE
        # (fila_robo acima não é mais lido — Robô virou padrão, ver
        # docstring de UsuarioFerramenta em db/models.py).
        "acesso_manual": "BOOLEAN DEFAULT 0",
    },
    "itemloterobo": {
        # Henrique, diretoria, 2026-08-26 — custo do resgate de páginas
        # problemáticas por transcrição, ver docstring de ItemLoteRobo em
        # db/models.py.
        "custo_transcricao_usd": "REAL DEFAULT 0",
        # Henrique, diretoria, 2026-08-27 — quem pediu esse processo pro
        # Robô, ver docstring de Job.solicitante_id em db/models.py.
        "solicitante_id": "INTEGER",
    },
    "itemloterobo_aburesi": {
        "custo_transcricao_usd": "REAL DEFAULT 0",
        "solicitante_id": "INTEGER",
    },
    "checagemfila": {
        "solicitante_id": "INTEGER",
    },
    "checagemfila_aburesi": {
        "solicitante_id": "INTEGER",
    },
}


# Colunas que existiram num model antigo e foram substituídas por outra
# (não só renomeadas via TABELAS_RENOMEADAS acima, que é pra tabela
# inteira) — continuam fisicamente no banco em qualquer instalação que
# rodou pelo menos uma vez ANTES da troca, e como não estão mais em
# nenhum model, create_all()/_garantir_colunas() não sabem que elas
# existem. Se a coluna antiga for NOT NULL sem valor padrão no schema
# (comum, já que o default do SQLModel é só do lado do Python/ORM, não
# vira DEFAULT de verdade na tabela), qualquer INSERT feito pelo model
# novo — que nunca preenche essa coluna — quebra com "NOT NULL
# constraint failed". Encontrado na prática (2026-08-20): banco criado
# na VM com o código antes do rename fila_motor -> fila_robo, atualizado
# pra depois do rename sem nunca ter rodado create_all numa tabela nova
# (usuarioferramenta já existia) — promover alguém a coordenador falhava
# com 500 ao inserir UsuarioFerramenta sem 'fila_motor'.
COLUNAS_OBSOLETAS = {
    # admin_ferramenta: Henrique, diretoria, 2026-08-24 — permissão
    # "admin só desta ferramenta" removida por completo, ver docstring de
    # UsuarioFerramenta em db/models.py.
    "usuarioferramenta": ["fila_motor", "admin_ferramenta"],
}


def _remover_colunas_obsoletas(engine):
    with engine.connect() as conexao:
        for tabela, colunas in COLUNAS_OBSOLETAS.items():
            existentes = {
                linha[1]
                for linha in conexao.exec_driver_sql(f"PRAGMA table_info({tabela})")
            }

            for nome in colunas:
                if nome in existentes:
                    conexao.exec_driver_sql(f"ALTER TABLE {tabela} DROP COLUMN {nome}")
                    registrar_log(
                        f"Migração: coluna obsoleta '{nome}' removida da tabela '{tabela}'."
                    )

        conexao.commit()


def _garantir_colunas(engine):
    with engine.connect() as conexao:
        for tabela, colunas in COLUNAS_PENDENTES.items():
            existentes = {
                linha[1]
                for linha in conexao.exec_driver_sql(f"PRAGMA table_info({tabela})")
            }

            for nome, tipo in colunas.items():
                if nome not in existentes:
                    conexao.exec_driver_sql(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")
                    registrar_log(f"Migração: coluna '{nome}' adicionada à tabela '{tabela}'.")

        conexao.commit()


# Índices únicos parciais — não têm "IF NOT EXISTS" natural via ALTER
# TABLE como COLUNAS_PENDENTES, mas CREATE INDEX já aceita IF NOT EXISTS
# nativamente, então não precisa do controle manual de PRAGMA table_info.
# Henrique, 2026-08-13: trava real de banco contra 2 arquivos do fluxo
# manual (Gerar Relatório URGENTE) virando "processando" (prestes a chamar a
# IA) pro MESMO número de processo ao mesmo tempo — duas pessoas (ou o
# mesmo PDF 2x) enviando quase junto. Índice PARCIAL (só olha linhas
# "processando") pra não impedir reenvio depois que a primeira já
# terminou. Quem grava por cima disso trata o erro de violação e vira
# "duplicado_em_andamento" (db/triagem_manual.py) em vez de quebrar.
INDICES_UNICOS_PARCIAIS = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_triagemmanual_processo_ativo "
    "ON triagemmanual (processo_detectado) "
    "WHERE processo_detectado IS NOT NULL AND status = 'processando'",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_triagemmanual_aburesi_processo_ativo "
    "ON triagemmanual_aburesi (processo_detectado) "
    "WHERE processo_detectado IS NOT NULL AND status = 'processando'",
]


_PADRAO_NOME_INDICE = re.compile(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (\w+)")


def _garantir_indices(engine):
    with engine.connect() as conexao:
        indices_existentes = {
            linha[0]
            for linha in conexao.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }

        for sql in INDICES_UNICOS_PARCIAIS:
            nome = _PADRAO_NOME_INDICE.match(sql).group(1)
            conexao.exec_driver_sql(sql)

            if nome not in indices_existentes:
                registrar_log(f"Migração: índice '{nome}' criado.")

        conexao.commit()


# Henrique, diretoria, 2026-08-19: "Motor" virou "Robô" em tudo,
# inclusive nomes de tabela — {nome_antigo: nome_novo}. Diferente de
# COLUNAS_PENDENTES (que só ADICIONA), aqui é RENAME de verdade (SQLite
# suporta nativamente, preserva os dados e os índices da tabela) — tem
# dado real de teste nessas 3 tabelas (lotes/itens do Robô, histórico de
# upload da Fila), então criar tabela nova vazia do lado ia deixar tudo
# isso órfão e invisível. Roda ANTES de create_all() de propósito: se a
# tabela antiga já foi renomeada, create_all() não recria nada; se ainda
# não, create_all() criaria a tabela nova vazia primeiro e o rename
# encontraria as duas com o mesmo schema — mais confuso sem necessidade.
TABELAS_RENOMEADAS = {
    "lotemotor": "loterobo",
    "itemlotemotor": "itemloterobo",
    "uploadfilamotor": "uploadfilarobo",
    "lotemotor_aburesi": "loterobo_aburesi",
    "itemlotemotor_aburesi": "itemloterobo_aburesi",
    "uploadfilamotor_aburesi": "uploadfilarobo_aburesi",
}


def _garantir_tabelas_renomeadas(engine):
    with engine.connect() as conexao:
        existentes = {
            linha[0]
            for linha in conexao.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        for nome_antigo, nome_novo in TABELAS_RENOMEADAS.items():
            if nome_antigo in existentes and nome_novo not in existentes:
                conexao.exec_driver_sql(f"ALTER TABLE {nome_antigo} RENAME TO {nome_novo}")
                registrar_log(f"Migração: tabela '{nome_antigo}' renomeada para '{nome_novo}'.")

        conexao.commit()


def _configurar_conexao_sqlite(conexao_dbapi, _):
    """Roda em toda conexão nova (SQLAlchemy usa um pool, várias conexões
    reais por trás do mesmo `engine`) — sem isso, escritas concorrentes de
    verdade (upload no site + Robô fechando lote ao mesmo tempo) podem
    esbarrar no travamento padrão do SQLite e devolver "database is
    locked" em vez de simplesmente esperar a vez. WAL deixa leitura e
    escrita acontecerem ao mesmo tempo (só escrita-com-escrita ainda
    espera); busy_timeout faz quem esbarrar num travamento esperar até 30s
    em vez de falhar na hora."""
    cursor = conexao_dbapi.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def _criar_engine():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{DB_PATH}")
    event.listen(engine, "connect", _configurar_conexao_sqlite)

    _garantir_tabelas_renomeadas(engine)
    _remover_colunas_obsoletas(engine)
    SQLModel.metadata.create_all(engine)
    _garantir_colunas(engine)
    _garantir_indices(engine)

    return engine


engine = _criar_engine()


def obter_sessao():
    return Session(engine)
