"""Rótulos amigáveis pros valores internos (status, tipo de erro) que o
banco guarda em snake_case sem acento — usados como filtro Jinja nas
telas de relatórios/histórico, pra não vazar texto técnico pro usuário.

Também moram aqui os badges "+N" que aparecem do lado do nome das abas
na navegação — usados como Jinja global (cada web/routes/*.py registra
as funções abaixo na sua própria instância de templates, ver comentário
em cada rota) pra aparecer SEMPRE, em toda tela da ferramenta, e não só
quando a aba não é a atual.

Henrique, 2026-08-13: o número deixou de ser uma contagem total (que só
cresce) e virou um indicador de "algo novo desde a última vez que você
abriu essa aba" — cada função aqui compara contra
`usuarios.obter_ultimo_visto` (por usuário + aba). "Gerar seu Relatório"
e "Fila do Motor" (as 2 "filas" do módulo — uma manual, outra do Motor)
só mostram o número na cor de revisão, e só quando surge uma Conferência
nova: tudo que aparece nelas foi o próprio usuário quem adicionou, não é
"novidade" precisar contar os pendentes. "Seus Relatórios"/"Relatórios
do Motor" mostram os dois números (sucesso e revisão) lado a lado.
"""

from datetime import datetime

from app.ferramentas.extratus.db.checagem_fila import contar_inconsistencias_ativas
from app.ferramentas.extratus.db.jobs import (
    contar_relatorios_motor_novos,
    contar_relatorios_novos_do_usuario,
)
from app.ferramentas.extratus.db.triagem_manual import contar_inconsistencias_ativas_do_usuario
from app.plataforma.db.usuarios import obter_ultimo_visto

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

FERRAMENTA_SLUG = "extratus"

# Chaves de aba usadas em UltimoVistoAba — mesmos nomes em toda parte
# (rotas que chamam `marcar_aba_vista` e funções de contagem abaixo).
# Valor da chave abaixo continua "inbox" de propósito (Rodada 13, rename
# de nomenclatura "Gerar seu Relatório") — é o que já está gravado no
# banco pra cada usuário; mudar o VALOR resetaria o "último visto" de
# todo mundo silenciosamente. Só o nome da constante Python mudou.
ABA_GERAR_RELATORIO = "inbox"
ABA_FILA = "fila"
ABA_RELATORIOS = "relatorios"
ABA_RELATORIOS_MOTOR = "relatorios-motor"

# `obter_ultimo_visto` devolve None pra quem nunca visitou a aba — trata
# como "desde sempre", pra tudo que já existir hoje contar como novo em
# vez de ficar escondido só por nunca ter sido visto.
_DESDE_SEMPRE = datetime.min


def rotulo_status(status):
    return STATUS_LABELS.get(status, status)


def rotulo_erro(tipo_erro):
    return ERRO_LABELS.get(tipo_erro, "Falha no processamento")


def contagem_nav_conferencias_manual(usuario):
    """Badge (só cor de revisão) da aba "Gerar seu Relatório" — quantas
    Conferências do próprio usuário estão pendentes AGORA (duplicidade,
    processo não encontrado etc.). Fica ligado até alguém aprovar ou
    descartar — só visitar a aba não zera (Henrique, 2026-08-13)."""
    return contar_inconsistencias_ativas_do_usuario(usuario.id)


def contagem_nav_conferencias_fila(usuario):
    """Badge (só cor de revisão) da aba "Fila do Motor" — quantas
    Conferências (compartilhadas, não é por usuário) estão pendentes
    AGORA. Mesmo comportamento "fica ligado até resolver" do item acima."""
    return contar_inconsistencias_ativas()


def contagem_nav_relatorios(usuario):
    """Badge duplo da aba "Seus Relatórios" — {"sucesso": N, "revisao": N}
    de relatórios MANUAIS do próprio usuário que terminaram desde a
    última visita."""
    desde = obter_ultimo_visto(usuario.id, FERRAMENTA_SLUG, ABA_RELATORIOS) or _DESDE_SEMPRE
    return contar_relatorios_novos_do_usuario(usuario.id, desde)


def contagem_nav_relatorios_motor(usuario):
    """Badge duplo da aba "Relatórios do Motor" — {"sucesso": N, "revisao": N}
    de relatórios do Motor (compartilhados) que terminaram desde a última
    visita DESSE usuário."""
    desde = obter_ultimo_visto(usuario.id, FERRAMENTA_SLUG, ABA_RELATORIOS_MOTOR) or _DESDE_SEMPRE
    return contar_relatorios_motor_novos(desde)
