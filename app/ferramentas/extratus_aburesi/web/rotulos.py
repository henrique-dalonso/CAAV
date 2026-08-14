"""Rótulos amigáveis pros valores internos (status, tipo de erro) que o
banco guarda em snake_case sem acento — usados como filtro Jinja nas
telas de relatórios/histórico, pra não vazar texto técnico pro usuário.

Também moram aqui os badges "+N" que aparecem do lado do nome das abas
na navegação — ver docstring equivalente em app/ferramentas/extratus/
web/rotulos.py (Extratus - Relatórios) pro raciocínio completo, mesma
lógica aqui.
"""

from datetime import datetime

from app.ferramentas.extratus_aburesi.db.checagem_fila import contar_inconsistencias_novas
from app.ferramentas.extratus_aburesi.db.jobs import (
    contar_relatorios_motor_novos,
    contar_relatorios_novos_do_usuario,
)
from app.ferramentas.extratus_aburesi.db.triagem_manual import contar_inconsistencias_novas_do_usuario
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

FERRAMENTA_SLUG = "extratus-aburesi"

ABA_GERAR_RELATORIO = "inbox"
ABA_FILA = "fila"
ABA_RELATORIOS = "relatorios"
ABA_RELATORIOS_MOTOR = "relatorios-motor"

_DESDE_SEMPRE = datetime.min


def rotulo_status(status):
    return STATUS_LABELS.get(status, status)


def rotulo_erro(tipo_erro):
    return ERRO_LABELS.get(tipo_erro, "Falha no processamento")


def contagem_nav_conferencias_manual(usuario):
    """Ver docstring equivalente em app/ferramentas/extratus/web/
    rotulos.py (Extratus - Relatórios) — mesma lógica."""
    desde = obter_ultimo_visto(usuario.id, FERRAMENTA_SLUG, ABA_GERAR_RELATORIO) or _DESDE_SEMPRE
    return contar_inconsistencias_novas_do_usuario(usuario.id, desde)


def contagem_nav_conferencias_fila(usuario):
    """Ver docstring equivalente em app/ferramentas/extratus/web/
    rotulos.py (Extratus - Relatórios) — mesma lógica."""
    desde = obter_ultimo_visto(usuario.id, FERRAMENTA_SLUG, ABA_FILA) or _DESDE_SEMPRE
    return contar_inconsistencias_novas(desde)


def contagem_nav_relatorios(usuario):
    """Ver docstring equivalente em app/ferramentas/extratus/web/
    rotulos.py (Extratus - Relatórios) — mesma lógica."""
    desde = obter_ultimo_visto(usuario.id, FERRAMENTA_SLUG, ABA_RELATORIOS) or _DESDE_SEMPRE
    return contar_relatorios_novos_do_usuario(usuario.id, desde)


def contagem_nav_relatorios_motor(usuario):
    """Ver docstring equivalente em app/ferramentas/extratus/web/
    rotulos.py (Extratus - Relatórios) — mesma lógica."""
    desde = obter_ultimo_visto(usuario.id, FERRAMENTA_SLUG, ABA_RELATORIOS_MOTOR) or _DESDE_SEMPRE
    return contar_relatorios_motor_novos(desde)
