"""Rótulos amigáveis pros valores internos (status, tipo de erro) que o
banco guarda em snake_case sem acento — usados como filtro Jinja nas
telas de relatórios/histórico, pra não vazar texto técnico pro usuário.

Também mora aqui a contagem que aparece do lado do nome das abas
"Gerar relatórios"/"Relatórios" na navegação — usada como Jinja global
(cada web/routes/*.py registra as duas funções abaixo na sua própria
instância de templates, ver comentário em cada rota) pra aparecer
SEMPRE, em toda tela da ferramenta, e não só quando a aba não é a atual.
"""

from app.ferramentas.extratus_aburesi.db.jobs import contar_jobs_manuais_do_usuario
from app.ferramentas.extratus_aburesi.db.triagem_manual import listar_estado_do_usuario

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


def contagem_nav_pendentes(usuario):
    """Ver docstring equivalente em app/ferramentas/extratus/web/
    rotulos.py (Extratus - Relatórios) — mesma lógica."""
    estado = listar_estado_do_usuario(usuario.id)

    return len(estado["pendentes"]) + len(estado["processando"])


def contagem_nav_relatorios(usuario):
    """Ver docstring equivalente em app/ferramentas/extratus/web/
    rotulos.py (Extratus - Relatórios) — mesma lógica."""
    return contar_jobs_manuais_do_usuario(usuario.id)
