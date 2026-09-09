import asyncio
import traceback

from app.ferramentas.nucleo_relatorios.core.app_logger import registrar_log
from app.ferramentas.nucleo_relatorios.core.robo_lote import rodar_ciclo_robo
from app.ferramentas.nucleo_relatorios.tipos import REGISTRO_TIPOS


# 5 minutos: dá folga (lotes do Batch API raramente terminam em menos que
# isso) sem ficar pesado no servidor — fácil de ajustar depois se
# necessário, não é um valor crítico.
INTERVALO_SEGUNDOS = 300

# Extratus-Relatórios, tipo "bancario" — única ferramenta/tipo que usa o
# motor compartilhado (nucleo_relatorios) hoje, ver
# nucleo_relatorios/tipos.py.
FERRAMENTA_SLUG = "extratus-relatorios"
TIPO_RELATORIO = REGISTRO_TIPOS["bancario"]


async def loop_robo():
    """Roda pra sempre em segundo plano enquanto o servidor web estiver de
    pé (ver `app/plataforma/web/main.py`). A cada tick, chama
    `rodar_ciclo_robo()` numa thread separada (`asyncio.to_thread`) pra
    não travar o resto do site enquanto o ciclo faz chamadas de rede/disco.
    Um erro num ciclo nunca derruba o loop — só loga e tenta de novo no
    próximo tick."""
    while True:
        try:
            await asyncio.to_thread(rodar_ciclo_robo, TIPO_RELATORIO, FERRAMENTA_SLUG)
        except Exception as erro:
            registrar_log(f"Erro no ciclo do robô: {erro}\n{traceback.format_exc()}")

        await asyncio.sleep(INTERVALO_SEGUNDOS)
