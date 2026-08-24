from urllib.parse import quote

from app.ferramentas.extratus_aburesi.db.checagem_fila import (
    MENSAGENS_INCONSISTENCIA,
    listar_inconsistencias,
)
from app.ferramentas.extratus_aburesi.db.jobs import (
    listar_jobs_robo_nao_notificados,
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
            "criado_em": registro.atualizado_em.isoformat(),
        })

    for job in listar_jobs_robo_nao_notificados():
        # Ver comentário equivalente em app/ferramentas/extratus/web/
        # notificacoes.py (Extratus - Relatórios) — mesma lógica.
        link = "/extratus-aburesi/relatorios-robo"
        if job.processo:
            link += "?processo=" + quote(job.processo)

        if job.status == "erro":
            motivo = job.erro_mensagem or job.tipo_erro or "falha desconhecida"
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": erro ao processar ({motivo})',
                "tipo": "erro",
                "link": link,
                "criado_em": job.criado_em.isoformat(),
            })
        elif job.status == "sucesso":
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": relatório do Robô pronto',
                "tipo": "pronto",
                "link": link,
                "descartavel": True,
                "resolver": f"/extratus-aburesi/relatorios-robo/{job.id}/marcar-notificacao-resolvida",
                "criado_em": job.criado_em.isoformat(),
            })
        else:  # "revisao"
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": relatório do Robô pronto, mas precisa de revisão',
                "tipo": "revisao",
                "link": link,
                "criado_em": job.criado_em.isoformat(),
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
            "criado_em": registro.atualizado_em.isoformat(),
        })

    for registro in listar_erros_do_usuario(usuario_id):
        notificacoes.append({
            "mensagem": f'"{registro.nome_arquivo}": falha ao gerar o relatório',
            "tipo": "erro_manual",
            "link": "/extratus-aburesi/",
            "pessoal": True,
            "descartavel": False,
            "criado_em": registro.atualizado_em.isoformat(),
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
                "criado_em": job.criado_em.isoformat(),
            })
        else:
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": relatório pronto, mas precisa de revisão',
                "tipo": "revisao",
                "link": "/extratus-aburesi/relatorios",
                "pessoal": True,
                "descartavel": False,
                "criado_em": job.criado_em.isoformat(),
            })

    return notificacoes
