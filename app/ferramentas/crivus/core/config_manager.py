import json

from app.plataforma.paths import PROJECT_ROOT


CRIVUS_ROOT = PROJECT_ROOT / "app" / "ferramentas" / "crivus"

CONFIG_PATH = CRIVUS_ROOT / "config" / "config_lote.json"


CONFIG_PADRAO = {
    # Henrique, 2026-09-14: Processamento em Lote já sobe LIGADO por
    # padrão (sem etapa de "testar desligado primeiro") — essa bandeira
    # existe pra permitir pausar depois, na tela de Configurações.
    "lote_ativo": True,
}


def salvar_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_PATH, "w", encoding="utf-8") as arquivo:
        json.dump(config, arquivo, ensure_ascii=False, indent=4)


def carregar_config():
    if not CONFIG_PATH.exists():
        config = CONFIG_PADRAO.copy()
        salvar_config(config)
        return config

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as arquivo:
            config_usuario = json.load(arquivo)
    except (json.JSONDecodeError, OSError):
        config_usuario = None

    if not isinstance(config_usuario, dict):
        config = CONFIG_PADRAO.copy()
        salvar_config(config)
        return config

    config = CONFIG_PADRAO.copy()
    config.update(config_usuario)

    if config != config_usuario:
        salvar_config(config)

    return config


def definir_lote_ativo(ativo: bool):
    config = carregar_config()
    config["lote_ativo"] = bool(ativo)
    salvar_config(config)
    return config["lote_ativo"]
