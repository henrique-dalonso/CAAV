import json

import pytest

from app.ferramentas.extratus.core.config_manager import (
    CONFIG_PATH,
    atualizar_config_robo,
    carregar_config_bruto,
)


@pytest.fixture
def preservar_config_json():
    """atualizar_config_robo grava no config.json real (não há um de
    teste separado) — salva e restaura o conteúdo original pra não
    deixar a configuração da máquina alterada depois do teste."""
    conteudo_original = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else None

    yield

    if conteudo_original is not None:
        CONFIG_PATH.write_text(conteudo_original, encoding="utf-8")


def test_atualizar_config_robo_grava_pasta_e_provider(preservar_config_json):
    atualizar_config_robo(pasta_entrada="uma/pasta/de/teste", ia_provider="claude")

    salvo = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert salvo["robo_pasta_entrada"] == "uma/pasta/de/teste"
    assert salvo["ia_provider"] == "claude"


def test_atualizar_config_robo_rejeita_provider_invalido(preservar_config_json):
    with pytest.raises(ValueError):
        atualizar_config_robo(pasta_entrada="qualquer", ia_provider="modelo-inventado")


def test_atualizar_config_robo_rejeita_pasta_vazia(preservar_config_json):
    with pytest.raises(ValueError):
        atualizar_config_robo(pasta_entrada="   ", ia_provider="claude")


def test_carregar_config_bruto_nao_resolve_caminho_absoluto(preservar_config_json):
    atualizar_config_robo(pasta_entrada="relativa/de/teste", ia_provider="claude")

    bruto = carregar_config_bruto()
    assert bruto["robo_pasta_entrada"] == "relativa/de/teste"
