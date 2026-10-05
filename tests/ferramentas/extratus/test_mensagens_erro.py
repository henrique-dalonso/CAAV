from unittest.mock import patch

from app.ferramentas.nucleo_relatorios.core import pipeline
from app.ferramentas.nucleo_relatorios.core.erros import (
    MENSAGEM_POR_TIPO_ERRO,
    ErroParaUsuario,
    montar_mensagem_recusados,
    motivo_liberacao_manual,
    separar_mensagem_e_detalhe,
)
from app.ferramentas.nucleo_relatorios.core.pipeline import montar_motivo_revisao_pos_ia


def test_erro_escrito_pra_tela_vai_como_esta_sem_detalhe():
    mensagem, detalhe = separar_mensagem_e_detalhe(ErroParaUsuario("Texto pra tela."), "erro_ia")

    assert mensagem == "Texto pra tela."
    assert detalhe is None


def test_excecao_tecnica_vira_frase_da_etapa_e_detalhe_cru_fica_separado():
    mensagem, detalhe = separar_mensagem_e_detalhe(ValueError("PdfReadError: EOF marker not found"), "erro_pdf")

    assert mensagem == MENSAGEM_POR_TIPO_ERRO["erro_pdf"]
    assert detalhe == "PdfReadError: EOF marker not found"


def test_tratar_erro_grava_frase_amigavel_e_detalhe_no_job(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF")

    with patch.object(pipeline, "mover_para_erros", return_value=None), \
         patch.object(pipeline, "registrar_erro") as registrar:
        resultado = pipeline.tratar_erro(pdf, None, "erro_docx", OSError("disk full"), tmp_path)

    kwargs = registrar.call_args.kwargs
    assert kwargs["erro_mensagem"] == MENSAGEM_POR_TIPO_ERRO["erro_docx"]
    assert kwargs["erro_detalhe"] == "disk full"
    assert resultado["erro"] == MENSAGEM_POR_TIPO_ERRO["erro_docx"]


def test_motivo_revisao_sem_nenhum_caminho_arriscado_e_none():
    assert montar_motivo_revisao_pos_ia(False, 0, 0) is None


def test_motivo_revisao_junta_as_medidas_de_barateamento():
    motivo = montar_motivo_revisao_pos_ia(False, 3, 2)

    assert motivo == (
        "Medidas de barateamento foram aplicadas: 3 páginas removidas automaticamente "
        "e 2 páginas sem conteúdo seguro foram resgatadas. Recomenda-se revisão manual."
    )


def test_motivo_revisao_usa_singular_com_uma_pagina():
    motivo = montar_motivo_revisao_pos_ia(False, 1, 1)

    assert "1 página removida automaticamente" in motivo
    assert "1 página sem conteúdo seguro foi resgatada" in motivo


def test_motivo_revisao_processo_dividido_sozinho():
    motivo = montar_motivo_revisao_pos_ia(True, 0, 0)

    assert motivo.startswith("O processo foi dividido em partes")
    assert "barateamento" not in motivo
    assert motivo.endswith("Recomenda-se revisão manual.")


def test_mensagem_recusados_um_arquivo_por_linha():
    mensagem = montar_mensagem_recusados(2, [("a.txt", "motivo a"), ("b.pdf", "motivo b")])

    assert mensagem.split("\n") == [
        "2 arquivo(s) enviado(s). Os seguintes arquivos foram recusados:",
        '- Arquivo "a.txt" → MOTIVO: motivo a.',
        '- Arquivo "b.pdf" → MOTIVO: motivo b.',
    ]


def test_liberacao_manual_cita_quem_liberou():
    assert "por Fulano de Tal" in motivo_liberacao_manual("Fulano de Tal")
    assert "por" not in motivo_liberacao_manual(None).split("manualmente")[1].split("após")[0]
