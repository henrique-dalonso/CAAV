"""Fecha o mesmo buraco encontrado em Relatórios (2026-09-10): renderizar
`emenda.docx` nunca teve teste nenhum, então nada travava uma regressão de
rótulo/esqueleto de e-mail duplicado (mesma classe de bug real, a Parte 2
de `config/prompts/emenda.txt` também mandava a IA montar o e-mail sozinha,
sem saber que "Assunto:"/saudação/"FATAL:"/"No aguardo." já vêm do
template). Usa `dados` sintético, sem IA nenhuma."""

from docx import Document

from app.ferramentas.nucleo_relatorios.core.relatorio_manager import salvar_relatorio_docx
from app.ferramentas.nucleo_relatorios.tipos import REGISTRO_TIPOS


def _dados_sinteticos():
    return {
        "npjur": "1234567",
        "cnj": "0012345-67.2026.8.16.0030",
        "cliente": "Cliente Exemplo",
        "carteira": "MAPFRE",
        "autor": "Banco Exemplo S.A.",
        "reu": "Fulano de Tal",
        "comarca_vara": "3ª Vara Cível - Curitiba/PR",
        "decisao_resumo": "Juízo determinou emenda à inicial para juntada do contrato original, sob pena de indeferimento.",
        "checklist_verificacao": ["Conferir se o contrato já consta dos autos"],
        "documentos_ja_nos_autos": ["Procuração"],
        "processos_relacionados_flag": False,
        "processos_relacionados_detalhe": "",
        "uf": "PR",
        "identificador_carteira": "MAPFRE",
        "email_carteira_descricao": "O juízo determinou a juntada do contrato original de financiamento.",
        "providencia_solicitada": "contrato original de financiamento",
        "prazo_aviso_calculo": "",
        "prazo_data_inicio_formatada": "02/06/2026",
        "prazo_data_final_calculada": "10/06/2026",
        "prazo_ja_vencido": False,
        "prazo_diverge_do_informado": False,
        "prazo_data_informada_formatada": "",
    }


def _texto_completo(caminho_docx):
    documento = Document(str(caminho_docx))
    return "\n".join(paragrafo.text for paragrafo in documento.paragraphs)


def test_renderiza_sem_erro_e_inclui_o_conteudo_de_cada_campo(tmp_path):
    caminho_saida = tmp_path / "emenda_teste.docx"
    dados = _dados_sinteticos()
    template = REGISTRO_TIPOS["emenda"].template_docx_path

    salvar_relatorio_docx(dados, caminho_saida, template_docx_path=template)

    assert caminho_saida.exists()
    texto = _texto_completo(caminho_saida)
    assert dados["cnj"] in texto
    assert dados["decisao_resumo"] in texto
    assert dados["email_carteira_descricao"] in texto


def test_esqueleto_do_email_aparece_uma_unica_vez(tmp_path):
    """Trava a regressão real que motivou este arquivo: se o prompt
    induzisse a IA a escrever "Assunto:", a saudação ou "FATAL:"/"No
    aguardo." dentro do próprio conteúdo, isso duplicaria o que o molde
    já gera sozinho."""
    caminho_saida = tmp_path / "emenda_teste.docx"
    dados = _dados_sinteticos()
    template = REGISTRO_TIPOS["emenda"].template_docx_path

    salvar_relatorio_docx(dados, caminho_saida, template_docx_path=template)

    texto = _texto_completo(caminho_saida)
    esqueleto = ["Assunto:", "bom dia.", "FATAL:", "No aguardo."]
    for pedaco in esqueleto:
        assert texto.count(pedaco) == 1, f"'{pedaco}' apareceu {texto.count(pedaco)}x, esperado 1x"


def test_esqueleto_duplicado_no_valor_e_pego_pelo_teste_acima(tmp_path):
    """Prova que o teste anterior de fato pega o bug real — injeta o
    esqueleto do e-mail dentro de `email_carteira_descricao`, simulando o
    que o prompt antigo induzia."""
    caminho_saida = tmp_path / "emenda_com_bug.docx"
    dados = _dados_sinteticos()
    dados["email_carteira_descricao"] = (
        "@MAPFRE, bom dia. O juízo determinou a juntada do contrato original."
    )
    template = REGISTRO_TIPOS["emenda"].template_docx_path

    salvar_relatorio_docx(dados, caminho_saida, template_docx_path=template)

    texto = _texto_completo(caminho_saida)
    assert texto.count("bom dia.") == 2
