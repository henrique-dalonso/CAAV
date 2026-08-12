from app.ferramentas.extratus_aburesi.db.checagem_fila import (
    MENSAGENS_INCONSISTENCIA,
    listar_inconsistencias,
)
from app.ferramentas.extratus_aburesi.db.jobs import listar_erros_nao_resolvidos_do_motor


def listar_notificacoes():
    """Ver docstring equivalente em app/ferramentas/extratus/web/
    notificacoes.py (Extratus - Relatórios) — mesma lógica, tabelas
    próprias desse módulo (`_aburesi`)."""
    notificacoes = []

    for registro in listar_inconsistencias():
        motivo = MENSAGENS_INCONSISTENCIA.get(registro.status, "pendência na triagem")
        notificacoes.append({
            "mensagem": f'"{registro.nome_arquivo}": {motivo}',
            "tipo": "triagem",
            "link": "/extratus-aburesi/fila",
        })

    for job in listar_erros_nao_resolvidos_do_motor():
        motivo = job.erro_mensagem or job.tipo_erro or "falha desconhecida"
        notificacoes.append({
            "mensagem": f'"{job.arquivo_pdf}": erro ao processar ({motivo})',
            "tipo": "erro",
            "link": "/extratus-aburesi/erros",
        })

    return notificacoes
