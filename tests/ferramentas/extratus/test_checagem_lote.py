from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.ferramentas.extratus.core import checagem_lote
from app.ferramentas.extratus.db.checagem_fila import (
    APROVADO,
    DUPLICADO_EM_ANDAMENTO,
    DUPLICADO_RELATORIO,
    NAO_ENCONTRADO,
)


CONFIG_EXEMPLO = {
    "motor_pasta_entrada": "/pasta/motor",
    "pasta_erros": "/pasta/erros",
}


def _resultado(processo=None, nivel="alta", motivo="ok"):
    dominante = {"processo": processo} if processo else None
    return {"dominante": dominante, "confianca": {"nivel": nivel, "motivo": motivo}}


def test_rodar_ciclo_checagem_sincroniza_e_checa_cada_pendente():
    registro = SimpleNamespace(id=1, nome_arquivo="a.pdf")

    with patch.object(checagem_lote, "carregar_config", return_value=CONFIG_EXEMPLO), \
         patch.object(checagem_lote, "listar_pdfs", return_value=[Path("/pasta/motor/a.pdf")]), \
         patch.object(checagem_lote, "listar_arquivos_ja_reivindicados", return_value=set()), \
         patch.object(checagem_lote, "sincronizar_registros", return_value=[registro]) as sincronizar_mock, \
         patch.object(checagem_lote, "_checar_um_arquivo") as checar_mock:
        checagem_lote.rodar_ciclo_checagem()

    sincronizar_mock.assert_called_once_with({"a.pdf"})
    checar_mock.assert_called_once_with(registro, Path("/pasta/motor"), "/pasta/erros")


def test_rodar_ciclo_checagem_exclui_ja_reivindicado_dos_candidatos():
    with patch.object(checagem_lote, "carregar_config", return_value=CONFIG_EXEMPLO), \
         patch.object(checagem_lote, "listar_pdfs", return_value=[
             Path("/pasta/motor/a.pdf"), Path("/pasta/motor/ja_reivindicado.pdf"),
         ]), \
         patch.object(checagem_lote, "listar_arquivos_ja_reivindicados", return_value={"ja_reivindicado.pdf"}), \
         patch.object(checagem_lote, "sincronizar_registros", return_value=[]) as sincronizar_mock:
        checagem_lote.rodar_ciclo_checagem()

    sincronizar_mock.assert_called_once_with({"a.pdf"})


def test_checar_um_arquivo_aprova_quando_tudo_ok():
    registro = SimpleNamespace(id=1, nome_arquivo="a.pdf")

    with patch.object(checagem_lote, "analisar_pdf_isolado", return_value=_resultado(processo="123")), \
         patch.object(checagem_lote, "existe_relatorio_gerado_para_processo", return_value=False), \
         patch.object(checagem_lote, "existe_conflito_de_processo", return_value=False), \
         patch.object(checagem_lote, "atualizar_apos_checagem") as atualizar_mock:
        checagem_lote._checar_um_arquivo(registro, Path("/pasta/motor"), "/pasta/erros")

    atualizar_mock.assert_called_once_with(1, APROVADO, "123", "alta", "ok")


def test_checar_um_arquivo_marca_processo_nao_encontrado():
    registro = SimpleNamespace(id=1, nome_arquivo="a.pdf")

    with patch.object(checagem_lote, "analisar_pdf_isolado", return_value=_resultado(processo=None)), \
         patch.object(checagem_lote, "atualizar_apos_checagem") as atualizar_mock:
        checagem_lote._checar_um_arquivo(registro, Path("/pasta/motor"), "/pasta/erros")

    assert atualizar_mock.call_args[0][1] == NAO_ENCONTRADO
    assert atualizar_mock.call_args[0][2] is None


def test_checar_um_arquivo_marca_duplicado_relatorio():
    registro = SimpleNamespace(id=1, nome_arquivo="a.pdf")

    with patch.object(checagem_lote, "analisar_pdf_isolado", return_value=_resultado(processo="123")), \
         patch.object(checagem_lote, "existe_relatorio_gerado_para_processo", return_value=True), \
         patch.object(checagem_lote, "atualizar_apos_checagem") as atualizar_mock:
        checagem_lote._checar_um_arquivo(registro, Path("/pasta/motor"), "/pasta/erros")

    assert atualizar_mock.call_args[0][1] == DUPLICADO_RELATORIO
    assert atualizar_mock.call_args[0][2] == "123"


def test_checar_um_arquivo_marca_duplicado_em_andamento():
    registro = SimpleNamespace(id=1, nome_arquivo="a.pdf")

    with patch.object(checagem_lote, "analisar_pdf_isolado", return_value=_resultado(processo="123")), \
         patch.object(checagem_lote, "existe_relatorio_gerado_para_processo", return_value=False), \
         patch.object(checagem_lote, "existe_conflito_de_processo", return_value=True), \
         patch.object(checagem_lote, "atualizar_apos_checagem") as atualizar_mock:
        checagem_lote._checar_um_arquivo(registro, Path("/pasta/motor"), "/pasta/erros")

    assert atualizar_mock.call_args[0][1] == DUPLICADO_EM_ANDAMENTO


def test_checar_um_arquivo_pdf_ilegivel_trata_como_erro_de_verdade():
    """Diferente do "processo não encontrado" (que fica pendurado
    esperando Conferências), um PDF que nem abre precisa continuar caindo
    em pasta_erros/Job "erro" como sempre foi — motor_lote.py não detecta
    mais nada sozinho, então se a checagem não tratasse isso aqui, o
    arquivo ficaria preso pra sempre sem nunca aparecer como erro."""
    registro = SimpleNamespace(id=1, nome_arquivo="a.pdf")

    with patch.object(checagem_lote, "analisar_pdf_isolado", side_effect=RuntimeError("PDF corrompido")), \
         patch.object(checagem_lote, "tratar_erro") as tratar_erro_mock, \
         patch.object(checagem_lote, "atualizar_apos_checagem") as atualizar_mock:
        checagem_lote._checar_um_arquivo(registro, Path("/pasta/motor"), "/pasta/erros")

    tratar_erro_mock.assert_called_once()
    assert tratar_erro_mock.call_args[0][2] == "erro_pdf"
    atualizar_mock.assert_not_called()


def test_checar_um_arquivo_sumido_durante_o_ciclo_e_ignorado_sem_virar_erro():
    """Race real (achada 2026-08-06/07): o arquivo existia quando o ciclo
    tirou a foto da pasta, mas alguém removeu (ex: "Remover todos") antes
    de chegar a vez dele aqui. Isso não é uma falha de processamento —
    não deve virar Job "erro" nem notificação, só ser ignorado."""
    registro = SimpleNamespace(id=1, nome_arquivo="a.pdf")

    with patch.object(checagem_lote, "analisar_pdf_isolado", side_effect=FileNotFoundError()), \
         patch.object(checagem_lote, "tratar_erro") as tratar_erro_mock, \
         patch.object(checagem_lote, "atualizar_apos_checagem") as atualizar_mock:
        checagem_lote._checar_um_arquivo(registro, Path("/pasta/motor"), "/pasta/erros")

    tratar_erro_mock.assert_not_called()
    atualizar_mock.assert_not_called()
