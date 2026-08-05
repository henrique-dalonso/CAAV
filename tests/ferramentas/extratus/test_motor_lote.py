from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.ferramentas.extratus.core import motor_lote


CONFIG_EXEMPLO = {
    "motor_ativo": True,
    "motor_pasta_entrada": "/pasta/motor",
    "pasta_saida": "/pasta/saida",
    "pasta_processados": "/pasta/processados",
    "pasta_revisao": "/pasta/revisao",
    "pasta_erros": "/pasta/erros",
}


def test_rodar_ciclo_motor_nao_faz_nada_se_desligado_e_sem_lote_pendente():
    with patch.object(motor_lote, "carregar_config", return_value={"motor_ativo": False}), \
         patch.object(motor_lote, "listar_lotes_em_andamento", return_value=[]), \
         patch.object(motor_lote, "_obter_cliente") as cliente_mock:
        motor_lote.rodar_ciclo_motor()

    cliente_mock.assert_not_called()


def test_rodar_ciclo_motor_coleta_lote_pendente_mesmo_desligado():
    """Um lote já enviado pra Anthropic continua rodando do lado de lá
    independente do interruptor local — desligar o motor não pode deixar
    esse lote preso pra sempre sem nunca virar relatório."""
    with patch.object(motor_lote, "carregar_config", return_value={"motor_ativo": False}), \
         patch.object(motor_lote, "listar_lotes_em_andamento", return_value=[SimpleNamespace(id=1)]), \
         patch.object(motor_lote, "_obter_cliente", return_value=MagicMock()) as cliente_mock, \
         patch.object(motor_lote, "_coletar_lotes_pendentes", return_value=False) as coletar_mock, \
         patch.object(motor_lote, "_preparar_novo_lote") as preparar_mock, \
         patch.object(motor_lote, "_submeter_lote") as submeter_mock:
        motor_lote.rodar_ciclo_motor()

    cliente_mock.assert_called_once()
    coletar_mock.assert_called_once()
    # motor desligado: fecha o lote pendente, mas não abre lote novo
    preparar_mock.assert_not_called()
    submeter_mock.assert_not_called()


def test_rodar_ciclo_motor_nao_submete_novo_lote_se_ja_tem_um_em_voo():
    with patch.object(motor_lote, "carregar_config", return_value=CONFIG_EXEMPLO), \
         patch.object(motor_lote, "listar_lotes_em_andamento", return_value=[SimpleNamespace(id=1)]), \
         patch.object(motor_lote, "_obter_cliente", return_value=MagicMock()), \
         patch.object(motor_lote, "_coletar_lotes_pendentes", return_value=True) as coletar_mock, \
         patch.object(motor_lote, "_preparar_novo_lote") as preparar_mock, \
         patch.object(motor_lote, "_submeter_lote") as submeter_mock:
        motor_lote.rodar_ciclo_motor()

    coletar_mock.assert_called_once()
    preparar_mock.assert_not_called()
    submeter_mock.assert_not_called()


def test_rodar_ciclo_motor_submete_lote_quando_ha_itens_elegiveis():
    itens_fake = [{"custom_id": "x", "arquivo_pdf": "a.pdf"}]

    with patch.object(motor_lote, "carregar_config", return_value=CONFIG_EXEMPLO), \
         patch.object(motor_lote, "listar_lotes_em_andamento", return_value=[]), \
         patch.object(motor_lote, "_obter_cliente", return_value=MagicMock()), \
         patch.object(motor_lote, "_preparar_novo_lote", return_value=itens_fake), \
         patch.object(motor_lote, "_submeter_lote") as submeter_mock:
        motor_lote.rodar_ciclo_motor()

    submeter_mock.assert_called_once()


def test_rodar_ciclo_motor_nao_submete_nada_se_nenhum_arquivo_elegivel():
    with patch.object(motor_lote, "carregar_config", return_value=CONFIG_EXEMPLO), \
         patch.object(motor_lote, "listar_lotes_em_andamento", return_value=[]), \
         patch.object(motor_lote, "_obter_cliente", return_value=MagicMock()), \
         patch.object(motor_lote, "_preparar_novo_lote", return_value=[]), \
         patch.object(motor_lote, "_submeter_lote") as submeter_mock:
        motor_lote.rodar_ciclo_motor()

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
    )
    item_erro = SimpleNamespace(
        id=11, custom_id="falhou", arquivo_pdf="falhou.pdf",
        processo_detectado="456", confianca_nivel="alta", confianca_motivo="teste",
    )

    cliente_fake = MagicMock()
    cliente_fake.messages.batches.retrieve.return_value = SimpleNamespace(processing_status="ended")
    cliente_fake.messages.batches.results.return_value = [
        _resultado_sucesso("ok"),
        _resultado_erro("falhou"),
    ]

    with patch.object(motor_lote, "listar_lotes_em_andamento", return_value=[lote_fake]), \
         patch.object(motor_lote, "listar_itens_do_lote", return_value=[item_sucesso, item_erro]), \
         patch.object(motor_lote, "extrair_dados_e_uso", return_value=({"campo": "valor"}, {})) as extrair_mock, \
         patch.object(motor_lote, "finalizar_processamento") as finalizar_mock, \
         patch.object(motor_lote, "tratar_erro") as tratar_erro_mock, \
         patch.object(motor_lote, "marcar_item_concluido") as marcar_item_mock, \
         patch.object(motor_lote, "marcar_lote_concluido") as marcar_lote_mock:
        ainda_em_andamento = motor_lote._coletar_lotes_pendentes(cliente_fake, CONFIG_EXEMPLO)

    assert ainda_em_andamento is False
    finalizar_mock.assert_called_once()
    tratar_erro_mock.assert_called_once()
    # o resultado de um lote sempre tem que aplicar o desconto do Batch API
    assert extrair_mock.call_args.kwargs.get("via_batch") is True
    assert marcar_item_mock.call_count == 2
    marcar_item_mock.assert_any_call(10, "sucesso")
    marcar_item_mock.assert_any_call(11, "erro")
    marcar_lote_mock.assert_called_once_with(1)


