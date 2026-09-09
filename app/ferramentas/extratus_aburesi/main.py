from app.ferramentas.extratus_aburesi.core.config_manager import carregar_config
from app.ferramentas.nucleo_relatorios.core.app_logger import registrar_log
from app.ferramentas.nucleo_relatorios.core.fila_manager import montar_fila
from app.ferramentas.nucleo_relatorios.core.pipeline import processar_pdf
from app.ferramentas.nucleo_relatorios.tipos import REGISTRO_TIPOS


FERRAMENTA_SLUG = "extratus-aburesi"
TIPO_RELATORIO = REGISTRO_TIPOS["bancario"]


def main():
    config = carregar_config()

    registrar_log("Extratus iniciado com sucesso.")

    pasta_entrada = config.get(
        "pasta_entrada",
        "entrada_pdfs"
    )

    pasta_saida = config.get(
        "pasta_saida",
        "relatorios_prontos"
    )

    pasta_processados = config.get(
        "pasta_processados",
        "processados"
    )

    pasta_erros = config.get(
        "pasta_erros",
        "erros"
    )

    pasta_revisao = config.get(
        "pasta_revisao",
        "revisao"
    )

    limite = config.get(
        "limite_padrao",
        0
    )

    resultado_fila = montar_fila(
        pasta_entrada=pasta_entrada,
        limite=limite
    )

    registrar_log(
        f"PDFs encontrados: {resultado_fila['total_pdfs']}"
    )

    registrar_log(
        f"PDFs na fila: {resultado_fila['total_fila']}"
    )

    for pdf in resultado_fila["pdfs"]:
        processar_pdf(
            pdf, pasta_saida, pasta_processados, pasta_erros, pasta_revisao,
            tipo=TIPO_RELATORIO, ferramenta_slug=FERRAMENTA_SLUG,
        )

    registrar_log("Extratus finalizado.")


if __name__ == "__main__":
    main()
