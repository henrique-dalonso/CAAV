import app.plataforma.env  # noqa: F401 — carrega o .env antes de qualquer coisa

import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.plataforma.db.seed import garantir_ferramentas_padrao
from app.plataforma.web.auth import NaoAutenticado
from app.plataforma.web.routes import admin, auth, home
from app.ferramentas.extratus.web.routes import historico, inbox
from app.ferramentas.leitor_publicacoes.web.routes import home as leitor_publicacoes_home


BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = os.environ.get("EXTRATUS_SECRET_KEY")

if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print(
        "AVISO: EXTRATUS_SECRET_KEY não definida (.env). Gerando uma chave "
        "temporária — todo mundo será deslogado a cada reinício do servidor. "
        "Defina EXTRATUS_SECRET_KEY no .env antes de usar isso a sério."
    )

garantir_ferramentas_padrao()

app = FastAPI(title="Centro de Experiência do Colaborador — Alonso & Verdiani")

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(auth.router)
app.include_router(home.router)
app.include_router(admin.router)
app.include_router(inbox.router, prefix="/extratus")
app.include_router(historico.router, prefix="/extratus")
app.include_router(leitor_publicacoes_home.router, prefix="/leitor-publicacoes")


@app.exception_handler(NaoAutenticado)
def handler_nao_autenticado(request: Request, exc: NaoAutenticado):
    return RedirectResponse(url="/login", status_code=303)
