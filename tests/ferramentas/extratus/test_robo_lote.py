from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.ferramentas.extratus.core import robo_lote


CONFIG_EXEMPLO = {
    "robo_ativo": True,
    "robo_pasta_entrada": "/pasta/robô",
    "pasta_saida": "/pasta/saida",
    "pasta_processados": "/pasta/processados",
    "pasta_revisao": "/pasta/revisao",
    "pasta_erros": "/pasta/erros",
}


def test_rodar_ciclo_robo_nao_faz_nada_se_desligado_e_sem_lote_pendente():
    with patch.object(robo_lote, "carregar_config", return_value={"robo_ativo": False}), \
         patch.object(robo_lote, "listar_lotes_em_andamento", return_value=[]), \
         patch.object(robo_lote, "_obter_cliente") as cliente_mock:
        robo_lote.rodar_ciclo_robo()

    cliente_mock.assert_not_called()


def test_rodar_ciclo_robo_coleta_lote_pendente_mesmo_desligado():
    """Um lote já enviado pra Anthropic continua rodando do lado de lá
    independente do interruptor local — desligar o robô não pode deixar
    esse lote preso pra sempre sem nunca virar relatório."""
    with patch.object(robo_lote, "carregar_config", return_value={"robo_ativo": False}), \
         patch.object(robo_lote, "listar_lotes_em_andamento", return_value=[SimpleNamespace(id=1)]), \
         patch.object(robo_lote, "_obter_cliente", return_value=MagicMock()) as cliente_mock, \
         patch.object(robo_lote, "_coletar_lotes_pendentes", return_value=False) as coletar_mock, \
         patch.object(robo_lote, "_preparar_novo_lote") as preparar_mock, \
         patch.object(robo_lote, "_submeter_lote") as submeter_mock:
        robo_lote.rodar_ciclo_robo()

    cliente_mock.assert_called_once()
    coletar_mock.assert_called_once()
    # robô desligado: fecha o lote pendente, mas não abre lote novo
    preparar_mock.assert_not_called()
    submeter_mock.assert_not_called()


def test_rodar_ciclo_robo_nao_submete_novo_lote_se_ja_tem_um_em_voo():
    with patch.object(robo_lote, "carregar_config", return_value=CONFIG_EXEMPLO), \
         patch.object(robo_lote, "listar_lotes_em_andamento", return_value=[SimpleNamespace(id=1)]), \
         patch.object(robo_lote, "_obter_cliente", return_value=MagicMock()), \
         patch.object(robo_lote, "_coletar_lotes_pendentes", return_value=True) as coletar_mock, \
         patch.object(robo_lote, "_preparar_novo_lote") as preparar_mock, \
         patch.object(robo_lote, "_submeter_lote") as submeter_mock:
        robo_lote.rodar_ciclo_robo()

    coletar_mock.assert_called_once()
    preparar_mock.assert_not_called()
    submeter_mock.assert_not_called()


def test_rodar_ciclo_robo_submete_lote_quando_ha_itens_elegiveis():
    itens_fake = [{"custom_id": "x", "arquivo_pdf": "a.pdf"}]

    with patch.object(robo_lote, "carregar_config", return_value=CONFIG_EXEMPLO), \
         patch.object(robo_lote, "listar_lotes_em_andamento", return_value=[]), \
         patch.object(robo_lote, "_obter_cliente", return_value=MagicMock()), \
         patch.object(robo_lote, "_preparar_novo_lote", return_value=itens_fake), \
         patch.object(robo_lote, "_submeter_lote") as submeter_mock:
        robo_lote.rodar_ciclo_robo()

    submeter_mock.assert_called_once()


def test_rodar_ciclo_robo_nao_submete_nada_se_nenhum_arquivo_elegivel():
    with patch.object(robo_lote, "carregar_config", return_value=CONFIG_EXEMPLO), \
         patch.object(robo_lote, "listar_lotes_em_andamento", return_value=[]), \
         patch.object(robo_lote, "_obter_cliente", return_value=MagicMock()), \
         patch.object(robo_lote, "_preparar_novo_lote", return_value=[]), \
         patch.object(robo_lote, "_submeter_lote") as submeter_mock:
        robo_lote.rodar_ciclo_robo()

    submeter_mock.assert_not_called()


