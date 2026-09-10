"""Cobre um buraco real encontrado em 2026-09-10: `salvar_relatorio_docx`
nunca teve nenhum teste, então nada travava uma regressão de rótulo
duplicado (achado real em produção — ver [[extratus-motor-unificado]]) ou
de campo faltando no molde. Usa um `dados` sintético, sem IA nenhuma."""

from docx import Document

from app.ferramentas.nucleo_relatorios.core.relatorio_manager import salvar_relatorio_docx


def _dados_sinteticos():
    return {
        "tipo_acao": "Busca e Apreensão",
        "numero_processo": "0012345-67.2026.8.16.0030",
        "incidente": "",
        "valor_causa": "R$ 10.000,00",
        "valor_divida": "R$ 9.500,00",
        "autor": "Banco Exemplo S.A.",
        "reu": "Fulano de Tal",
        "bem": "Veículo Fiat Uno 2015, placa ABC1234",
        "contrato": "123456 - 36 parcelas - 1,5% a.m.",
        "comarca": "1ª Vara Cível - Curitiba/PR",
        "cronologia": [
            {"data": "01/01/2026", "ator": "Autor", "descricao": "Distribuição da inicial."},
            {"data": "10/01/2026", "ator": "Juízo", "descricao": "Liminar deferida."},
        ],
        "parecer": "Recomenda-se acompanhar o cumprimento do mandado.",
        "data_publicacao": "15/01/2026",
        "prazo_fatal_ed": "",
        "prazo_fatal": "30/01/2026",
        "status_atual": "Aguardando cumprimento de mandado.",
    }


def _texto_completo(caminho_docx):
    documento = Document(str(caminho_docx))
    return "\n".join(paragrafo.text for paragrafo in documento.paragraphs)


def test_renderiza_sem_erro_e_inclui_o_conteudo_de_cada_campo(tmp_path):
    caminho_saida = tmp_path / "relatorio_teste.docx"
    dados = _dados_sinteticos()

    salvar_relatorio_docx(dados, caminho_saida)

    assert caminho_saida.exists()
    texto = _texto_completo(caminho_saida)
    assert dados["numero_processo"] in texto
    assert dados["parecer"] in texto
    assert dados["cronologia"][0]["descricao"] in texto


def test_cada_rotulo_do_molde_aparece_uma_unica_vez(tmp_path):
    """Trava a regressão real que motivou este arquivo: o prompt antigo
    fazia a IA embutir o rótulo dentro do próprio valor (ex: "Prazo Fatal:
    30/01/2026" dentro do campo `prazo_fatal`), duplicando o rótulo que o
    molde já escreve em negrito."""
    caminho_saida = tmp_path / "relatorio_teste.docx"
    dados = _dados_sinteticos()

    salvar_relatorio_docx(dados, caminho_saida)

    texto = _texto_completo(caminho_saida)
    rotulos = [
        "TIPO DA AÇÃO",
        "N° PROCESSO",
        "VALOR DA CAUSA",
        "VALOR DA DÍVIDA AJUIZADA",
        "AUTOR",
        "RÉU",
        "CONTRATO",
        "COMARCA/TRIBUNAL",
        "Data publicação/ciência",
        # "Prazo Fatal:" com dois-pontos, não "Prazo Fatal" sozinho — sem o
        # dois-pontos, isso também bate como substring dentro do rótulo
        # separado "Prazo Fatal ED:", inflando a contagem por acidente.
        "Prazo Fatal:",
        "Status atual",
    ]
    for rotulo in rotulos:
        assert texto.count(rotulo) == 1, f"Rótulo '{rotulo}' apareceu {texto.count(rotulo)}x, esperado 1x"


def test_rotulo_embutido_no_valor_e_pego_pelo_teste_acima(tmp_path):
    """Prova que o teste anterior de fato pega o bug real (a IA embutindo
    o rótulo dentro do próprio campo, como o prompt antigo induzia) — sem
    isso, o teste acima poderia estar "verde" por acidente."""
    caminho_saida = tmp_path / "relatorio_com_bug.docx"
    dados = _dados_sinteticos()
    dados["prazo_fatal"] = "Prazo Fatal: 30/01/2026"

    salvar_relatorio_docx(dados, caminho_saida)

    texto = _texto_completo(caminho_saida)
    assert texto.count("Prazo Fatal:") == 2
