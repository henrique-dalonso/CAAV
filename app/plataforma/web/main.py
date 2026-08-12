import app.plataforma.env  # noqa: F401 — carrega o .env antes de qualquer coisa

import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select
from starlette.middleware.sessions import SessionMiddleware

from app.plataforma.db.models import Ferramenta
from app.plataforma.db.seed import garantir_ferramentas_padrao
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import registrar_acesso_ferramenta
from app.plataforma.web.auth import NaoAutenticado
from app.plataforma.web.routes import admin, auth, home, notificacoes, perfil
from app.ferramentas.extratus.core.checagem_watcher import loop_checagem
from app.ferramentas.extratus.core.motor_watcher import loop_motor
from app.ferramentas.extratus.web.routes import fila, historico, inbox, motor, relatorios_motor, relatorios_prontos
from app.ferramentas.extratus_aburesi.core.checagem_watcher import loop_checagem as loop_checagem_aburesi
from app.ferramentas.extratus_aburesi.core.motor_watcher import loop_motor as loop_motor_aburesi
from app.ferramentas.extratus_aburesi.web.routes import (
    fila as fila_aburesi,
    historico as historico_aburesi,
    inbox as inbox_aburesi,
    motor as motor_aburesi,
    relatorios_motor as relatorios_motor_aburesi,
    relatorios_prontos as relatorios_prontos_aburesi,
)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # O vigia do Motor só faz alguma coisa quando "motor_ativo" estiver
    # ligado (ver motor_lote.rodar_ciclo_motor) — aqui só garantimos que
    # ele existe rodando em segundo plano enquanto o servidor estiver de
    # pé, prontinho pra agir assim que alguém ligar o interruptor. Cada
    # módulo (Extratus - Relatórios, Extratus - Aburesi, e qualquer futuro)
    # roda seu próprio vigia, em paralelo, de verdade — só mais uma linha
    # aqui quando um módulo novo ganhar Motor.
    tarefa_motor = asyncio.create_task(loop_motor())
    tarefa_motor_aburesi = asyncio.create_task(loop_motor_aburesi())
    # Checagem da Fila (a "triagem" de duplicidade nome+processo) — loop
    # bem mais rápido que o do Motor, só leitura local, sem custo de API.
    tarefa_checagem = asyncio.create_task(loop_checagem())
    tarefa_checagem_aburesi = asyncio.create_task(loop_checagem_aburesi())

    yield

    tarefa_motor.cancel()
    tarefa_motor_aburesi.cancel()
    tarefa_checagem.cancel()
    tarefa_checagem_aburesi.cancel()


app = FastAPI(
    title="Centro de Experiência do Colaborador — Alonso & Verdiani",
    lifespan=lifespan,
    # Explorador de API automático do FastAPI é coisa de desenvolvimento —
    # não faz sentido expor /docs, /redoc, /openapi.json num site pronto
    # pro público.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


@app.middleware("http")
async def middleware_registrar_acesso_ferramenta(request: Request, call_next):
    """Toda vez que alguém logado acessa a página principal de uma
    ferramenta (a URL exata cadastrada em Ferramenta.url), soma 1 no
    contador de uso — alimenta o bloco "Mais utilizadas" da home. Não
    bloqueia nem altera a resposta, só observa.

    Roda pra TODA requisição (esse middleware envolve o app inteiro,
    inclusive os StaticFiles montados) — sem esse corte cedo, cada
    CSS/JS/ícone de cada página abria uma sessão de banco e rodava um
    SELECT à toa, já que nenhuma URL de estático nunca bate com
    `Ferramenta.url`. Isso é exatamente o tipo de coisa que passa
    despercebida em um teste isolado mas soma alguns ms por requisição,
    multiplicado por vários arquivos estáticos por página carregada."""
    if "/static/" in request.url.path:
        return await call_next(request)

    resposta = await call_next(request)

    usuario_id = request.session.get("usuario_id")

    if usuario_id:
        with obter_sessao() as sessao:
            ferramenta = sessao.exec(
                select(Ferramenta).where(Ferramenta.url == request.url.path)
            ).first()

        if ferramenta:
            registrar_acesso_ferramenta(usuario_id, ferramenta.id)

    return resposta

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Cada ferramenta pode ter seus próprios arquivos estáticos (CSS/JS),
# servidos sob /extratus/static/... — mantém a separação sistema x
# ferramenta também nos assets, não só no código Python.
EXTRATUS_STATIC_DIR = (
    BASE_DIR.parent.parent / "ferramentas" / "extratus" / "web" / "static"
)
app.mount(
    "/extratus/static",
    StaticFiles(directory=EXTRATUS_STATIC_DIR),
    name="extratus-static",
)

EXTRATUS_ABURESI_STATIC_DIR = (
    BASE_DIR.parent.parent / "ferramentas" / "extratus_aburesi" / "web" / "static"
)
app.mount(
    "/extratus-aburesi/static",
    StaticFiles(directory=EXTRATUS_ABURESI_STATIC_DIR),
    name="extratus-aburesi-static",
)

LEITOR_PUBLICACOES_STATIC_DIR = (
    BASE_DIR.parent.parent / "ferramentas" / "leitor_publicacoes" / "web" / "static"
)
app.mount(
    "/leitor-publicacoes/static",
    StaticFiles(directory=LEITOR_PUBLICACOES_STATIC_DIR),
    name="leitor-publicacoes-static",
)

app.include_router(auth.router)
app.include_router(home.router)
app.include_router(admin.router)
app.include_router(perfil.router)
app.include_router(notificacoes.router)
app.include_router(inbox.router, prefix="/extratus")
app.include_router(relatorios_prontos.router, prefix="/extratus")
app.include_router(historico.router, prefix="/extratus")
app.include_router(motor.router, prefix="/extratus")
app.include_router(fila.router, prefix="/extratus")
app.include_router(relatorios_motor.router, prefix="/extratus")
app.include_router(inbox_aburesi.router, prefix="/extratus-aburesi")
app.include_router(relatorios_prontos_aburesi.router, prefix="/extratus-aburesi")
app.include_router(historico_aburesi.router, prefix="/extratus-aburesi")
app.include_router(motor_aburesi.router, prefix="/extratus-aburesi")
app.include_router(fila_aburesi.router, prefix="/extratus-aburesi")
app.include_router(relatorios_motor_aburesi.router, prefix="/extratus-aburesi")
app.include_router(leitor_publicacoes_home.router, prefix="/leitor-publicacoes")


@app.exception_handler(NaoAutenticado)
def handler_nao_autenticado(request: Request, exc: NaoAutenticado):
    return RedirectResponse(url="/login", status_code=303)
