from datetime import datetime

from app.plataforma.paths import PROJECT_ROOT


# Log da plataforma em si (login, migração de banco, etc.) — separado do
# log de cada ferramenta (app/ferramentas/*/core/app_logger.py), que é
# sobre o processamento de PDF/relatório de cada uma.
LOG_PATH = PROJECT_ROOT / "app" / "plataforma" / "logs" / "plataforma.log"


def registrar_log(mensagem):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    linha = f"[{data_hora}] {mensagem}\n"

    with open(LOG_PATH, "a", encoding="utf-8") as arquivo:
        arquivo.write(linha)

    print(linha.strip())
