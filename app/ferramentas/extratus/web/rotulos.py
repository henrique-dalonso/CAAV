"""Rótulos amigáveis pros valores internos (status, tipo de erro) que o
banco guarda em snake_case sem acento — usados como filtro Jinja nas
telas de relatórios/histórico, pra não vazar texto técnico pro usuário.

Também mora aqui a contagem que aparece do lado do nome das abas
"Gerar relatórios"/"Relatórios" na navegação — usada como Jinja global
(cada web/routes/*.py registra as duas funções abaixo na sua própria
instância de templates, ver comentário em cada rota) pra aparecer
SEMPRE, em toda tela da ferramenta, e não só quando a aba não é a atual.
"""

from app.ferramentas.extratus.db.jobs import contar_jobs_manuais_do_usuario
from app.ferramentas.extratus.db.triagem_manual import listar_estado_do_usuario

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
    """Quantos uploads do usuário logado ainda estão ativos (em triagem
    ou em geração) em "Gerar seu Relatório" — mesma fonte que a própria
    tela usa (inbox.py), pra o número da aba nunca destoar do que a
    pessoa vê quando clica nela."""
    estado = listar_estado_do_usuario(usuario.id)

    return len(estado["pendentes"]) + len(estado["processando"])


def contagem_nav_relatorios(usuario):
    """Quantos relatórios MANUAIS o próprio usuário logado solicitou —
    Henrique, 2026-08-12: precisa bater com o que a tela "Seus
    Relatórios" mostra por padrão (checkbox "Solicitados por mim" já vem
    marcado), não o total do escritório inteiro. Conta Job (usuario_id
    preenchido), não arquivo .docx em disco: desde que "Relatórios
    Finalizados" (2026-08-08) separou os relatórios do Motor pra sua
    própria tela, a mesma pasta de saída ainda recebe .docx dos dois
    caminhos — contar arquivo bruto destoaria do que a lista realmente
    mostra."""
    return contar_jobs_manuais_do_usuario(usuario.id)
