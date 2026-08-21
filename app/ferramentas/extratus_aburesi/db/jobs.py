from pathlib import Path

from sqlmodel import func, select

from app.ferramentas.extratus_aburesi.db.models import Job
from app.plataforma.db.session import obter_sessao
from app.plataforma.web.eventos_sse import avisar_mudanca


def registrar_processado(
    arquivo_pdf,
    processo,
    relatorio_path,
    destino_pdf,
    confianca,
    motivo_confianca=None,
    uso_ia=None,
    usuario_id=None,
):
    """Registra um PDF que gerou relatório — status "sucesso" (confiança
    alta) ou "revisao" (confiança média/baixa, precisa de olho humano).

    `uso_ia`, se informado, é um dict com modelo/tokens_entrada/tokens_saida/
    custo_estimado_usd.
    `usuario_id` identifica quem disparou o processamento (upload/processar
    tudo) — fica None pra execuções via linha de comando/robô automático.
    """
    status = "sucesso" if str(confianca).strip().lower() == "alta" else "revisao"
    uso_ia = uso_ia or {}

    with obter_sessao() as sessao:
        job = Job(
            arquivo_pdf=str(arquivo_pdf),
            processo=processo,
            status=status,
            confianca=confianca,
            motivo_confianca=motivo_confianca,
            relatorio_path=str(relatorio_path) if relatorio_path else None,
            destino_pdf=str(destino_pdf) if destino_pdf else None,
            modelo_ia=uso_ia.get("modelo"),
            tokens_entrada=uso_ia.get("tokens_entrada"),
            tokens_saida=uso_ia.get("tokens_saida"),
            custo_estimado_usd=uso_ia.get("custo_estimado_usd"),
            usuario_id=usuario_id,
        )

        sessao.add(job)
        sessao.commit()
        sessao.refresh(job)

        avisar_mudanca()

        return job


def registrar_erro(
    arquivo_pdf, processo, tipo_erro, erro_mensagem, destino_pdf=None, usuario_id=None
):
    with obter_sessao() as sessao:
        job = Job(
            arquivo_pdf=str(arquivo_pdf),
            processo=processo,
            status="erro",
            tipo_erro=tipo_erro,
            erro_mensagem=str(erro_mensagem),
            destino_pdf=str(destino_pdf) if destino_pdf else None,
            usuario_id=usuario_id,
        )

        sessao.add(job)
        sessao.commit()
        sessao.refresh(job)

        avisar_mudanca()

        return job


def listar_jobs(limite=100):
    with obter_sessao() as sessao:
        consulta = (
            select(Job)
            .order_by(Job.criado_em.desc())
            .limit(limite)
        )

        return sessao.exec(consulta).all()


