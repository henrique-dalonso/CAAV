import asyncio
import traceback

from app.ferramentas.condenacao.core.config_manager import carregar_config
from app.ferramentas.nucleo_relatorios.core.app_logger import registrar_log
from app.ferramentas.nucleo_relatorios.core.robo_lote import rodar_ciclo_robo
from app.ferramentas.nucleo_relatorios.tipos import REGISTRO_TIPOS


# 2 minutos — mesmo ajuste já aplicado em Extratus-Relatórios/Emenda (ver
# docstring de rodar_ciclo_robo em core/robo_lote.py pro porquê). Não é
# um valor crítico, fácil de ajustar de novo se precisar.
INTERVALO_SEGUNDOS = 120

# Condenação, tipo "condenacao" — mesmo motor compartilhado
# (nucleo_relatorios) que Extratus-Relatórios/Emenda usam, ver
# nucleo_relatorios/tipos.py.
FERRAMENTA_SLUG = "condenacao"
TIPO_RELATORIO = REGISTRO_TIPOS["condenacao"]


async def loop_robo():
    """Roda pra sempre em segundo plano enquanto o servidor web estiver de
    pé (ver `app/plataforma/web/main.py`). A cada tick, chama
    `rodar_ciclo_robo()` numa thread separada (`asyncio.to_thread`) pra
    não travar o resto do site enquanto o ciclo faz chamadas de rede/disco.
    Um erro num ciclo nunca derruba o loop — só loga e tenta de novo no
    próximo tick."""
    while True:
        try:
            config = carregar_config()
            await asyncio.to_thread(rodar_ciclo_robo, config, TIPO_RELATORIO, FERRAMENTA_SLUG)
        except Exception as erro:
            registrar_log(f"Erro no ciclo do robô: {erro}\n{traceback.format_exc()}")

        await asyncio.sleep(INTERVALO_SEGUNDOS)
