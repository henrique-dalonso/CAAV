from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.ferramentas.extratus_aburesi.core.ia_cliente import (
    LIMITE_MB_ARQUIVO_PARA_PDF_NATIVO,
    LIMITE_TOKENS_TEXTO_EXTRAIDO,
    MODELO_PADRAO,
    MODELO_PEDACO,
    _agregar_pedacos,
    _dividir_paginas_em_pedacos,
    _montar_parametros_pedaco,
    _montar_parametros_reducao,
    _pagina_parece_lista_de_terceiros,
    cabe_no_limite_pdf_nativo,
    estimar_tokens_texto,
    extrair_dados_e_uso,
    filtrar_paginas_lista_de_terceiros,
    gerar_relatorio_claude_dividido,
    montar_diagnostico_com_triagem,
    parece_digitalizado,
)


def test_parece_digitalizado_quando_maioria_das_paginas_sem_texto():
    assert parece_digitalizado(total_paginas=10, paginas_sem_texto=5) is True


def test_nao_parece_digitalizado_quando_poucas_paginas_sem_texto():
    assert parece_digitalizado(total_paginas=20, paginas_sem_texto=1) is False


def test_estimar_tokens_texto_proporcional_ao_tamanho():
    assert estimar_tokens_texto("a" * 1000) == 600


def test_cabe_no_limite_pdf_nativo_arquivo_grande_demais(tmp_path):
    arquivo = tmp_path / "grande.pdf"
    tamanho_bytes = (LIMITE_MB_ARQUIVO_PARA_PDF_NATIVO + 1) * 1_000_000
    arquivo.write_bytes(b"0" * tamanho_bytes)

    assert cabe_no_limite_pdf_nativo(arquivo) is False


def test_limite_tokens_texto_extraido_deixa_folga_da_janela_de_contexto():
    # Sanity check do valor em si: tem que deixar espaço pra prompt/schema/
    # resposta dentro da janela real de 1 milhão de tokens do Sonnet 5.
    assert LIMITE_TOKENS_TEXTO_EXTRAIDO < 1_000_000


def _resposta_fake(tokens_entrada=100_000, tokens_saida=1_000, modelo=None):
    return SimpleNamespace(
        model=modelo,
        content=[SimpleNamespace(type="tool_use", input={"campo": "valor"})],
        usage=SimpleNamespace(
            input_tokens=tokens_entrada,
            output_tokens=tokens_saida,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )


def test_extrair_dados_e_uso_aplica_desconto_do_batch():
    _, uso_normal = extrair_dados_e_uso(_resposta_fake(modelo=MODELO_PADRAO), via_batch=False)
    _, uso_batch = extrair_dados_e_uso(_resposta_fake(modelo=MODELO_PADRAO), via_batch=True)

    assert uso_batch["custo_estimado_usd"] == round(uso_normal["custo_estimado_usd"] / 2, 4)


def test_extrair_dados_e_uso_cobra_preco_do_modelo_pedaco_quando_foi_ele_que_respondeu():
    # Modelo mais barato (Haiku) usado na etapa de pedaço — o custo tem que
    # refletir o preço DELE, não o do modelo padrão (Sonnet), senão o
    # Histórico infla o gasto real da etapa mais barata.
    _, uso_ia = extrair_dados_e_uso(_resposta_fake(modelo=MODELO_PEDACO))
    assert uso_ia["custo_estimado_usd"] == round(100_000 / 1e6 * 1.00 + 1_000 / 1e6 * 5.00, 4)
    assert uso_ia["modelo"] == MODELO_PEDACO


def test_extrair_dados_e_uso_sem_model_na_resposta_cai_no_preco_padrao():
    # `resposta.model` ausente (só acontece em resposta fake/mock de teste,
    # a API real sempre devolve) não pode quebrar — cai no preço padrão.
    resposta_sem_model = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input={"campo": "valor"})],
        usage=SimpleNamespace(
            input_tokens=100_000, output_tokens=1_000,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
        ),
    )
    _, uso_ia = extrair_dados_e_uso(resposta_sem_model)
    assert uso_ia["custo_estimado_usd"] == round(100_000 / 1e6 * 2.00 + 1_000 / 1e6 * 10.00, 4)
    assert uso_ia["modelo"] == MODELO_PADRAO


def test_montar_parametros_pedaco_usa_modelo_mais_barato():
    parametros = _montar_parametros_pedaco("texto do pedaço", 1, 2, "0000000-00.2026.8.06.0300", "instruções")
    assert parametros["model"] == MODELO_PEDACO


