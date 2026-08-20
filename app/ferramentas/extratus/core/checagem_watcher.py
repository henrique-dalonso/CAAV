import asyncio
import traceback

from app.ferramentas.extratus.core.app_logger import registrar_log
from app.ferramentas.extratus.core.checagem_lote import rodar_ciclo_checagem


# Bem mais rápido que o Robô (300s) de propósito — a checagem é só
# leitura local (PDF + banco), sem custo de API nenhum, então não tem
# motivo pra fazer alguém esperar minutos pra saber se o arquivo tem
# algum problema. Henrique foi firme sobre isso precisar "parecer
# responsivo".
INTERVALO_SEGUNDOS = 5


async def loop_checagem():
    """Mesmo padrão do loop_robo() (robo_watcher.py) — roda pra sempre
    em segundo plano, nunca derruba o servidor se um ciclo falhar, só
    loga e tenta de novo no próximo tick."""
    while True:
        try:
            await asyncio.to_thread(rodar_ciclo_checagem)
        except Exception as erro:
            registrar_log(f"Erro no ciclo de checagem da fila: {erro}\n{traceback.format_exc()}")

        await asyncio.sleep(INTERVALO_SEGUNDOS)
