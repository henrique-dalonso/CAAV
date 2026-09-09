from pathlib import Path

from docxtpl import DocxTemplate

from app.plataforma.paths import PROJECT_ROOT


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

    template = DocxTemplate(str(template_path))
    template.render(dados)
    template.save(str(caminho_saida))
