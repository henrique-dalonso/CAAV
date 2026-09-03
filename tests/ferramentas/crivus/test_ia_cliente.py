from types import SimpleNamespace

from app.ferramentas.crivus.core.ia_cliente import (
    FERRAMENTA_ANALISE_PUBLICACAO,
    MODELO_PADRAO,
    extrair_dados_e_uso,
    montar_parametros_mensagem,
)


def _resposta_fake(dados_ferramenta, modelo=MODELO_PADRAO, tokens_entrada=1000, tokens_saida=200):
    bloco = SimpleNamespace(type="tool_use", input=dados_ferramenta)
    usage = SimpleNamespace(
        input_tokens=tokens_entrada,
        output_tokens=tokens_saida,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    return SimpleNamespace(content=[bloco], usage=usage, model=modelo)


def test_extrair_dados_e_uso_calcula_custo_pelo_modelo_padrao():
    dados_ferramenta = {
        "leitura_publicacao": "texto",
        "conclusao_operacional": "texto",
        "nivel_confianca": "ALTO",
        "tem_alerta_critico": False,
        "acompanhamentos": [],
        "agendamentos": [],
    }
    resposta = _resposta_fake(dados_ferramenta, tokens_entrada=1_000_000, tokens_saida=1_000_000)

    dados, uso = extrair_dados_e_uso(resposta)

    assert dados == dados_ferramenta
    assert uso["modelo"] == MODELO_PADRAO
    # 1M de entrada a $2 + 1M de saída a $10 = $12
    assert uso["custo_estimado_usd"] == 12.0
    assert uso["tokens_entrada"] == 1_000_000
    assert uso["tokens_saida"] == 1_000_000


def test_extrair_dados_e_uso_sem_tool_use_levanta_erro():
    resposta = SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")], usage=None, model=MODELO_PADRAO)

    try:
        extrair_dados_e_uso(resposta)
        assert False, "deveria ter levantado RuntimeError"
    except RuntimeError:
        pass


def test_montar_parametros_mensagem_forca_a_ferramenta_estruturada():
    parametros = montar_parametros_mensagem("teor de teste qualquer")

    assert parametros["model"] == MODELO_PADRAO
    assert parametros["tool_choice"] == {"type": "tool", "name": "registrar_analise_publicacao"}
    assert parametros["tools"] == [FERRAMENTA_ANALISE_PUBLICACAO]
    assert parametros["system"][0]["cache_control"] == {"type": "ephemeral"}

    texto_usuario = parametros["messages"][0]["content"][0]["text"]
    assert "teor de teste qualquer" in texto_usuario


def test_montar_parametros_mensagem_sem_anexos_nao_adiciona_blocos_extras():
    parametros = montar_parametros_mensagem("teor sem anexo")
    conteudo = parametros["messages"][0]["content"]

    # só o bloco do teor + o pedido de análise, nenhum documento/imagem
    assert len(conteudo) == 2
    assert all(bloco["type"] == "text" for bloco in conteudo)