def _resultado_sucesso(custom_id):
    mensagem_fake = SimpleNamespace(content=[], usage=SimpleNamespace(
        input_tokens=100, output_tokens=10,
        cache_creation_input_tokens=0, cache_read_input_tokens=0,
    ))
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type="succeeded", message=mensagem_fake),
    )


def _resultado_erro(custom_id, tipo="errored"):
    return SimpleNamespace(custom_id=custom_id, result=SimpleNamespace(type=tipo))


def test_coletar_lotes_pendentes_finaliza_sucesso_e_erro_sem_derrubar_o_outro():
    lote_fake = SimpleNamespace(id=1, batch_id="msgbatch_teste")

    item_sucesso = SimpleNamespace(
        id=10, custom_id="ok", arquivo_pdf="ok.pdf",
        processo_detectado="123", confianca_nivel="alta", confianca_motivo="teste",
        custo_transcricao_usd=0.0, solicitante_id=None,
    )
    item_erro = SimpleNamespace(
        id=11, custom_id="falhou", arquivo_pdf="falhou.pdf",
        processo_detectado="456", confianca_nivel="alta", confianca_motivo="teste",
        custo_transcricao_usd=0.0, solicitante_id=None,
    )

    cliente_fake = MagicMock()
    cliente_fake.messages.batches.retrieve.return_value = SimpleNamespace(processing_status="ended")
    cliente_fake.messages.batches.results.return_value = [
        _resultado_sucesso("ok"),
        _resultado_erro("falhou"),
    ]

    with patch.object(robo_lote, "listar_lotes_em_andamento", return_value=[lote_fake]), \
         patch.object(robo_lote, "listar_itens_do_lote", return_value=[item_sucesso, item_erro]), \
         patch.object(robo_lote, "extrair_dados_e_uso", return_value=({"campo": "valor"}, {"custo_estimado_usd": 0.5})) as extrair_mock, \
         patch.object(robo_lote, "finalizar_processamento") as finalizar_mock, \
         patch.object(robo_lote, "tratar_erro") as tratar_erro_mock, \
         patch.object(robo_lote, "marcar_item_concluido") as marcar_item_mock, \
         patch.object(robo_lote, "marcar_lote_concluido") as marcar_lote_mock:
        ainda_em_andamento = robo_lote._coletar_lotes_pendentes(cliente_fake, CONFIG_EXEMPLO)

    assert ainda_em_andamento is False
    finalizar_mock.assert_called_once()
    tratar_erro_mock.assert_called_once()
    # o resultado de um lote sempre tem que aplicar o desconto do Batch API
    assert extrair_mock.call_args.kwargs.get("via_batch") is True
    assert marcar_item_mock.call_count == 2
    marcar_item_mock.assert_any_call(10, "sucesso")
    marcar_item_mock.assert_any_call(11, "erro")
    marcar_lote_mock.assert_called_once_with(1)


def test_coletar_lotes_pendentes_soma_custo_de_transcricao_ao_custo_final():
    """Regressão do resgate de página problemática (Henrique, 2026-08-26):
    o custo da transcrição foi pago ANTES do lote ser submetido (ver
    _preparar_novo_lote) e fica guardado em ItemLoteRobo.custo_transcricao_usd
    até o resultado do lote voltar — precisa ser somado aqui, senão o gasto
    real fica invisível no Histórico/Custos."""
    lote_fake = SimpleNamespace(id=1, batch_id="msgbatch_teste")
    item_transcrito = SimpleNamespace(
        id=20, custom_id="ok", arquivo_pdf="ok.pdf",
        processo_detectado="123", confianca_nivel="revisao", confianca_motivo="teste",
        custo_transcricao_usd=0.0123, solicitante_id=None,
    )

    cliente_fake = MagicMock()
    cliente_fake.messages.batches.retrieve.return_value = SimpleNamespace(processing_status="ended")
    cliente_fake.messages.batches.results.return_value = [_resultado_sucesso("ok")]

    uso_capturado = {}

    def _finalizar_fake(*args, **kwargs):
        uso_capturado.update(args[4])

    with patch.object(robo_lote, "listar_lotes_em_andamento", return_value=[lote_fake]), \
         patch.object(robo_lote, "listar_itens_do_lote", return_value=[item_transcrito]), \
         patch.object(robo_lote, "extrair_dados_e_uso", return_value=({"campo": "valor"}, {"custo_estimado_usd": 0.5})), \
         patch.object(robo_lote, "finalizar_processamento", side_effect=_finalizar_fake), \
         patch.object(robo_lote, "marcar_item_concluido"), \
         patch.object(robo_lote, "marcar_lote_concluido"):
        robo_lote._coletar_lotes_pendentes(cliente_fake, CONFIG_EXEMPLO)

    assert uso_capturado["custo_estimado_usd"] == 0.5123
    assert uso_capturado["custo_transcricao_usd"] == 0.0123


