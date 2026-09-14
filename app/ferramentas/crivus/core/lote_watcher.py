import asyncio
import traceback

from app.ferramentas.crivus.core.config_manager import carregar_config
from app.ferramentas.crivus.core.lote_batch import rodar_ciclo_lote


# 60s — mesmo raciocínio do robô do Extratus (checar status de batch não
# custa token nem chega perto de limite de taxa da API): quanto menor o
# intervalo, mais cedo uma linha que "envelheceu" e ficou atrasada é
# retirada da fila de despacho (ver lote_batch.py).
INTERVALO_SEGUNDOS = 60


async def loop_lote():
    """Roda pra sempre em segundo plano enquanto o servidor web estiver de
    pé (ver `app/plataforma/web/main.py`). A cada tick, chama
    `rodar_ciclo_lote()` numa thread separada (`asyncio.to_thread`) pra
    não travar o resto do site enquanto o ciclo faz chamadas de rede/disco.
    Um erro num ciclo nunca derruba o loop — só loga e tenta de novo no
    próximo tick."""
    while True:
        try:
            config = carregar_config()
            await asyncio.to_thread(rodar_ciclo_lote, config)
        except Exception as erro:
            print(f"Erro no ciclo do Processamento em Lote (Crivus): {erro}\n{traceback.format_exc()}")

        await asyncio.sleep(INTERVALO_SEGUNDOS)