def test_montar_parametros_reducao_usa_modelo_padrao():
    parametros = _montar_parametros_reducao("resumo consolidado", "0000000-00.2026.8.06.0300", "instruções")
    assert parametros["model"] == MODELO_PADRAO


# --- Divisão de processos grandes em pedaços (map-reduce) ---

def _pagina_fake(numero, caracteres):
    return {"numero": numero, "texto_marcado": "a" * caracteres}


def test_dividir_paginas_agrupa_ate_o_limite_de_tokens():
    paginas = [_pagina_fake(i, 1000) for i in range(1, 21)]

    pedacos = _dividir_paginas_em_pedacos(paginas, limite_tokens_por_pedaco=1500)

    assert len(pedacos) == 10
    for pedaco in pedacos:
        assert pedaco.count("a" * 1000) == 2


def test_dividir_paginas_pagina_unica_maior_que_limite_nao_trava():
    paginas = [_pagina_fake(1, 10_000)]

    pedacos = _dividir_paginas_em_pedacos(paginas, limite_tokens_por_pedaco=100)

    assert len(pedacos) == 1


def test_dividir_paginas_lista_vazia():
    assert _dividir_paginas_em_pedacos([], limite_tokens_por_pedaco=1000) == []


def test_agregar_pedacos_junta_cronologia_e_documentos_por_pedaco():
    resultados = [
        {
            "cronologia": [{"data": "01/01/2020", "ator": "Autor", "descricao": "Petição inicial"}],
            "documentos_identificados": ["petição inicial"],
            "campos_processo": {"valor_causa": "R$ 1.000,00"},
        },
        {
            "cronologia": [{"data": "02/02/2020", "ator": "Juiz", "descricao": "Decisão"}],
            "documentos_identificados": ["decisão"],
            "campos_processo": {},
        },
    ]

    cronologia, documentos_por_pedaco, campos = _agregar_pedacos(resultados)

    assert len(cronologia) == 2
    assert documentos_por_pedaco == [(1, ["petição inicial"]), (2, ["decisão"])]
    assert campos == {"valor_causa": ["R$ 1.000,00"]}


def test_agregar_pedacos_campos_divergentes_viram_lista_de_candidatos():
    resultados = [
        {"cronologia": [], "documentos_identificados": [], "campos_processo": {"valor_causa": "R$ 1.000,00"}},
        {"cronologia": [], "documentos_identificados": [], "campos_processo": {"valor_causa": "R$ 1000"}},
    ]

    _, _, campos = _agregar_pedacos(resultados)

    assert campos["valor_causa"] == ["R$ 1.000,00", "R$ 1000"]


def _resposta_pedaco_fake(descricao):
    return SimpleNamespace(
        content=[SimpleNamespace(
            type="tool_use",
            input={
                "cronologia": [{"data": "01/01/2020", "ator": "Autor", "descricao": descricao}],
                "documentos_identificados": [descricao],
                "campos_processo": {},
            },
        )],
        usage=SimpleNamespace(
            input_tokens=10_000, output_tokens=200,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
        ),
    )


def _resposta_reducao_fake():
    return SimpleNamespace(
        content=[SimpleNamespace(
            type="tool_use",
            input={
                "tipo_acao": "Execução", "numero_processo": "0000000-00.2026.8.06.0300",
                "valor_causa": "R$ 1.000,00", "valor_divida": "R$ 1.000,00",
                "autor": "Banco X", "reu": "Fulano", "comarca": "Comarca X",
                "cronologia": [], "parecer": "Parecer final.", "status_atual": "Em andamento",
            },
        )],
        usage=SimpleNamespace(
            input_tokens=5_000, output_tokens=800,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
        ),
    )


def test_gerar_relatorio_claude_dividido_faz_uma_chamada_por_pedaco_mais_reducao(tmp_path):
    arquivo = tmp_path / "processo_grande.pdf"
    arquivo.write_bytes(b"%PDF-1.4 fake")

    cliente_fake = MagicMock()
    cliente_fake.messages.create.side_effect = [
        _resposta_pedaco_fake("trecho 1"),
        _resposta_pedaco_fake("trecho 2"),
        _resposta_reducao_fake(),
    ]

    with patch(
        "app.ferramentas.extratus_aburesi.core.ia_cliente.extrair_paginas_pdf",
        return_value=([], 2),
    ), patch(
        "app.ferramentas.extratus_aburesi.core.ia_cliente._dividir_paginas_em_pedacos",
        return_value=["texto do pedaço 1", "texto do pedaço 2"],
    ):
        dados, uso = gerar_relatorio_claude_dividido(arquivo, "0000000-00.2026.8.06.0300", cliente_fake, "instruções")

    assert cliente_fake.messages.create.call_count == 3
    assert dados["parecer"] == "Parecer final."
    assert uso["dividido"] is True
    assert uso["total_pedacos"] == 2
    tokens_entrada_esperado = 10_000 + 10_000 + 5_000
    tokens_saida_esperado = 200 + 200 + 800
    custo_esperado = round(
        tokens_entrada_esperado / 1e6 * 2.00 + tokens_saida_esperado / 1e6 * 10.00, 4
    )
    assert uso["tokens_entrada"] == tokens_entrada_esperado
    assert uso["tokens_saida"] == tokens_saida_esperado
    assert uso["custo_estimado_usd"] == custo_esperado


