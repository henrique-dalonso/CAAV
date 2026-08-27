from unittest.mock import patch

from app.ferramentas.extratus_aburesi.core import pipeline


def test_processo_dividido_forca_confianca_revisao_mesmo_com_deteccao_alta():
    with patch.object(
        pipeline, "obter_dados_deteccao",
        return_value=("0000000-00.2026.8.06.0300", {"nivel": "alta", "motivo": "regex bateu"}),
    ), patch.object(
        pipeline, "gerar_relatorio",
        return_value=({"parecer": "..."}, {"dividido": True, "total_pedacos": 5, "custo_estimado_usd": 1.23}),
    ), patch.object(
        pipeline, "finalizar_processamento", return_value={"sucesso": True},
    ) as finalizar_mock:
        pipeline.processar_pdf(
            "processo.pdf", "saida", "processados", "erros", "revisao",
            ia_provider="claude",
        )

    confianca_usada = finalizar_mock.call_args.args[2]
    assert confianca_usada["nivel"] == "revisao"


def test_processo_com_paginas_excluidas_por_triagem_forca_confianca_revisao():
    with patch.object(
        pipeline, "obter_dados_deteccao",
        return_value=("0000000-00.2026.8.06.0300", {"nivel": "alta", "motivo": "regex bateu"}),
    ), patch.object(
        pipeline, "gerar_relatorio",
        return_value=({"parecer": "..."}, {"paginas_excluidas_triagem": [33, 34, 35], "custo_estimado_usd": 0.30}),
    ), patch.object(
        pipeline, "finalizar_processamento", return_value={"sucesso": True},
    ) as finalizar_mock:
        pipeline.processar_pdf(
            "processo.pdf", "saida", "processados", "erros", "revisao",
            ia_provider="claude",
        )

    confianca_usada = finalizar_mock.call_args.args[2]
    assert confianca_usada["nivel"] == "revisao"
    assert "3 página" in confianca_usada["motivo"]


def test_processo_com_pagina_resgatada_por_transcricao_forca_confianca_revisao():
    """Ver docstring equivalente em tests/ferramentas/extratus/
    test_pipeline.py."""
    with patch.object(
        pipeline, "obter_dados_deteccao",
        return_value=("0000000-00.2026.8.06.0300", {"nivel": "alta", "motivo": "regex bateu"}),
    ), patch.object(
        pipeline, "gerar_relatorio",
        return_value=({"parecer": "..."}, {"paginas_transcritas": [7], "custo_estimado_usd": 0.31}),
    ), patch.object(
        pipeline, "finalizar_processamento", return_value={"sucesso": True},
    ) as finalizar_mock:
        pipeline.processar_pdf(
            "processo.pdf", "saida", "processados", "erros", "revisao",
            ia_provider="claude",
        )

    confianca_usada = finalizar_mock.call_args.args[2]
    assert confianca_usada["nivel"] == "revisao"
    assert "1 página" in confianca_usada["motivo"]


def test_processo_normal_mantem_confianca_da_deteccao():
    with patch.object(
        pipeline, "obter_dados_deteccao",
        return_value=("0000000-00.2026.8.06.0300", {"nivel": "alta", "motivo": "regex bateu"}),
    ), patch.object(
        pipeline, "gerar_relatorio",
        return_value=({"parecer": "..."}, {"custo_estimado_usd": 0.20}),
    ), patch.object(
        pipeline, "finalizar_processamento", return_value={"sucesso": True},
    ) as finalizar_mock:
        pipeline.processar_pdf(
            "processo.pdf", "saida", "processados", "erros", "revisao",
            ia_provider="claude",
        )

    confianca_usada = finalizar_mock.call_args.args[2]
    assert confianca_usada["nivel"] == "alta"
