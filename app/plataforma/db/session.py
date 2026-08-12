from sqlmodel import SQLModel, create_engine, Session

from app.plataforma.paths import PROJECT_ROOT

# Garante que TODAS as tabelas (de todas as ferramentas) sejam registradas
# antes do create_all — sempre que uma ferramenta nova ganhar tabelas
# próprias, o models dela precisa ser importado aqui também.
from app.plataforma.db import models as _modelos_plataforma  # noqa: F401
from app.ferramentas.extratus.db import models as _modelos_extratus  # noqa: F401
from app.ferramentas.extratus_aburesi.db import models as _modelos_extratus_aburesi  # noqa: F401


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
    },
    "ferramenta": {
        "cor_acento": "VARCHAR",
        "cor_acento_hover": "VARCHAR",
        "cor_acento_fraco": "VARCHAR",
        "cor_acento_escuro": "VARCHAR",
        "cor_acento_hover_escuro": "VARCHAR",
        "cor_acento_fraco_escuro": "VARCHAR",
    },
    "job": {
        "notificacao_resolvida": "BOOLEAN DEFAULT 0",
    },
    "job_aburesi": {
        "notificacao_resolvida": "BOOLEAN DEFAULT 0",
    },
    "triagemmanual": {
        "origem_duplicado": "VARCHAR",
    },
    "triagemmanual_aburesi": {
        "origem_duplicado": "VARCHAR",
    },
}


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

        conexao.commit()


# Índices únicos parciais — não têm "IF NOT EXISTS" natural via ALTER
# TABLE como COLUNAS_PENDENTES, mas CREATE INDEX já aceita IF NOT EXISTS
# nativamente, então não precisa do controle manual de PRAGMA table_info.
# Henrique, 2026-08-13: trava real de banco contra 2 arquivos do fluxo
# manual (Gerar seu Relatório) virando "processando" (prestes a chamar a
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


def _garantir_indices(engine):
    with engine.connect() as conexao:
        for sql in INDICES_UNICOS_PARCIAIS:
            conexao.exec_driver_sql(sql)
        conexao.commit()


def _criar_engine():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{DB_PATH}")

    SQLModel.metadata.create_all(engine)
    _garantir_colunas(engine)
    _garantir_indices(engine)

    return engine


engine = _criar_engine()


def obter_sessao():
    return Session(engine)
