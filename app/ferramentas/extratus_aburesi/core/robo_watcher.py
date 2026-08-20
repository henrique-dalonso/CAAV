import asyncio
import traceback

from app.ferramentas.extratus_aburesi.core.app_logger import registrar_log
from app.ferramentas.extratus_aburesi.core.robo_lote import rodar_ciclo_robo


# 5 minutos: dá folga (lotes do Batch API raramente terminam em menos que
# isso) sem ficar pesado no servidor — fácil de ajustar depois se
# necessário, não é um valor crítico.
INTERVALO_SEGUNDOS = 300


async def loop_robo():
    """Roda pra sempre em segundo plano enquanto o servidor web estiver de
    pé (ver `app/plataforma/web/main.py`). A cada tick, chama
    `rodar_ciclo_robo()` numa thread separada (`asyncio.to_thread`) pra
    não travar o resto do site enquanto o ciclo faz chamadas de rede/disco.
    Um erro num ciclo nunca derruba o loop — só loga e tenta de novo no
    próximo tick."""
    while True:
        try:
            await asyncio.to_thread(rodar_ciclo_robo)
        except Exception as erro:
            registrar_log(f"Erro no ciclo do robô: {erro}\n{traceback.format_exc()}")

        await asyncio.sleep(INTERVALO_SEGUNDOS)