# --- Triagem de anexos de listagem de terceiros (cessão de carteira de crédito) ---

def _texto_lista_terceiros(quantidade_cpfs=15):
    linhas = "\n".join(
        f"{i:03d}.{i:03d}.{i:03d}-{i % 100:02d} NOME FULANO {i}" for i in range(quantidade_cpfs)
    )
    return f"Página 5 de 281\nANEXO I do Termo de Cessão\n{linhas}"


def test_pagina_parece_lista_de_terceiros_com_os_dois_sinais():
    assert _pagina_parece_lista_de_terceiros(_texto_lista_terceiros(15)) is True


def test_pagina_normal_do_processo_nao_parece_lista_de_terceiros():
    texto = "Vistos. Defiro o pedido de busca e apreensão do bem. CPF do réu: 123.456.789-00."
    assert _pagina_parece_lista_de_terceiros(texto) is False


def test_filtrar_paginas_separa_suspeitas_sem_perder_nenhuma():
    paginas = [
        {"numero": 1, "texto_bruto": "Vistos. Defiro o pedido."},
        {"numero": 2, "texto_bruto": _texto_lista_terceiros(15)},
        {"numero": 3, "texto_bruto": "Intime-se a parte ré."},
    ]

    relevantes, excluidas = filtrar_paginas_lista_de_terceiros(paginas)

    assert [p["numero"] for p in relevantes] == [1, 3]
    assert excluidas == [2]


def _pagina_fake_completa(numero, texto_bruto):
    return {"numero": numero, "texto_bruto": texto_bruto, "texto_marcado": f"--- Página {numero} ---\n{texto_bruto}"}


def test_montar_diagnostico_com_triagem_remove_paginas_suspeitas():
    paginas_fake = [
        _pagina_fake_completa(1, "Vistos. Defiro o pedido de busca e apreensão."),
        _pagina_fake_completa(2, _texto_lista_terceiros(15)),
    ]
    diagnostico_original_fake = {
        "texto": "\n\n".join(p["texto_marcado"] for p in paginas_fake),
        "total_paginas": 2,
        "paginas_sem_texto": 0,
        "caracteres": 500,
    }

    with patch(
        "app.ferramentas.extratus_aburesi.core.ia_cliente.extrair_texto_pdf_com_diagnostico",
        return_value=diagnostico_original_fake,
    ), patch(
        "app.ferramentas.extratus_aburesi.core.ia_cliente.extrair_paginas_pdf",
        return_value=(paginas_fake, 2),
    ):
        diagnostico, paginas_relevantes, paginas_excluidas = montar_diagnostico_com_triagem("qualquer.pdf")

    assert paginas_excluidas == [2]
    assert [p["numero"] for p in paginas_relevantes] == [1]
    assert "removidas desta análise" in diagnostico["texto"]
    assert "NOME FULANO" not in diagnostico["texto"]


def test_montar_diagnostico_documento_digitalizado_nao_aplica_triagem():
    diagnostico_digitalizado = {"texto": "", "total_paginas": 10, "paginas_sem_texto": 9, "caracteres": 0}

    with patch(
        "app.ferramentas.extratus_aburesi.core.ia_cliente.extrair_texto_pdf_com_diagnostico",
        return_value=diagnostico_digitalizado,
    ), patch(
        "app.ferramentas.extratus_aburesi.core.ia_cliente.extrair_paginas_pdf",
    ) as extrair_paginas_mock:
        diagnostico, paginas_relevantes, paginas_excluidas = montar_diagnostico_com_triagem("qualquer.pdf")

    extrair_paginas_mock.assert_not_called()
    assert diagnostico == diagnostico_digitalizado
    assert paginas_relevantes is None
    assert paginas_excluidas == []