def test_coletar_lotes_pendentes_nao_mexe_em_lote_ainda_em_progresso():
    lote_fake = SimpleNamespace(id=1, batch_id="msgbatch_teste")

    cliente_fake = MagicMock()
    cliente_fake.messages.batches.retrieve.return_value = SimpleNamespace(processing_status="in_progress")

    with patch.object(robo_lote, "listar_lotes_em_andamento", return_value=[lote_fake]), \
         patch.object(robo_lote, "marcar_lote_concluido") as marcar_lote_mock:
        ainda_em_andamento = robo_lote._coletar_lotes_pendentes(cliente_fake, CONFIG_EXEMPLO)

    assert ainda_em_andamento is True
    marcar_lote_mock.assert_not_called()
    cliente_fake.messages.batches.results.assert_not_called()


def _checagem_aprovada(processo="123", nivel="alta", motivo="x", solicitante_id=None):
    """Simula uma linha de ChecagemFila já aprovada — robo_lote.py não
    detecta processo/confiança sozinho mais, só reaproveita o que a
    checagem (checagem_lote.py, roda em segundo plano) já detectou."""
    return SimpleNamespace(
        processo_detectado=processo, confianca_nivel=nivel, confianca_motivo=motivo,
        solicitante_id=solicitante_id,
    )


