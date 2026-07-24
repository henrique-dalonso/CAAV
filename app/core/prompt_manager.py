from app.core.paths import PROJECT_ROOT


PROMPT_PATH = PROJECT_ROOT / "config" / "instrucoes_relatorio.txt"


def carregar_instrucoes_relatorio():
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {PROMPT_PATH}"
        )

    with open(
        PROMPT_PATH,
        "r",
        encoding="utf-8"
    ) as arquivo:
        return arquivo.read()