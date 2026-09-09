"""
Gera o template Word (config/templates/emenda.docx) usado pelo tipo
"emenda" do motor compartilhado (nucleo_relatorios/tipos.py).

Segue a especificacao de formatacao do PARTE 2 do prompt de emenda
(config/prompts/emenda.txt): A4, margens 2,5cm, Arial 11, rotulos em
negrito na identificacao do processo, titulo de secao em negrito com linha
divisoria fina abaixo, checklist como lista nativa do Word (nao marcador
digitado como texto) e o bloco de e-mail padrao destacado por sombreamento
leve de paragrafo.

Mesmo principio do gerar_template_relatorio.py (o template "bancario"):
este script so precisa ser rodado de novo se o template for perdido ou
corrompido. Ajuste visual pontual deve ser feito abrindo o .docx gerado
direto no Word.

Nao cobre (fora do escopo desta entrega, ver docstring de
calculadores/feriados_forenses.py): feriado/ponto facultativo de COMARCA
(so feriado forense NACIONAL + recesso). O template inclui uma nota fixa
avisando essa lacuna, pra nunca virar uma omissao silenciosa pra quem le o
.docx final.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.plataforma.paths import PROJECT_ROOT


CAMINHO_SAIDA = str(
    PROJECT_ROOT / "app" / "ferramentas" / "nucleo_relatorios" / "config" / "templates" / "emenda.docx"
)

CINZA = RGBColor(0x80, 0x80, 0x80)

# Cor de fundo do sombreamento do bloco de e-mail — cinza bem claro, só o
# suficiente pra separar visualmente do resto do documento sem prejudicar
# a leitura nem o contraste na impressão em preto e branco.
COR_SOMBREAMENTO_EMAIL = "F2F2F2"


def adicionar_borda_inferior(paragrafo, cor="808080", tamanho=6):
    """Ver função equivalente em gerar_template_relatorio.py — mesmo
    raciocínio, duplicada aqui (não importada de lá) porque os dois
    scripts são independentes entre si de propósito: cada tipo (bancario,
    emenda, e o que vier depois) gera seu próprio template isolado, sem
    acoplar um script de geração ao outro."""
    p_pr = paragrafo._p.get_or_add_pPr()
    p_borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(tamanho))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), cor)
    p_borders.append(bottom)
    p_pr.append(p_borders)


def sombrear_paragrafo(paragrafo, cor_fundo=COR_SOMBREAMENTO_EMAIL):
    """python-docx não expõe sombreamento de parágrafo (`w:shd`) em nível
    alto — só de célula de tabela. Construção manual do elemento OOXML,
    mesmo espírito de `adicionar_borda_inferior` acima (que já faz o
    mesmo tipo de manipulação pra bordas): pega/cria o `w:pPr` do
    parágrafo e anexa um `w:shd` com preenchimento sólido
    (`w:val="clear"`, sem padrão de trama) na cor pedida."""
    p_pr = paragrafo._p.get_or_add_pPr()
    sombra = OxmlElement("w:shd")
    sombra.set(qn("w:val"), "clear")
    sombra.set(qn("w:color"), "auto")
    sombra.set(qn("w:fill"), cor_fundo)
    p_pr.append(sombra)


def configurar_pagina(documento):
    secao = documento.sections[0]
    secao.page_height = Cm(29.7)
    secao.page_width = Cm(21.0)
    secao.top_margin = Cm(2.5)
    secao.bottom_margin = Cm(2.5)
    secao.left_margin = Cm(2.5)
    secao.right_margin = Cm(2.5)


def configurar_fonte_padrao(documento):
    estilo = documento.styles["Normal"]
    estilo.font.name = "Arial"
    estilo.font.size = Pt(11)
    estilo.paragraph_format.space_after = Pt(0)
    estilo.paragraph_format.line_spacing = 1.0


def campo_rotulo(documento, rotulo, variavel, espaco_depois=4):
    """Rótulo em negrito, valor em texto normal, mesma linha — regra de
    PARTE 2 pra "Identificação do processo"."""
    paragrafo = documento.add_paragraph()
    paragrafo.paragraph_format.space_after = Pt(espaco_depois)
    paragrafo.paragraph_format.line_spacing = 1.0

    run_rotulo = paragrafo.add_run(f"{rotulo}: ")
    run_rotulo.bold = True

    paragrafo.add_run("{{ " + variavel + " }}")

    return paragrafo


def titulo_secao(documento, texto):
    """Título de seção em negrito com linha divisória fina abaixo — regra
    de PARTE 2 pra DECISÃO DO JUÍZO / O QUE DEVE SER VERIFICADO / E-MAIL
    PADRÃO PARA A CARTEIRA."""
    paragrafo = documento.add_paragraph()
    paragrafo.paragraph_format.space_before = Pt(12)
    paragrafo.paragraph_format.space_after = Pt(6)

    run = paragrafo.add_run(texto)
    run.bold = True
    run.font.size = Pt(11)

    adicionar_borda_inferior(paragrafo)

    return paragrafo


def paragrafo_email(documento, texto_com_jinja, negrito=False):
    """Parágrafo do bloco de e-mail — sempre sombreado, pra ficar
    visualmente destacado e "pronto pra copiar e colar" (regra do prompt).
    `texto_com_jinja` já vem com a sintaxe `{{ variavel }}` do docxtpl
    embutida — o texto fixo do esqueleto (saudação, "bom dia",
    "No aguardo.") é escrito aqui em código, nunca gerado pela IA (ver
    docstring de FERRAMENTA_EMENDA em core/ia_cliente.py)."""
    paragrafo = documento.add_paragraph()
    paragrafo.paragraph_format.space_after = Pt(4)
    paragrafo.paragraph_format.line_spacing = 1.0

    run = paragrafo.add_run(texto_com_jinja)
    run.bold = negrito

    sombrear_paragrafo(paragrafo)

    return paragrafo


def item_checklist(documento, texto_com_jinja):
    """Item de lista nativa do Word ("List Bullet") — nunca um marcador
    unicode digitado dentro do texto (regra explícita de PARTE 2)."""
    paragrafo = documento.add_paragraph(texto_com_jinja, style="List Bullet")
    paragrafo.paragraph_format.space_after = Pt(2)
    return paragrafo


def construir_template():
    documento = Document()

    configurar_pagina(documento)
    configurar_fonte_padrao(documento)

    # Título
    titulo = documento.add_paragraph()
    run_titulo = titulo.add_run("ANÁLISE DE EMENDA/DESPACHO")
    run_titulo.bold = True
    run_titulo.font.size = Pt(14)
    titulo.paragraph_format.space_after = Pt(12)

    # --- Identificação do processo ---
    subtitulo_id = documento.add_paragraph()
    run_subtitulo = subtitulo_id.add_run("IDENTIFICAÇÃO DO PROCESSO")
    run_subtitulo.bold = True
    subtitulo_id.paragraph_format.space_after = Pt(6)

    campo_rotulo(documento, "NPJur", "npjur")
    campo_rotulo(documento, "CNJ", "cnj")
    campo_rotulo(documento, "CLIENTE", "cliente")
    campo_rotulo(documento, "CARTEIRA", "carteira")
    campo_rotulo(documento, "AUTOR", "autor")
    campo_rotulo(documento, "RÉU", "reu")
    campo_rotulo(documento, "COMARCA/VARA", "comarca_vara")

    # --- Decisão do juízo ---
    titulo_secao(documento, "DECISÃO DO JUÍZO")

    paragrafo_resumo = documento.add_paragraph("{{ decisao_resumo }}")
    paragrafo_resumo.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    paragrafo_resumo.paragraph_format.space_after = Pt(8)

    # Prazo fatal — resultado do cálculo determinístico (nunca da IA, ver
    # calculadores/prazo_fatal.py), já formatado em código antes de
    # chegar aqui (core/pos_processamento_emenda.py).
    campo_rotulo(documento, "Data de início da contagem", "prazo_data_inicio_formatada")
    campo_rotulo(documento, "Data final apurada", "prazo_data_final_calculada")

    documento.add_paragraph("{% if prazo_ja_vencido %}")
    paragrafo_vencido = documento.add_paragraph()
    run_vencido = paragrafo_vencido.add_run("PRAZO JÁ VENCIDO na data desta análise.")
    run_vencido.bold = True
    documento.add_paragraph("{% endif %}")

    documento.add_paragraph("{% if prazo_diverge_do_informado %}")
    paragrafo_diverge = documento.add_paragraph()
    run_diverge = paragrafo_diverge.add_run(
        "Atenção: a data \"FATAL\" informada em e-mail interno/decisão "
        "({{ prazo_data_informada_formatada }}) diverge da data calculada "
        "acima pela contagem legal. Confirmar manualmente qual prevalece."
    )
    run_diverge.italic = True
    documento.add_paragraph("{% endif %}")

    documento.add_paragraph("{% if prazo_aviso_calculo %}")
    paragrafo_aviso = documento.add_paragraph()
    run_aviso = paragrafo_aviso.add_run("{{ prazo_aviso_calculo }}")
    run_aviso.italic = True
    documento.add_paragraph("{% endif %}")

    nota_feriados = documento.add_paragraph()
    run_nota = nota_feriados.add_run(
        "Nota: o cálculo acima considera apenas feriados forenses NACIONAIS "
        "e o recesso forense (20/12 a 20/01). Feriado ou ponto facultativo "
        "de comarca não está incluído — confirmar manualmente se a comarca "
        "do processo tiver algum."
    )
    run_nota.italic = True
    run_nota.font.size = Pt(9)
    run_nota.font.color.rgb = CINZA
    nota_feriados.paragraph_format.space_after = Pt(10)

    # --- O que deve ser verificado pelo colaborador ---
    titulo_secao(documento, "O QUE DEVE SER VERIFICADO")

    documento.add_paragraph("{% for item in checklist_verificacao %}")
    item_checklist(documento, "{{ item }}")
    documento.add_paragraph("{% endfor %}")

    subtitulo_docs = documento.add_paragraph()
    run_subtitulo_docs = subtitulo_docs.add_run("Documentos já localizados nos autos:")
    run_subtitulo_docs.bold = True
    run_subtitulo_docs.font.size = Pt(10)
    subtitulo_docs.paragraph_format.space_before = Pt(8)

    documento.add_paragraph("{% for documento_encontrado in documentos_ja_nos_autos %}")
    item_checklist(documento, "{{ documento_encontrado }}")
    documento.add_paragraph("{% endfor %}")

    documento.add_paragraph("{% if processos_relacionados_flag %}")
    paragrafo_relacionados = documento.add_paragraph()
    run_relacionados = paragrafo_relacionados.add_run(
        "Processo relacionado identificado (litispendência/ação conexa/recurso "
        "pendente): {{ processos_relacionados_detalhe }} — pesquisar nos autos "
        "recursais ou no sistema do tribunal antes de cobrar posicionamento "
        "da carteira."
    )
    run_relacionados.italic = True
    documento.add_paragraph("{% endif %}")

    # --- E-mail padrão para a carteira ---
    titulo_secao(documento, "E-MAIL PADRÃO PARA A CARTEIRA")

    # Esqueleto fixo (assunto, saudação, "bom dia", "FATAL:", "No
    # aguardo.") escrito em código — só o conteúdo variável vem da IA. Ver
    # docstring de `paragrafo_email` e de FERRAMENTA_EMENDA
    # (core/ia_cliente.py) pro porquê.
    paragrafo_email(
        documento,
        "Assunto: {{ uf }} EMENDA NPJur: {{ npjur }} Cliente: {{ cliente }} "
        "Autor: {{ autor }} Réu: {{ reu }}",
        negrito=True,
    )
    paragrafo_email(documento, "@{{ identificador_carteira }}, bom dia.")
    paragrafo_email(documento, "{{ email_carteira_descricao }}")
    paragrafo_email(documento, "Gentileza disponibilizar {{ providencia_solicitada }}.")
    paragrafo_email(documento, "FATAL: {{ prazo_data_final_calculada }}", negrito=True)
    paragrafo_email(documento, "No aguardo.")

    documento.save(CAMINHO_SAIDA)
    print(f"Template salvo em: {CAMINHO_SAIDA}")


if __name__ == "__main__":
    construir_template()
