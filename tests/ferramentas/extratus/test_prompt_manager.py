import pytest

from app.ferramentas.extratus.core import prompt_manager


@pytest.fixture
def prompt_de_teste(tmp_path, monkeypatch):
    """Aponta PROMPT_PATH/HISTORICO_PROMPTS_DIR pra uma pasta temporária,
    pra nenhum teste jamais escrever em cima do prompt real do Max."""
    caminho = tmp_path / "instrucoes_relatorio.txt"
    caminho.write_text("instrucoes originais", encoding="utf-8")

    monkeypatch.setattr(prompt_manager, "PROMPT_PATH", caminho)
    monkeypatch.setattr(prompt_manager, "HISTORICO_PROMPTS_DIR", tmp_path / "historico_prompts")

    return caminho


def test_extensao_esperada_prompt(prompt_de_teste):
    assert prompt_manager.extensao_esperada_prompt() == ".txt"


def test_substituir_instrucoes_relatorio_sobrescreve_o_arquivo(prompt_de_teste):
    prompt_manager.substituir_instrucoes_relatorio("instrucoes novas".encode("utf-8"))

    assert prompt_manager.carregar_instrucoes_relatorio() == "instrucoes novas"


def test_substituir_instrucoes_relatorio_guarda_backup_do_anterior(prompt_de_teste):
    prompt_manager.substituir_instrucoes_relatorio("instrucoes novas".encode("utf-8"))

    backups = list(prompt_manager.HISTORICO_PROMPTS_DIR.glob("*.txt"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "instrucoes originais"


def test_substituir_instrucoes_relatorio_rejeita_conteudo_nao_utf8(prompt_de_teste):
    conteudo_binario = bytes([0xFF, 0xFE, 0x00, 0x01, 0x02])

    with pytest.raises(ValueError):
        prompt_manager.substituir_instrucoes_relatorio(conteudo_binario)

    # Conteudo original preservado -- upload invalido nao pode corromper o prompt.
    assert prompt_manager.carregar_instrucoes_relatorio() == "instrucoes originais"
