from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.ferramentas.extratus_aburesi.core import motor_lote


CONFIG_EXEMPLO = {
    "motor_ativo": True,
    "motor_pasta_entrada": "/pasta/motor",
    "pasta_saida": "/pasta/saida",
    "pasta_processados": "/pasta/processados",
    "pasta_revisao": "/pasta/revisao",
    "pasta_erros": "/pasta/erros",
}


def _checagem_aprovada(processo="123", nivel="alta", motivo="x"):
    """Simula uma linha de ChecagemFila já aprovada — motor_lote.py não
    detecta processo/confiança sozinho mais, só reaproveita o que a
    checagem (checagem_lote.py, roda em segundo plano) já detectou."""
    return SimpleNamespace(processo_detectado=processo, confianca_nivel=nivel, confianca_motivo=motivo)


def test_preparar_novo_lote_forca_revisao_quando_triagem_excluiu_paginas():
    pdf_com_anexo = Path("/pasta/motor/tem_anexo.pdf")
    parametros_fake = {"model": "x"}

    with patch.object(motor_lote, "listar_pdfs", return_value=[pdf_com_anexo]), \
         patch.object(motor_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(motor_lote, "listar_aprovados_por_nome", return_value={"tem_anexo.pdf": _checagem_aprovada(motivo="regex bateu")}), \
         patch.object(motor_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(motor_lote, "montar_diagnostico_isolado", return_value=({}, None, [33, 34, 35])), \
         patch.object(motor_lote, "montar_parametros_mensagem", return_value=parametros_fake):
        itens = motor_lote._preparar_novo_lote(CONFIG_EXEMPLO)

    assert len(itens) == 1
    assert itens[0]["confianca_nivel"] == "revisao"
    assert "3 página" in itens[0]["confianca_motivo"]


def test_preparar_novo_lote_sem_triagem_mantem_confianca_original():
    pdf_normal = Path("/pasta/motor/normal.pdf")
    parametros_fake = {"model": "x"}

    with patch.object(motor_lote, "listar_pdfs", return_value=[pdf_normal]), \
         patch.object(motor_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(motor_lote, "listar_aprovados_por_nome", return_value={"normal.pdf": _checagem_aprovada(motivo="regex bateu")}), \
         patch.object(motor_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(motor_lote, "montar_diagnostico_isolado", return_value=({}, None, [])), \
         patch.object(motor_lote, "montar_parametros_mensagem", return_value=parametros_fake):
        itens = motor_lote._preparar_novo_lote(CONFIG_EXEMPLO)

    assert len(itens) == 1
    assert itens[0]["confianca_nivel"] == "alta"


def test_preparar_novo_lote_ignora_arquivo_ainda_nao_aprovado_na_checagem():
    """Núcleo do que a checagem (2026-08-06) precisa garantir: um arquivo
    que ainda não tem checagem, ou que a checagem recusou (duplicado,
    processo não encontrado), nunca chega a entrar num lote."""
    pdf_nao_aprovado = Path("/pasta/motor/nao_aprovado.pdf")

    with patch.object(motor_lote, "listar_pdfs", return_value=[pdf_nao_aprovado]), \
         patch.object(motor_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(motor_lote, "listar_aprovados_por_nome", return_value={}), \
         patch.object(motor_lote, "carregar_instrucoes_relatorio", return_value="instrucoes"), \
         patch.object(motor_lote, "montar_diagnostico_isolado") as diagnostico_mock:
        itens = motor_lote._preparar_novo_lote(CONFIG_EXEMPLO)

    assert itens == []
    diagnostico_mock.assert_not_called()
