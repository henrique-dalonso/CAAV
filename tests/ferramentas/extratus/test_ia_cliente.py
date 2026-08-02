from types import SimpleNamespace

from app.ferramentas.extratus.core.ia_cliente import (
    LIMITE_MB_ARQUIVO_PARA_PDF_NATIVO,
    LIMITE_TOKENS_TEXTO_EXTRAIDO,
    cabe_no_limite_pdf_nativo,
    estimar_tokens_texto,
    extrair_dados_e_uso,
    parece_digitalizado,
)


def test_parece_digitalizado_quando_maioria_das_paginas_sem_texto():
    assert parece_digitalizado(total_paginas=10, paginas_sem_texto=5) is True


def test_nao_parece_digitalizado_quando_poucas_paginas_sem_texto():
    # 1 de 20 páginas sem texto (5%) — abaixo do limite de 15%, é PDF nativo normal.
    assert parece_digitalizado(total_paginas=20, paginas_sem_texto=1) is False


def test_parece_digitalizado_no_limite_exato_conta_como_nao_digitalizado():
    # Exatamente 15% não deve disparar (o teste real usa ">" estrito).
    assert parece_digitalizado(total_paginas=100, paginas_sem_texto=15) is False


def test_parece_digitalizado_zero_paginas_e_tratado_como_digitalizado():
    assert parece_digitalizado(total_paginas=0, paginas_sem_texto=0) is True


def test_estimar_tokens_texto_proporcional_ao_tamanho():
    texto = "a" * 1000
    assert estimar_tokens_texto(texto) == 600


def test_estimar_tokens_texto_vazio():
    assert estimar_tokens_texto("") == 0


def test_cabe_no_limite_pdf_nativo_arquivo_pequeno(tmp_path):
    arquivo = tmp_path / "pequeno.pdf"
    arquivo.write_bytes(b"0" * 1_000_000)  # 1MB

    assert cabe_no_limite_pdf_nativo(arquivo) is True


def test_cabe_no_limite_pdf_nativo_arquivo_grande_demais(tmp_path):
    arquivo = tmp_path / "grande.pdf"
    tamanho_bytes = (LIMITE_MB_ARQUIVO_PARA_PDF_NATIVO + 1) * 1_000_000
    arquivo.write_bytes(b"0" * tamanho_bytes)

    assert cabe_no_limite_pdf_nativo(arquivo) is False


def test_limite_tokens_texto_extraido_deixa_folga_da_janela_de_contexto():
    # Sanity check do valor em si: tem que deixar espaço pra prompt/schema/
    # resposta dentro da janela de 200 mil tokens do modelo.
    assert LIMITE_TOKENS_TEXTO_EXTRAIDO < 200_000


def _resposta_fake(tokens_entrada=100_000, tokens_saida=1_000):
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input={"campo": "valor"})],
        usage=SimpleNamespace(
            input_tokens=tokens_entrada,
            output_tokens=tokens_saida,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        ),
    )


def test_extrair_dados_e_uso_preco_cheio_por_padrao():
    _, uso_ia = extrair_dados_e_uso(_resposta_fake())
    assert uso_ia["custo_estimado_usd"] == round(100_000 / 1e6 * 2.00 + 1_000 / 1e6 * 10.00, 4)


def test_extrair_dados_e_uso_aplica_desconto_do_batch():
    _, uso_normal = extrair_dados_e_uso(_resposta_fake(), via_batch=False)
    _, uso_batch = extrair_dados_e_uso(_resposta_fake(), via_batch=True)

    assert uso_batch["custo_estimado_usd"] == round(uso_normal["custo_estimado_usd"] / 2, 4)
