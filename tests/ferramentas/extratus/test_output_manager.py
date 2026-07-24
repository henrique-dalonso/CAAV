from app.ferramentas.extratus.core.output_manager import gerar_caminho_unico, mover_por_confianca


def test_gerar_caminho_unico_devolve_mesmo_caminho_se_nao_existe(tmp_path):
    alvo = tmp_path / "relatorio.docx"
    assert gerar_caminho_unico(alvo) == alvo


def test_gerar_caminho_unico_evita_sobrescrever(tmp_path):
    alvo = tmp_path / "relatorio.docx"
    alvo.write_text("já existe")

    resultado = gerar_caminho_unico(alvo)

    assert resultado != alvo
    assert resultado.name == "relatorio_1.docx"


def test_gerar_caminho_unico_incrementa_ate_achar_livre(tmp_path):
    (tmp_path / "relatorio.docx").write_text("x")
    (tmp_path / "relatorio_1.docx").write_text("x")

    resultado = gerar_caminho_unico(tmp_path / "relatorio.docx")

    assert resultado.name == "relatorio_2.docx"


def test_mover_por_confianca_alta_vai_pra_processados(tmp_path):
    origem = tmp_path / "entrada" / "caso.pdf"
    origem.parent.mkdir()
    origem.write_bytes(b"%PDF-fake")

    destino = mover_por_confianca(
        origem, "alta", tmp_path / "processados", tmp_path / "revisao"
    )

    assert destino.parent.name == "processados"
    assert destino.exists()


def test_mover_por_confianca_media_vai_pra_revisao(tmp_path):
    origem = tmp_path / "entrada" / "caso.pdf"
    origem.parent.mkdir()
    origem.write_bytes(b"%PDF-fake")

    destino = mover_por_confianca(
        origem, "media", tmp_path / "processados", tmp_path / "revisao"
    )

    assert destino.parent.name == "revisao"


def test_mover_por_confianca_nivel_revisao_vai_pra_revisao_nao_erros(tmp_path):
    """Regressão: nível de confiança "revisao" já foi parar na pasta de
    erros por engano (bug corrigido em 2026-07-23) — trava isso pra não
    voltar a acontecer.
    """
    origem = tmp_path / "entrada" / "caso.pdf"
    origem.parent.mkdir()
    origem.write_bytes(b"%PDF-fake")

    destino = mover_por_confianca(
        origem, "revisao", tmp_path / "processados", tmp_path / "revisao"
    )

    assert destino.parent.name == "revisao"


def test_mover_por_confianca_valor_inesperado_vai_pra_revisao_por_seguranca(tmp_path):
    origem = tmp_path / "entrada" / "caso.pdf"
    origem.parent.mkdir()
    origem.write_bytes(b"%PDF-fake")

    destino = mover_por_confianca(
        origem, "valor-nunca-visto", tmp_path / "processados", tmp_path / "revisao"
    )

    assert destino.parent.name == "revisao"
