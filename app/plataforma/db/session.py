from sqlmodel import SQLModel, create_engine, Session

from app.plataforma.paths import PROJECT_ROOT

# Garante que TODAS as tabelas (de todas as ferramentas) sejam registradas
# antes do create_all — sempre que uma ferramenta nova ganhar tabelas
# próprias, o models dela precisa ser importado aqui também.
from app.plataforma.db import models as _modelos_plataforma  # noqa: F401
from app.ferramentas.extratus.db import models as _modelos_extratus  # noqa: F401
from app.ferramentas.extratus_aburesi.db import models as _modelos_extratus_aburesi  # noqa: F401


DB_PATH = PROJECT_ROOT / "banco" / "plataforma.db"


def _criar_engine():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{DB_PATH}")

    SQLModel.metadata.create_all(engine)

    return engine


engine = _criar_engine()


def obter_sessao():
    return Session(engine)