def listar_jobs_manuais(limite=100):
    """Ver docstring equivalente em app/ferramentas/extratus/db/jobs.py
    (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = (
            select(Job)
            .where(Job.usuario_id.is_not(None))
            .order_by(Job.criado_em.desc())
            .limit(limite)
        )

        return sessao.exec(consulta).all()


def listar_jobs_robo(limite=100):
    """Ver docstring equivalente em app/ferramentas/extratus/db/jobs.py
    (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = (
            select(Job)
            .where(Job.usuario_id.is_(None))
            .order_by(Job.criado_em.desc())
            .limit(limite)
        )

        return sessao.exec(consulta).all()


def obter_relatorio_existente_para_processo(processo):
    """Ver docstring equivalente em app/ferramentas/extratus/db/jobs.py
    (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = (
            select(Job)
            .where(Job.processo == processo, Job.status.in_(["sucesso", "revisao"]))
            .order_by(Job.criado_em.desc())
        )
        return sessao.exec(consulta).first()


def existe_relatorio_gerado_para_processo(processo):
    """Já existe um Job de verdade bem-sucedido pra esse número de
    processo? Usado pela checagem da Fila do Robô (db/checagem_fila.py),
    que só precisa saber se existe, não onde."""
    return obter_relatorio_existente_para_processo(processo) is not None


def listar_erros_nao_resolvidos_do_robo():
    """Erros de PDF do Robô (usuario_id None — ver tratar_erro/
    checagem_lote.py) que ainda não foram marcados como resolvidos —
    alimenta o sininho de notificações. Não tem janela de tempo de
    propósito (Henrique: um erro não pode sumir sozinho, alguém precisa
    de fato tratar) — só sai daqui quando a futura tela de Erros marcar
    `notificacao_resolvida`. Erros do fluxo manual (usuario_id
    preenchido) não entram — a pessoa já viu o erro na hora, síncrono."""
    with obter_sessao() as sessao:
        consulta = select(Job).where(
            Job.status == "erro",
            Job.usuario_id.is_(None),
            Job.notificacao_resolvida == False,  # noqa: E712
        )
        return sessao.exec(consulta).all()


def listar_jobs_robo_nao_notificados():
    """Ver docstring equivalente em app/ferramentas/extratus/db/jobs.py
    (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = select(Job).where(
            Job.usuario_id.is_(None),
            Job.notificacao_resolvida == False,  # noqa: E712
        )
        return sessao.exec(consulta).all()


def marcar_notificacao_resolvida_robo(job_id):
    """Ver docstring equivalente em app/ferramentas/extratus/db/jobs.py
    (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        job = sessao.get(Job, job_id)

        if not job or job.usuario_id is not None:
            return False

        job.notificacao_resolvida = True
        sessao.add(job)
        sessao.commit()

        avisar_mudanca()

        return True


def listar_relatorios_manuais_nao_notificados_do_usuario(usuario_id):
    """Ver docstring equivalente em app/ferramentas/extratus/db/jobs.py
    (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = select(Job).where(
            Job.usuario_id == usuario_id,
            Job.status.in_(["sucesso", "revisao"]),
            Job.notificacao_resolvida == False,  # noqa: E712
        )
        return sessao.exec(consulta).all()


def marcar_notificacao_resolvida(job_id, usuario_id):
    """Ver docstring equivalente em app/ferramentas/extratus/db/jobs.py
    (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        job = sessao.get(Job, job_id)

        if not job or job.usuario_id != usuario_id:
            return False

        job.notificacao_resolvida = True
        sessao.add(job)
        sessao.commit()

        avisar_mudanca()

        return True


def excluir_job(job_id):
    """Exclui um relatório permanentemente — Henrique, diretoria,
    2026-08-21: só admin da plataforma pode (ver exigir_admin na rota),
    independente de quem gerou ou do status. Remove o arquivo físico do
    relatório (.docx) e o PDF de origem já movido pra pasta final
    (processados/revisão/erros), além da própria linha no banco. Devolve
    False sem mudar nada se o job já não existir mais."""
    with obter_sessao() as sessao:
        job = sessao.get(Job, job_id)

        if not job:
            return False

        for caminho in (job.relatorio_path, job.destino_pdf):
            if caminho and Path(caminho).exists():
                Path(caminho).unlink()

        sessao.delete(job)
        sessao.commit()

        avisar_mudanca()

        return True


def contar_por_status():
    contagem = {"sucesso": 0, "revisao": 0, "erro": 0}

    with obter_sessao() as sessao:
        linhas = sessao.exec(
            select(Job.status, func.count()).group_by(Job.status)
        ).all()

    for status, total in linhas:
        contagem[status] = total

    return contagem


def contar_jobs_manuais_do_usuario(usuario_id):
    """Ver docstring equivalente em app/ferramentas/extratus/db/jobs.py
    (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = select(Job).where(Job.usuario_id == usuario_id)
        return len(sessao.exec(consulta).all())


def contar_relatorios_novos_do_usuario(usuario_id, desde):
    """Ver docstring equivalente em app/ferramentas/extratus/db/jobs.py
    (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = (
            select(Job.status, func.count())
            .where(
                Job.usuario_id == usuario_id,
                Job.criado_em > desde,
                Job.status.in_(["sucesso", "revisao"]),
            )
            .group_by(Job.status)
        )
        contagem = dict(sessao.exec(consulta).all())

    return {"sucesso": contagem.get("sucesso", 0), "revisao": contagem.get("revisao", 0)}


def contar_relatorios_robo_novos(desde):
    """Ver docstring equivalente em app/ferramentas/extratus/db/jobs.py
    (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = (
            select(Job.status, func.count())
            .where(
                Job.usuario_id.is_(None),
                Job.criado_em > desde,
                Job.status.in_(["sucesso", "revisao"]),
            )
            .group_by(Job.status)
        )
        contagem = dict(sessao.exec(consulta).all())

    return {"sucesso": contagem.get("sucesso", 0), "revisao": contagem.get("revisao", 0)}


def somar_custo_por_usuario():
    """Soma o custo estimado de IA por usuário — pra tela de custos do
    admin, ver quanto cada login gastou e o total do sistema. Só soma
    Job com custo > 0 (igual ao comportamento antigo, que pulava custo
    None/0) — um usuário sem nenhum custo real não aparece no dicionário."""
    with obter_sessao() as sessao:
        linhas = sessao.exec(
            select(Job.usuario_id, func.sum(Job.custo_estimado_usd))
            .where(Job.custo_estimado_usd > 0)
            .group_by(Job.usuario_id)
        ).all()

    return {usuario_id: total for usuario_id, total in linhas}
