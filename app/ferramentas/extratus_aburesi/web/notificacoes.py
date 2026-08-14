from urllib.parse import quote

from app.ferramentas.extratus_aburesi.db.checagem_fila import (
    MENSAGENS_INCONSISTENCIA,
    listar_inconsistencias,
)
from app.ferramentas.extratus_aburesi.db.jobs import (
    listar_erros_nao_resolvidos_do_motor,
    listar_relatorios_manuais_nao_notificados_do_usuario,
)
from app.ferramentas.extratus_aburesi.db.triagem_manual import (
    MENSAGENS_INCONSISTENCIA as MENSAGENS_INCONSISTENCIA_MANUAL,
    listar_erros_do_usuario,
    listar_inconsistencias_do_usuario,
)


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
        # Ver comentário equivalente em app/ferramentas/extratus/web/
        # notificacoes.py (Extratus - Relatórios) — mesma lógica.
        link = "/extratus-aburesi/relatorios-motor"
        if job.processo:
            link += "?processo=" + quote(job.processo)

        notificacoes.append({
            "mensagem": f'"{job.arquivo_pdf}": erro ao processar ({motivo})',
            "tipo": "erro",
            "link": link,
        })

    return notificacoes


def listar_notificacoes_pessoais(usuario_id):
    """Ver docstring equivalente em app/ferramentas/extratus/web/
    notificacoes.py (Extratus - Relatórios) — mesma lógica, tabelas
    próprias desse módulo (`_aburesi`)."""
    notificacoes = []

    for registro in listar_inconsistencias_do_usuario(usuario_id):
        motivo = MENSAGENS_INCONSISTENCIA_MANUAL.get(registro.status, "pendência na triagem")
        notificacoes.append({
            "mensagem": f'"{registro.nome_arquivo}": {motivo}',
            "tipo": "conferencia_manual",
            "link": "/extratus-aburesi/",
            "pessoal": True,
            "descartavel": False,
        })

    for registro in listar_erros_do_usuario(usuario_id):
        notificacoes.append({
            "mensagem": f'"{registro.nome_arquivo}": falha ao gerar o relatório',
            "tipo": "erro_manual",
            "link": "/extratus-aburesi/",
            "pessoal": True,
            "descartavel": False,
        })

    for job in listar_relatorios_manuais_nao_notificados_do_usuario(usuario_id):
        if job.status == "sucesso":
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": relatório pronto',
                "tipo": "pronto",
                "link": "/extratus-aburesi/relatorios",
                "pessoal": True,
                "descartavel": True,
                "resolver": f"/extratus-aburesi/relatorios/{job.id}/marcar-notificacao-resolvida",
            })
        else:
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": relatório pronto, mas precisa de revisão',
                "tipo": "revisao",
                "link": "/extratus-aburesi/relatorios",
                "pessoal": True,
                "descartavel": False,
            })

    return notificacoes
