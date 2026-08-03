from datetime import datetime

from app.plataforma.paths import PROJECT_ROOT


LOG_PATH = PROJECT_ROOT / "app" / "ferramentas" / "extratus_aburesi" / "logs" / "extratus.log"


def registrar_log(mensagem):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    linha = f"[{data_hora}] {mensagem}\n"

    with open(LOG_PATH, "a", encoding="utf-8") as arquivo:
        arquivo.write(linha)

    print(linha.strip())