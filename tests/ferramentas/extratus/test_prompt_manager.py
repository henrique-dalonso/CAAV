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


def test_metadados_prompt_sem_historico_ainda(prompt_de_teste):
    metadados = prompt_manager.obter_metadados_prompt()

    assert metadados["atualizado_em"] is not None
    assert metadados["total_versoes_anteriores"] == 0


def test_metadados_prompt_conta_versoes_apos_substituicoes(prompt_de_teste):
    prompt_manager.substituir_instrucoes_relatorio("versao 2".encode("utf-8"))
    prompt_manager.substituir_instrucoes_relatorio("versao 3".encode("utf-8"))

    metadados = prompt_manager.obter_metadados_prompt()

    assert metadados["total_versoes_anteriores"] == 2


def test_listar_versoes_prompt_vazio_sem_historico(prompt_de_teste):
    assert prompt_manager.listar_versoes_prompt() == []


def test_listar_versoes_prompt_mais_recente_primeiro(prompt_de_teste):
    prompt_manager.substituir_instrucoes_relatorio("versao 2".encode("utf-8"))
    prompt_manager.substituir_instrucoes_relatorio("versao 3".encode("utf-8"))

    versoes = prompt_manager.listar_versoes_prompt()

    assert len(versoes) == 2
    conteudos = [
        (prompt_manager.HISTORICO_PROMPTS_DIR / v["nome_arquivo"]).read_text(encoding="utf-8")
        for v in versoes
    ]
    # "versao 2" foi guardada por último (é o backup feito ao subir
    # "versao 3"), então deve vir primeiro na lista.
    assert conteudos == ["versao 2", "instrucoes originais"]


def test_ativar_versao_prompt_troca_a_ativa_e_guarda_a_atual(prompt_de_teste):
    prompt_manager.substituir_instrucoes_relatorio("versao 2".encode("utf-8"))
    versao_original = prompt_manager.listar_versoes_prompt()[0]

    prompt_manager.ativar_versao_prompt(versao_original["nome_arquivo"])

    assert prompt_manager.carregar_instrucoes_relatorio() == "instrucoes originais"
    # "versao 2" (que estava ativa) agora tem que estar guardada no lugar.
    versoes_depois = prompt_manager.listar_versoes_prompt()
    conteudos = [
        (prompt_manager.HISTORICO_PROMPTS_DIR / v["nome_arquivo"]).read_text(encoding="utf-8")
        for v in versoes_depois
    ]
    assert "versao 2" in conteudos


def test_ativar_versao_prompt_inexistente_leva_erro_claro(prompt_de_teste):
    with pytest.raises(ValueError):
        prompt_manager.ativar_versao_prompt("nao_existe.txt")


def test_ativar_versao_prompt_ignora_tentativa_de_escapar_da_pasta(prompt_de_teste):
    # nome_arquivo malicioso ("../instrucoes_relatorio.txt" tentando
    # apontar pro próprio PROMPT_PATH fora de HISTORICO_PROMPTS_DIR) —
    # Path(...).name descarta a parte de caminho, sobra só o nome, que
    # não existe dentro do histórico (vazio no teste) — devolve erro,
    # não segue o caminho de fora.
    with pytest.raises(ValueError):
        prompt_manager.ativar_versao_prompt("../instrucoes_relatorio.txt")
