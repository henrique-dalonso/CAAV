import asyncio
import traceback

from app.ferramentas.extratus.core.config_manager import carregar_config
from app.ferramentas.nucleo_relatorios.core.app_logger import registrar_log
from app.ferramentas.nucleo_relatorios.core.robo_lote import rodar_ciclo_robo
from app.ferramentas.nucleo_relatorios.tipos import REGISTRO_TIPOS


# 2 minutos (era 5 até 2026-09-09) — Henrique: o intervalo maior somado à
# antiga trava de "um lote por vez" (removida em robo_lote.py) fazia
# dezenas de casos novos esperarem um lote pequeno terminar antes de
# subir. Múltiplos lotes em voo já é seguro (ver docstring de
# rodar_ciclo_robo), então o intervalo menor só reduz o tempo até notar
# trabalho novo — checar status de lote não custa token nem chega perto
# de limite de requisição da Anthropic (1000+/min mesmo no tier mais
# baixo). Não é um valor crítico, fácil de ajustar de novo se precisar.
INTERVALO_SEGUNDOS = 120

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
    próximo tick.

    Carrega `config` (config_manager DESTA tela, `extratus`) a cada tick
    e passa pra `rodar_ciclo_robo` — achado real, 2026-09-09: antes desta
    correção, `rodar_ciclo_robo` sempre carregava a config do
    Extratus-Relatórios por dentro, então funcionava aqui só por
    coincidência (é literalmente essa tela); Aburesi e Emenda, que usam
    o mesmo `rodar_ciclo_robo`, estavam lendo a config errada."""
    while True:
        try:
            config = carregar_config()
            await asyncio.to_thread(rodar_ciclo_robo, config, TIPO_RELATORIO, FERRAMENTA_SLUG)
        except Exception as erro:
            registrar_log(f"Erro no ciclo do robô: {erro}\n{traceback.format_exc()}")

        await asyncio.sleep(INTERVALO_SEGUNDOS)