def test_preparar_novo_lote_ignora_arquivo_ja_reivindicado():
    pdf_ja_reivindicado = Path("/pasta/robô/ja_reivindicado.pdf")

    with patch.object(robo_lote, "listar_pdfs", return_value=[pdf_ja_reivindicado]), \
         patch.object(robo_lote, "listar_arquivos_ja_reivindicados", return_value={"ja_reivindicado.pdf"}), \
         patch.object(robo_lote, "listar_aprovados_por_nome", return_value={}), \
         patch.object(robo_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(robo_lote, "extrair_paginas_isolado") as extrair_mock:
        itens = robo_lote._preparar_novo_lote(CONFIG_EXEMPLO, MagicMock())

    assert itens == []
    extrair_mock.assert_not_called()


def test_preparar_novo_lote_ignora_arquivo_ainda_nao_aprovado_na_checagem():
    """Núcleo do que a checagem (2026-08-06) precisa garantir: um arquivo
    que ainda não tem checagem, ou que a checagem recusou (duplicado,
    processo não encontrado), nunca chega a entrar num lote — mesmo sem
    já estar "reivindicado" nem dar erro nenhum de montagem."""
    pdf_nao_aprovado = Path("/pasta/robô/nao_aprovado.pdf")

    with patch.object(robo_lote, "listar_pdfs", return_value=[pdf_nao_aprovado]), \
         patch.object(robo_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(robo_lote, "listar_aprovados_por_nome", return_value={}), \
         patch.object(robo_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(robo_lote, "extrair_paginas_isolado") as extrair_mock:
        itens = robo_lote._preparar_novo_lote(CONFIG_EXEMPLO, MagicMock())

    assert itens == []
    extrair_mock.assert_not_called()


def test_preparar_novo_lote_trata_erro_de_montagem_sem_incluir_no_lote():
    pdf_grande_demais = Path("/pasta/robô/grande.pdf")

    with patch.object(robo_lote, "listar_pdfs", return_value=[pdf_grande_demais]), \
         patch.object(robo_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(robo_lote, "listar_aprovados_por_nome", return_value={"grande.pdf": _checagem_aprovada()}), \
         patch.object(robo_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(robo_lote, "extrair_paginas_isolado", return_value=([], 0)), \
         patch.object(robo_lote, "montar_diagnostico_com_triagem", return_value=({}, None, [], [], 0.0)), \
         patch.object(robo_lote, "montar_parametros_mensagem", side_effect=RuntimeError("grande demais")), \
         patch.object(robo_lote, "tratar_erro") as tratar_erro_mock:
        itens = robo_lote._preparar_novo_lote(CONFIG_EXEMPLO, MagicMock())

    assert itens == []
    tratar_erro_mock.assert_called_once()
    assert tratar_erro_mock.call_args[0][2] == "erro_ia"


def test_preparar_novo_lote_inclui_arquivo_elegivel():
    pdf_ok = Path("/pasta/robô/ok.pdf")
    parametros_fake = {"model": "x"}
    cliente_fake = MagicMock()

    with patch.object(robo_lote, "listar_pdfs", return_value=[pdf_ok]), \
         patch.object(robo_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(robo_lote, "listar_aprovados_por_nome", return_value={"ok.pdf": _checagem_aprovada()}), \
         patch.object(robo_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(robo_lote, "extrair_paginas_isolado", return_value=([], 0)), \
         patch.object(robo_lote, "montar_diagnostico_com_triagem", return_value=({}, None, [], [], 0.0)) as diagnostico_mock, \
         patch.object(robo_lote, "montar_parametros_mensagem", return_value=parametros_fake):
        itens = robo_lote._preparar_novo_lote(CONFIG_EXEMPLO, cliente_fake)

    assert len(itens) == 1
    assert itens[0]["arquivo_pdf"] == "ok.pdf"
    assert itens[0]["processo_detectado"] == "123"
    assert itens[0]["params"] == parametros_fake
    assert itens[0]["confianca_nivel"] == "alta"
    assert itens[0]["custo_transcricao_usd"] == 0.0
    assert isinstance(itens[0]["custom_id"], str) and len(itens[0]["custom_id"]) > 0
    # o cliente real (não isolado em subprocesso) precisa chegar até a
    # triagem/resgate — ver docstring de extrair_paginas_isolado.
    assert diagnostico_mock.call_args.kwargs.get("cliente") is cliente_fake


def test_preparar_novo_lote_forca_revisao_quando_triagem_excluiu_paginas():
    pdf_com_anexo = Path("/pasta/robô/tem_anexo.pdf")
    parametros_fake = {"model": "x"}

    with patch.object(robo_lote, "listar_pdfs", return_value=[pdf_com_anexo]), \
         patch.object(robo_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(robo_lote, "listar_aprovados_por_nome", return_value={"tem_anexo.pdf": _checagem_aprovada(motivo="regex bateu")}), \
         patch.object(robo_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(robo_lote, "extrair_paginas_isolado", return_value=([], 0)), \
         patch.object(robo_lote, "montar_diagnostico_com_triagem", return_value=({}, None, [33, 34, 35], [], 0.0)), \
         patch.object(robo_lote, "montar_parametros_mensagem", return_value=parametros_fake):
        itens = robo_lote._preparar_novo_lote(CONFIG_EXEMPLO, MagicMock())

    assert len(itens) == 1
    assert itens[0]["confianca_nivel"] == "revisao"
    assert "3 página" in itens[0]["confianca_motivo"]


def test_preparar_novo_lote_forca_revisao_e_guarda_custo_quando_pagina_e_transcrita():
    """Regressão do achado real (Henrique, 2026-08-26): página resgatada
    por transcrição também força revisão manual (caminho novo, ainda em
    validação) e o custo da transcrição precisa sobreviver até o lote
    resultado voltar (ver ItemLoteRobo.custo_transcricao_usd)."""
    pdf_com_pagina_ruim = Path("/pasta/robô/pagina_ruim.pdf")
    parametros_fake = {"model": "x"}

    with patch.object(robo_lote, "listar_pdfs", return_value=[pdf_com_pagina_ruim]), \
         patch.object(robo_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(robo_lote, "listar_aprovados_por_nome", return_value={"pagina_ruim.pdf": _checagem_aprovada()}), \
         patch.object(robo_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(robo_lote, "extrair_paginas_isolado", return_value=([], 0)), \
         patch.object(robo_lote, "montar_diagnostico_com_triagem", return_value=({}, None, [], [7], 0.0123)), \
         patch.object(robo_lote, "montar_parametros_mensagem", return_value=parametros_fake):
        itens = robo_lote._preparar_novo_lote(CONFIG_EXEMPLO, MagicMock())

    assert len(itens) == 1
    assert itens[0]["confianca_nivel"] == "revisao"
    assert "1 página" in itens[0]["confianca_motivo"]
    assert itens[0]["custo_transcricao_usd"] == 0.0123
