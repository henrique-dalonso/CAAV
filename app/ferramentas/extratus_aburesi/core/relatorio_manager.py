from pathlib import Path

from docxtpl import DocxTemplate

from app.plataforma.paths import PROJECT_ROOT


TEMPLATE_PATH = PROJECT_ROOT / "app" / "ferramentas" / "extratus_aburesi" / "config" / "relatorio_template.docx"


def salvar_relatorio_texto(
    conteudo,
    caminho_saida
):
    caminho_saida = Path(caminho_saida)

    caminho_saida.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        caminho_saida,
        "w",
        encoding="utf-8"
    ) as arquivo:
        arquivo.write(conteudo)


def salvar_relatorio_docx(
    dados,
    caminho_saida
):
    """Preenche o template Word (app/ferramentas/extratus_aburesi/config/relatorio_template.docx)
    com os dados do relatório e salva o resultado.

    `dados` é um dicionário com os campos definidos no template (ver
    app/ferramentas/extratus_aburesi/scripts/gerar_template_relatorio.py),
    vindo da IA real (ia_cliente.gerar_relatorio_claude).
    """
    caminho_saida = Path(caminho_saida)

    caminho_saida.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Template de relatório não encontrado: {TEMPLATE_PATH}. "
            "Rode app/ferramentas/extratus_aburesi/scripts/gerar_template_relatorio.py para recriá-lo."
        )

    template = DocxTemplate(str(TEMPLATE_PATH))
    template.render(dados)
    template.save(str(caminho_saida))
