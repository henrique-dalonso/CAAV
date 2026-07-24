from sqlmodel import SQLModel, create_engine, Session

from app.core.paths import PROJECT_ROOT
from app.db import models  # garante que a tabela Job seja registrada antes do create_all


DB_PATH = PROJECT_ROOT / "historico" / "extratus.db"


def _criar_engine():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{DB_PATH}")

    SQLModel.metadata.create_all(engine)

    return engine


engine = _criar_engine()


def obter_sessao():
    return Session(engine)
