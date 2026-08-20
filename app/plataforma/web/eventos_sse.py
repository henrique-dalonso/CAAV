import asyncio
import threading


# Hub de Server-Sent Events pro sininho — Henrique, 2026-08-08: "não da
# para deixar certas coisas instantaneas" (o polling de 5s do sininho).
# Broadcast puro, sem alvo por usuário de propósito: cada conexão SSE só
# recebe um "algo mudou, confira de novo" sem conteúdo nenhum — quem
# decide o que cada usuário pode ver continua sendo só o /notificacoes
# de sempre (notificacoes_do_usuario, já filtra por acesso à fila do
# robô por ferramenta). Fazer o hub saber "quem precisa ver o quê"
# duplicaria essa lógica de permissão num lugar novo, arriscando os dois
# lados divergirem com o tempo — mais simples e mais seguro deixar o hub
# saber só "aconteceu uma mudança relevante", ponto.
#
# Em memória, um processo só (sem Redis/fila externa) — proporcional ao
# tamanho real de time que usa isso; ver [[extratus-notificacoes]] pra
# raciocínio parecido sobre escala.
_conexoes: list[asyncio.Queue] = []

# threading.Lock (não asyncio.Lock) de propósito — essa lista é mexida
# tanto pelo event loop async das rotas SSE quanto pelos watchers do
# Robô/Checagem, que rodam em thread OS separada (asyncio.to_thread).
# Um lock de asyncio só protege contra outras coroutines do MESMO loop,
# não contra outra thread real — sem essa trava, um registrar/remover
# concorrente com um avisar_mudanca() rodando no watcher podia mudar o
# tamanho da lista no meio do "for fila in _conexoes" (Rodada 12, achado
# de qualidade de código).
_trava_conexoes = threading.Lock()


def registrar_conexao() -> asyncio.Queue:
    # maxsize pequeno de propósito: isso é só um sinal "confira de novo",
    # nunca precisa acumular mais que uns poucos avisos — se um cliente
    # ficar pra trás (aba dormindo, conexão lenta), o put_nowait em
    # avisar_mudanca() simplesmente descarta o excesso (ver QueueFull
    # abaixo) em vez de crescer sem limite.
    fila: asyncio.Queue = asyncio.Queue(maxsize=10)
    with _trava_conexoes:
        _conexoes.append(fila)
    return fila


def remover_conexao(fila: asyncio.Queue) -> None:
    with _trava_conexoes:
        if fila in _conexoes:
            _conexoes.remove(fila)


def avisar_mudanca() -> None:
    """Chamado sempre que algo que pode afetar o sininho muda de verdade
    — um Job novo (sucesso/revisão/erro, manual ou Robô), um ciclo de
    checagem que promoveu/resolveu uma inconsistência de triagem, ou uma
    decisão no painel de Conferências (aprovar/descartar/descartar
    todas/remover pendente). Acorda toda conexão SSE aberta pra buscar
    o estado real na hora, em vez de esperar o próximo poll."""
    with _trava_conexoes:
        filas = list(_conexoes)

    for fila in filas:
        try:
            fila.put_nowait(None)
        except asyncio.QueueFull:
            pass
