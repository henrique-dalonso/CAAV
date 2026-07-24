from datetime import datetime
from pathlib import Path

from app.ferramentas.extratus.core.prompt_manager import carregar_instrucoes_relatorio


def gerar_relatorio_simulado(caminho_pdf, processo_detectado):
    """Devolve dados de exemplo no mesmo formato que a IA real vai devolver.

    Isso garante que o resto do pipeline (geração do .docx a partir do
    template) já está pronto pro formato certo antes da IA existir de fato.
    """
    carregar_instrucoes_relatorio()

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    return {
        "tipo_acao": "(exemplo — IA ainda não ativada)",
        "numero_processo": processo_detectado or "não localizado nos autos",
        "incidente": "",
        "valor_causa": "não localizado nos autos",
        "valor_divida": "não localizado nos autos",
        "autor": "não localizado nos autos",
        "reu": "não localizado nos autos",
        "bem": "não localizado nos autos",
        "contrato": "não localizado nos autos",
        "comarca": "não localizado nos autos",
        "cronologia": [
            {
                "data": agora,
                "ator": "Extratus",
                "descricao": (
                    f"Relatório simulado gerado a partir de {Path(caminho_pdf).name}. "
                    "A integração real com IA ainda não está ativada."
                ),
            },
        ],
        "parecer": (
            "Este é um relatório simulado. Quando a integração real com IA "
            "estiver ativada, este texto será substituído pela análise real "
            "do processo, seguindo as instruções carregadas do escritório."
        ),
        "data_publicacao": "",
        "prazo_fatal_ed": "",
        "prazo_fatal": "",
        "status_atual": "Simulado — aguardando integração real de IA.",
    }


def gerar_relatorio_claude(caminho_pdf, processo_detectado):
    carregar_instrucoes_relatorio()

    raise NotImplementedError(
        "Integração com Claude ainda não implementada. "
        "Use gerar_relatorio_simulado() por enquanto."
    )
