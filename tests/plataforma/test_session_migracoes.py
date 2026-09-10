"""Fecha um buraco real de cobertura: nenhuma das migrações de banco em
`session.py` (COLUNAS_PENDENTES, INDICES_UNICOS_PARCIAIS, tabelas
renomeadas) tinha teste algum antes disso. Foco aqui é só a migração
mais recente e mais delicada — remover o UNIQUE global de
`checagemfila.nome_arquivo` (achado real: colidiu 2x em produção quando
ferramentas diferentes recebiam um arquivo com o mesmo nome)."""

import sqlalchemy.exc
import pytest
from sqlalchemy import create_engine

from app.plataforma.db.session import _garantir_checagemfila_sem_unique_global


_SQL_INDICE_COMPOSTO = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_checagemfila_ferramenta_arquivo "
    "ON checagemfila (ferramenta_slug, nome_arquivo)"
)


def _criar_tabela_no_formato_antigo(engine):
    """Simula o schema real de produção ANTES da migração (2026-09-10):
    `checagemfila` com um índice nomeado ÚNICO cobrindo só
    `nome_arquivo` — o mesmo formato que `Field(unique=True, index=True)`
    do SQLModel gerava (confirmado testando localmente antes de escrever
    a migração real)."""
    with engine.connect() as conexao:
        conexao.exec_driver_sql("""
            CREATE TABLE checagemfila (
                id INTEGER PRIMARY KEY,
                ferramenta_slug VARCHAR NOT NULL,
                nome_arquivo VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                solicitante_id INTEGER,
                processo_detectado VARCHAR,
                confianca_nivel VARCHAR,
                confianca_motivo VARCHAR,
                criado_em DATETIME NOT NULL,
                atualizado_em DATETIME NOT NULL
            )
        """)
        conexao.exec_driver_sql(
            "CREATE UNIQUE INDEX ix_checagemfila_nome_arquivo ON checagemfila (nome_arquivo)"
        )
        conexao.exec_driver_sql(
            "CREATE INDEX ix_checagemfila_ferramenta_slug ON checagemfila (ferramenta_slug)"
        )
        conexao.commit()


def _inserir(engine, ferramenta_slug, nome_arquivo):
    with engine.connect() as conexao:
        conexao.exec_driver_sql(
            "INSERT INTO checagemfila (ferramenta_slug, nome_arquivo, status, criado_em, atualizado_em) "
            "VALUES (:ferramenta, :nome, 'pendente', datetime('now'), datetime('now'))",
            {"ferramenta": ferramenta_slug, "nome": nome_arquivo},
        )
        conexao.commit()


def test_migracao_remove_unique_global_preservando_dados(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'teste.db'}")
    _criar_tabela_no_formato_antigo(engine)
    _inserir(engine, "extratus-relatorios", "processo.pdf")

    _garantir_checagemfila_sem_unique_global(engine)

    with engine.connect() as conexao:
        indices = conexao.exec_driver_sql("PRAGMA index_list(checagemfila)").fetchall()
        indice_nome_arquivo = next(i for i in indices if i[1] == "ix_checagemfila_nome_arquivo")
        assert indice_nome_arquivo[2] == 0  # não é mais único

        linhas = conexao.exec_driver_sql(
            "SELECT ferramenta_slug, nome_arquivo FROM checagemfila"
        ).fetchall()
        assert linhas == [("extratus-relatorios", "processo.pdf")]


def test_migracao_e_idempotente(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'teste.db'}")
    _criar_tabela_no_formato_antigo(engine)

    _garantir_checagemfila_sem_unique_global(engine)
    _garantir_checagemfila_sem_unique_global(engine)  # não deve levantar exceção na 2ª vez

    with engine.connect() as conexao:
        indices = conexao.exec_driver_sql("PRAGMA index_list(checagemfila)").fetchall()
        nomes = [i[1] for i in indices if i[1] == "ix_checagemfila_nome_arquivo"]
        assert len(nomes) == 1  # não duplicou o índice rodando 2x


def test_migracao_sem_tabela_nao_faz_nada(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'teste_vazio.db'}")
    _garantir_checagemfila_sem_unique_global(engine)  # não deve levantar exceção


def test_mesmo_nome_em_ferramentas_diferentes_nao_colide_mas_na_mesma_continua_bloqueado(tmp_path):
    """Prova o comportamento real que motivou a migração inteira (achado
    em produção 2026-09-10, 2 colisões reais confirmadas antes disso)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'teste.db'}")
    _criar_tabela_no_formato_antigo(engine)
    _garantir_checagemfila_sem_unique_global(engine)

    with engine.connect() as conexao:
        conexao.exec_driver_sql(_SQL_INDICE_COMPOSTO)
        conexao.commit()

    _inserir(engine, "extratus-relatorios", "processo.pdf")
    _inserir(engine, "emenda", "processo.pdf")  # mesmo nome, ferramenta diferente — antes colidia

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        _inserir(engine, "extratus-relatorios", "processo.pdf")  # mesmo nome, MESMA ferramenta — continua bloqueado
