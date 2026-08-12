import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.plataforma.db.models import Usuario
from app.plataforma.web.auth import exigir_login
from app.plataforma.web.eventos_sse import registrar_conexao, remover_conexao
from app.plataforma.web.notificacoes import notificacoes_do_usuario


router = APIRouter()


@router.get("/notificacoes")
def obter_notificacoes(usuario: Usuario = Depends(exigir_login)):
    """Endpoint enxuto pro sininho do cabeçalho (base.js) — chamado na
    carga inicial e sempre que /notificacoes/eventos avisar que algo
    mudou (também num poll de segurança bem espaçado, ver base.js)."""
    return {"itens": notificacoes_do_usuario(usuario)}


@router.get("/notificacoes/eventos")
async def eventos_notificacoes(usuario: Usuario = Depends(exigir_login)):
    """SSE (Server-Sent Events) — Henrique, 2026-08-08: "não da para
    deixar certas coisas instantâneas?" Uma conexão só, o navegador (via
    EventSource, base.js) fica escutando; toda vez que algo relevante
    muda de verdade em qualquer lugar do site (ver eventos_sse.py pra a
    lista de gatilhos), essa conexão recebe um "atualizar" e o cliente
    busca /notificacoes de novo na hora — sem esperar o próximo tick de
    um timer. Não manda dado nenhum aqui, só o sinal — quem decide o que
    cada usuário vê continua sendo só o /notificacoes de sempre."""
    fila = registrar_conexao()

    async def gerar_eventos():
        try:
            # Primeiro byte logo de cara — alguns navegadores/proxies só
            # consideram a conexão "aberta" depois do primeiro evento.
            yield "event: conectado\ndata: ok\n\n"

            while True:
                try:
                    await asyncio.wait_for(fila.get(), timeout=25)
                    yield "event: atualizar\ndata: ok\n\n"
                except TimeoutError:
                    # Keep-alive — evita que um proxy/load balancer no
                    # meio do caminho feche a conexão por "inatividade"
                    # antes de qualquer coisa acontecer de verdade.
                    yield ": keep-alive\n\n"
        finally:
            # Roda mesmo se o cliente cair a conexão (GeneratorExit) —
            # sem isso, _conexoes em eventos_sse.py cresceria pra sempre
            # com filas de conexões que já fecharam.
            remover_conexao(fila)

    return StreamingResponse(gerar_eventos(), media_type="text/event-stream")
