import json
from pathlib import Path

from app.plataforma.paths import PROJECT_ROOT


EXTRATUS_ROOT = PROJECT_ROOT / "app" / "ferramentas" / "extratus"

CONFIG_PATH = EXTRATUS_ROOT / "config" / "config.json"


CONFIG_PADRAO = {
    "pasta_entrada": "app/ferramentas/extratus/dados/entrada_pdfs",
    "pasta_saida": "app/ferramentas/extratus/dados/relatorios_prontos",
    "pasta_processados": "app/ferramentas/extratus/dados/processados",
    "pasta_revisao": "app/ferramentas/extratus/dados/revisao",
    "pasta_erros": "app/ferramentas/extratus/dados/erros",

    "limite_padrao": 0,

    "ia_provider": "simulado",
    "modelo_ia": "claude-sonnet-4"
}

PASTAS_CONFIGURAVEIS = [
    "pasta_entrada",
    "pasta_saida",
    "pasta_processados",
    "pasta_revisao",
    "pasta_erros",
]


def salvar_config(config):
    CONFIG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        CONFIG_PATH,
        "w",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            config,
            arquivo,
            ensure_ascii=False,
            indent=4
        )


def resolver_pastas(config):
    """Devolve uma cópia do config com as pastas como caminho absoluto,
    baseado na raiz do projeto — não em qual pasta o programa foi chamado.

    O arquivo config.json em si continua guardando só os nomes simples
    (ex: "entrada_pdfs"), pra ficar fácil de editar à mão.
    """
    resolvido = dict(config)

    for chave in PASTAS_CONFIGURAVEIS:
        valor = resolvido.get(chave)

        if valor:
            caminho = Path(valor)

            if not caminho.is_absolute():
                caminho = PROJECT_ROOT / caminho

            resolvido[chave] = str(caminho)

    return resolvido


def carregar_config():
    if not CONFIG_PATH.exists():
        config = CONFIG_PADRAO.copy()
        salvar_config(config)
        return resolver_pastas(config)

    try:
        with open(
            CONFIG_PATH,
            "r",
            encoding="utf-8"
        ) as arquivo:
            config_usuario = json.load(arquivo)

    except (
        json.JSONDecodeError,
        OSError
    ):
        config = CONFIG_PADRAO.copy()
        salvar_config(config)
        return resolver_pastas(config)

    if not isinstance(config_usuario, dict):
        config = CONFIG_PADRAO.copy()
        salvar_config(config)
        return resolver_pastas(config)

    config = CONFIG_PADRAO.copy()
    config.update(config_usuario)

    if config != config_usuario:
        salvar_config(config)

    return resolver_pastas(config)