def test_coletar_lotes_pendentes_nao_mexe_em_lote_ainda_em_progresso():
    lote_fake = SimpleNamespace(id=1, batch_id="msgbatch_teste")

    cliente_fake = MagicMock()
    cliente_fake.messages.batches.retrieve.return_value = SimpleNamespace(processing_status="in_progress")

    with patch.object(motor_lote, "listar_lotes_em_andamento", return_value=[lote_fake]), \
         patch.object(motor_lote, "marcar_lote_concluido") as marcar_lote_mock:
        ainda_em_andamento = motor_lote._coletar_lotes_pendentes(cliente_fake, CONFIG_EXEMPLO)

    assert ainda_em_andamento is True
    marcar_lote_mock.assert_not_called()
    cliente_fake.messages.batches.results.assert_not_called()


def test_preparar_novo_lote_ignora_arquivo_ja_reivindicado():
    pdf_ja_reivindicado = Path("/pasta/motor/ja_reivindicado.pdf")

    with patch.object(motor_lote, "listar_pdfs", return_value=[pdf_ja_reivindicado]), \
         patch.object(motor_lote, "listar_arquivos_ja_reivindicados", return_value={"ja_reivindicado.pdf"}), \
         patch.object(motor_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(motor_lote, "obter_dados_deteccao") as deteccao_mock:
        itens = motor_lote._preparar_novo_lote(CONFIG_EXEMPLO)

    assert itens == []
    deteccao_mock.assert_not_called()


def test_preparar_novo_lote_trata_erro_de_montagem_sem_incluir_no_lote():
    pdf_grande_demais = Path("/pasta/motor/grande.pdf")

    with patch.object(motor_lote, "listar_pdfs", return_value=[pdf_grande_demais]), \
         patch.object(motor_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(motor_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(motor_lote, "obter_dados_deteccao", return_value=("123", {"nivel": "alta", "motivo": "x"})), \
         patch.object(motor_lote, "montar_diagnostico_com_triagem", return_value=({}, None, [])), \
         patch.object(motor_lote, "montar_parametros_mensagem", side_effect=RuntimeError("grande demais")), \
         patch.object(motor_lote, "tratar_erro") as tratar_erro_mock:
        itens = motor_lote._preparar_novo_lote(CONFIG_EXEMPLO)

    assert itens == []
    tratar_erro_mock.assert_called_once()
    assert tratar_erro_mock.call_args[0][2] == "erro_ia"


def test_preparar_novo_lote_inclui_arquivo_elegivel():
    pdf_ok = Path("/pasta/motor/ok.pdf")
    parametros_fake = {"model": "x"}

    with patch.object(motor_lote, "listar_pdfs", return_value=[pdf_ok]), \
         patch.object(motor_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(motor_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(motor_lote, "obter_dados_deteccao", return_value=("123", {"nivel": "alta", "motivo": "x"})), \
         patch.object(motor_lote, "montar_diagnostico_com_triagem", return_value=({}, None, [])), \
         patch.object(motor_lote, "montar_parametros_mensagem", return_value=parametros_fake):
        itens = motor_lote._preparar_novo_lote(CONFIG_EXEMPLO)

    assert len(itens) == 1
    assert itens[0]["arquivo_pdf"] == "ok.pdf"
    assert itens[0]["processo_detectado"] == "123"
    assert itens[0]["params"] == parametros_fake
    assert itens[0]["confianca_nivel"] == "alta"
    assert isinstance(itens[0]["custom_id"], str) and len(itens[0]["custom_id"]) > 0


def test_preparar_novo_lote_forca_revisao_quando_triagem_excluiu_paginas():
    pdf_com_anexo = Path("/pasta/motor/tem_anexo.pdf")
    parametros_fake = {"model": "x"}

    with patch.object(motor_lote, "listar_pdfs", return_value=[pdf_com_anexo]), \
         patch.object(motor_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(motor_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(motor_lote, "obter_dados_deteccao", return_value=("123", {"nivel": "alta", "motivo": "regex bateu"})), \
         patch.object(motor_lote, "montar_diagnostico_com_triagem", return_value=({}, None, [33, 34, 35])), \
         patch.object(motor_lote, "montar_parametros_mensagem", return_value=parametros_fake):
        itens = motor_lote._preparar_novo_lote(CONFIG_EXEMPLO)

    assert len(itens) == 1
    assert itens[0]["confianca_nivel"] == "revisao"
    assert "3 página" in itens[0]["confianca_motivo"]
