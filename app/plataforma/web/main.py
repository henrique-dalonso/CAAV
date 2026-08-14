import app.plataforma.env  # noqa: F401 — carrega o .env antes de qualquer coisa

import asyncio
import os
import secrets
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.plataforma.db.models import Ferramenta
from app.plataforma.db.seed import garantir_ferramentas_padrao
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import registrar_acesso_ferramenta
from app.plataforma.web.auth import NaoAutenticado
from app.plataforma.web.routes import admin, auth, home, notificacoes, perfil
from app.plataforma.web.templates_util import criar_templates
from app.ferramentas.extratus.core.checagem_watcher import loop_checagem
from app.ferramentas.extratus.core.motor_watcher import loop_motor
from app.ferramentas.extratus.web.routes import configuracoes_motor, custos, fila, gerar_relatorio, relatorios_manuais, relatorios_motor
from app.ferramentas.extratus_aburesi.core.checagem_watcher import loop_checagem as loop_checagem_aburesi
from app.ferramentas.extratus_aburesi.core.motor_watcher import loop_motor as loop_motor_aburesi
from app.ferramentas.extratus_aburesi.web.routes import (
    configuracoes_motor as configuracoes_motor_aburesi,
    custos as custos_aburesi,
    fila as fila_aburesi,
    gerar_relatorio as gerar_relatorio_aburesi,
    relatorios_manuais as relatorios_manuais_aburesi,
    relatorios_motor as relatorios_motor_aburesi,
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
app.include_router(gerar_relatorio.router, prefix="/extratus")
app.include_router(relatorios_manuais.router, prefix="/extratus")
app.include_router(custos.router, prefix="/extratus")
app.include_router(configuracoes_motor.router, prefix="/extratus")
app.include_router(fila.router, prefix="/extratus")
app.include_router(relatorios_motor.router, prefix="/extratus")
app.include_router(gerar_relatorio_aburesi.router, prefix="/extratus-aburesi")
app.include_router(relatorios_manuais_aburesi.router, prefix="/extratus-aburesi")
app.include_router(custos_aburesi.router, prefix="/extratus-aburesi")
app.include_router(configuracoes_motor_aburesi.router, prefix="/extratus-aburesi")
app.include_router(fila_aburesi.router, prefix="/extratus-aburesi")
app.include_router(relatorios_motor_aburesi.router, prefix="/extratus-aburesi")
app.include_router(leitor_publicacoes_home.router, prefix="/leitor-publicacoes")


@app.exception_handler(NaoAutenticado)
def handler_nao_autenticado(request: Request, exc: NaoAutenticado):
    return RedirectResponse(url="/login", status_code=303)


# Página de erro estilizada (403/404/500 e qualquer outro HTTPException)
# — antes disso, qualquer erro (sem permissão, página inexistente, bug
# real) caía no JSON cru padrão do FastAPI/Starlette. Standalone, igual
# login.html/login.css — NÃO estende base.html de propósito: base.html
# exige `usuario` preenchido (usuario.tema, usuario.nome...) sem checagem
# de nulo, e uma URL inválida pode nunca ter passado por login nenhum.
templates_erro = criar_templates(BASE_DIR / "templates")


# Detalhes que o próprio Starlette preenche sozinho quando NENHUMA rota
# bate com a URL (não veio de um `raise HTTPException(..., detail=...)`
# escrito por nós) — em inglês, genéricos demais pra mostrar direto.
# Achado testando ao vivo: sem esse filtro, uma URL inexistente mostrava
# "Not Found" cru na tela em vez da mensagem em português.
_DETALHES_PADRAO_DO_FRAMEWORK = {"Not Found", "Method Not Allowed", "Bad Request", "Forbidden", "Internal Server Error"}


def _detalhe_especifico(exc: HTTPException) -> str | None:
    detalhe = exc.detail
    if not detalhe or detalhe in _DETALHES_PADRAO_DO_FRAMEWORK:
        return None
    return detalhe


def _pagina_erro(request: Request, status_code: int, titulo: str, mensagem: str, orientacao: str | None = None):
    return templates_erro.TemplateResponse(
        request,
        "erro.html",
        {
            "codigo": status_code,
            "titulo": titulo,
            "mensagem": mensagem,
            "orientacao": orientacao,
            "botao_texto": "Voltar para a Home",
            "botao_link": "/",
        },
        status_code=status_code,
    )


@app.exception_handler(HTTPException)
def handler_http_exception(request: Request, exc: HTTPException):
    if exc.status_code == 403:
        return _pagina_erro(
            request, 403, "Sem permissão",
            _detalhe_especifico(exc) or "Você não tem permissão para acessar isso.",
            orientacao="Peça a um administrador para liberar seu acesso.",
        )

    if exc.status_code == 404:
        return _pagina_erro(
            request, 404, "Não encontramos isso",
            _detalhe_especifico(exc) or "A página ou o arquivo que você procura não existe, ou foi removido.",
        )

    return _pagina_erro(
        request, exc.status_code, "Algo não deu certo",
        _detalhe_especifico(exc) or "Não foi possível completar essa ação.",
    )


@app.exception_handler(Exception)
def handler_erro_interno(request: Request, exc: Exception):
    # Bug real/exceção não tratada — nunca deve travar silenciosamente:
    # imprime o traceback completo no log do servidor (mesmo padrão de
    # `print` já usado no resto do projeto, ver ia_cliente.py) antes de
    # mostrar a tela amigável pra quem está usando o site.
    traceback.print_exc()

    return _pagina_erro(
        request, 500, "Algo deu errado",
        "Nosso sistema encontrou um problema inesperado. Tente novamente "
        "daqui a pouco — se continuar acontecendo, avise o suporte.",
    )
