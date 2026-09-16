import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import dispensar_notificacao, usuario_tem_acesso
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


@router.post("/notificacoes/ferramentas/dispensar")
def dispensar_notificacao_ferramenta(ferramenta_slug: str, chave: str, usuario: Usuario = Depends(exigir_login)):
    """Dispensa LÓGICA de um item da aba "Ferramentas" do sino — Henrique,
    diretoria, 2026-09-16: "um apagar lógico, não físico, removendo
    somente pro usuário que apagou, continua existindo a notificação de
    fato". Não toca na notificação de origem (Job/ChecagemFila) em
    nenhum momento, só registra que ESSE usuário não quer mais ver essa
    `chave` (ver NotificacaoDispensada, app/plataforma/db/models.py, e
    a montagem de "resolver" em app/plataforma/web/notificacoes.py).
    Genérico pra qualquer ferramenta/tipo de notificação, um único
    endpoint pros 4 módulos (extratus, extratus-aburesi, emenda,
    condenacao) em vez de repetir por módulo como o X de "Minhas" faz."""
    if not usuario_tem_acesso(usuario, ferramenta_slug):
        raise HTTPException(status_code=404)

    dispensar_notificacao(usuario.id, ferramenta_slug, chave)
    return {"ok": True}


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
