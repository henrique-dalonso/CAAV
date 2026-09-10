import re
from pathlib import Path

from docxtpl import DocxTemplate, RichText

from app.plataforma.paths import PROJECT_ROOT


# Achado real (2026-09-10, testando Relatórios e Condenação contra a API
# de verdade): o prompt pede a recomendação do parecer "em NEGRITO", mas
# o campo "parecer" é só um valor de texto puro no schema — a IA
# expressa esse negrito do único jeito que sabe (markdown, "**assim**"),
# e sem tratamento isso aparecia com os asteriscos literais no Word, sem
# negrito nenhum de verdade. Em vez de pedir pra IA parar de usar
# markdown (ela tende a usar de qualquer forma, é o jeito mais natural
# de sinalizar ênfase em texto puro), o código passa a INTERPRETAR essa
# marcação — o rótulo "{{r parecer }}" no molde (note o "r") ativa o
# RichText do docxtpl, que já suporta negrito de verdade dentro de um
# parágrafo.
_PADRAO_NEGRITO_MARKDOWN = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def texto_para_richtext(texto):
    """Converte `texto` (pode conter `**negrito**` em markdown) num
    `RichText` do docxtpl, com negrito de verdade. Sempre devolve um
    RichText, mesmo sem nenhum "**" no texto — funciona igual a um valor
    de texto puro nesse caso, então é seguro chamar pra qualquer campo,
    não só os que a IA de fato tentou negritar."""
    rt = RichText()

    if not texto:
        return rt

    posicao = 0
    for correspondencia in _PADRAO_NEGRITO_MARKDOWN.finditer(texto):
        if correspondencia.start() > posicao:
            rt.add(texto[posicao:correspondencia.start()])
        rt.add(correspondencia.group(1), bold=True)
        posicao = correspondencia.end()

    if posicao < len(texto):
        rt.add(texto[posicao:])

    return rt


# Template do tipo "bancario" (Extratus-Relatórios), o único que existe
# hoje — continua como constante de módulo, usada como padrão quando quem
# chama não passa `template_docx_path` (uso direto/teste). Produção
# (core/pipeline.py::finalizar_processamento) sempre passa
# `tipo.template_docx_path` explicitamente — é assim que um tipo novo
# (EMENDA, CONDENAÇÃO) no futuro preenche o SEU PRÓPRIO template, sem
# precisar de uma cópia deste módulo.
TEMPLATE_PATH = PROJECT_ROOT / "app" / "ferramentas" / "nucleo_relatorios" / "config" / "relatorio_template.docx"


def salvar_relatorio_docx(
    dados,
    caminho_saida,
    template_docx_path=None,
):
    """Preenche o template Word (nucleo_relatorios/config/relatorio_template.docx,
    ou `template_docx_path` quando informado — ver TipoRelatorio.template_docx_path)
    com os dados do relatório e salva o resultado.

    `dados` é um dicionário com os campos definidos no template (ver
    nucleo_relatorios/scripts/gerar_template_relatorio.py), vindo da IA
    real (ia_cliente.gerar_relatorio_claude).
    """
    caminho_saida = Path(caminho_saida)
    template_path = Path(template_docx_path) if template_docx_path else TEMPLATE_PATH

    caminho_saida.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if not template_path.exists():
        raise FileNotFoundError(
            f"Template de relatório não encontrado: {template_path}. "
            "Rode nucleo_relatorios/scripts/gerar_template_relatorio.py para recriá-lo."
        )

    # "parecer" é o único campo hoje que o prompt pede pra IA destacar em
    # negrito (a recomendação de ação imediata) — ver docstring de
    # texto_para_richtext. Cópia rasa: nunca modifica o `dados` de quem
    # chamou.
    dados = dict(dados)
    if "parecer" in dados:
        dados["parecer"] = texto_para_richtext(dados["parecer"])

    template = DocxTemplate(str(template_path))
    template.render(dados)
    template.save(str(caminho_saida))
