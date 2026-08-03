"""Rótulos amigáveis pros valores internos (status, tipo de erro) que o
banco guarda em snake_case sem acento — usados como filtro Jinja nas
telas de relatórios/histórico, pra não vazar texto técnico pro usuário.
"""

STATUS_LABELS = {
    "sucesso": "Sucesso",
    "revisao": "Revisão",
    "erro": "Erro",
}

ERRO_LABELS = {
    "erro_pdf": "Falha ao ler o PDF",
    "erro_ia": "Falha ao gerar o relatório",
    "erro_docx": "Falha ao salvar o relatório",
    "erro_movimentacao": "Falha ao mover o arquivo",
}


def rotulo_status(status):
    return STATUS_LABELS.get(status, status)


def rotulo_erro(tipo_erro):
    return ERRO_LABELS.get(tipo_erro, "Falha no processamento")
