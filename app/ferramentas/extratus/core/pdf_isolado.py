from concurrent.futures import ProcessPoolExecutor


_executor = None


def _obter_executor():
    """Cria o pool de processos na primeira vez que alguém precisa dele e
    reaproveita depois — nunca na importação do módulo (evita subir
    processos ociosos toda vez que os testes importam isso). 2 workers:
    o suficiente pra tirar leitura de PDF do processo principal sem manter
    processos parados a maior parte do tempo. Compartilhado entre
    checagem_lote.py e motor_lote.py — mesma causa raiz, mesma correção."""
    global _executor

    if _executor is None:
        _executor = ProcessPoolExecutor(max_workers=2)

    return _executor


def executar_isolado(funcao, *args):
    """Roda `funcao(*args)` num PROCESSO separado, não só numa thread.

    Bug real reportado por Henrique (2026-08-06/07, achado originalmente
    na checagem da fila — ver histórico em checagem_lote.py): o site
    inteiro ficava lento/travado enquanto um PDF era lido, principalmente
    com arquivos grandes (documentos reais de até 979 páginas neste
    projeto). Causa raiz: `pypdf` (leitura de PDF) é Python puro — nunca
    libera o GIL. Rodar isso numa thread (`asyncio.to_thread`) não
    resolve: o GIL é um só por processo, então a thread ainda briga pelo
    mesmo turno de execução que atende toda requisição HTTP do site
    (navegação, upload, polling) — o processo inteiro fica efetivamente
    monopolizado enquanto páginas de PDF são lidas.

    Um processo separado tem seu próprio interpretador/GIL — roda de
    verdade em paralelo com o resto do servidor, sem competir por turno
    nenhum. Reaparecida em 2026-08-11 num SEGUNDO lugar (o ciclo do
    Motor, `motor_lote.py`, que lê PDF pra montar a triagem de anexos de
    terceiros) que tinha sido implementado depois da correção original e
    não tinha herdado o isolamento — mesmo sintoma, lugar novo."""
    return _obter_executor().submit(funcao, *args).result()
