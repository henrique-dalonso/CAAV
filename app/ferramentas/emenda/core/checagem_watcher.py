import asyncio
import traceback

from app.ferramentas.nucleo_relatorios.core.app_logger import registrar_log
from app.ferramentas.nucleo_relatorios.core.checagem_lote import rodar_ciclo_checagem


# Bem mais rápido que o Robô (300s) de propósito — a checagem é só
# leitura local (PDF + banco), sem custo de API nenhum, então não tem
# motivo pra fazer alguém esperar minutos pra saber se o arquivo tem
# algum problema. Henrique foi firme sobre isso precisar "parecer
# responsivo".
INTERVALO_SEGUNDOS = 5

# Emenda, tipo "emenda" — mesmo motor compartilhado
# (nucleo_relatorios) que Extratus-Relatórios usa, ver
# nucleo_relatorios/tipos.py.
FERRAMENTA_SLUG = "emenda"


async def loop_checagem():
    """Mesmo padrão do loop_robo() (robo_watcher.py) — roda pra sempre
    em segundo plano, nunca derruba o servidor se um ciclo falhar, só
    loga e tenta de novo no próximo tick."""
    while True:
        try:
            await asyncio.to_thread(rodar_ciclo_checagem, FERRAMENTA_SLUG)
        except Exception as erro:
            registrar_log(f"Erro no ciclo de checagem da fila: {erro}\n{traceback.format_exc()}")

        await asyncio.sleep(INTERVALO_SEGUNDOS)
