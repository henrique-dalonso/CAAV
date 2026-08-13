from sqlmodel import func, select

from app.ferramentas.extratus.db.models import Job
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
    tudo) — fica None pra execuções via linha de comando/motor automático.
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
    """Só os relatórios gerados manualmente (usuario_id preenchido) —
    usado pela tela "Relatórios". Os do Motor (usuario_id None) têm sua
    própria tela, "Relatórios Finalizados" (Henrique, 2026-08-08: "na
    aba manual só aparecerão os relatórios realizados manualmente...
    e na Relatórios do Motor será o repositório universal do motor").
    `listar_jobs()` continua sem filtro nenhum — Custos (admin) precisa
    ver tudo, Motor incluso."""
    with obter_sessao() as sessao:
        consulta = (
            select(Job)
            .where(Job.usuario_id.is_not(None))
            .order_by(Job.criado_em.desc())
            .limit(limite)
        )

        return sessao.exec(consulta).all()


def listar_jobs_motor(limite=100):
    """Só os relatórios (prontos, em revisão ou com erro) gerados pelo
    Motor (usuario_id None) — alimenta "Relatórios Finalizados"."""
    with obter_sessao() as sessao:
        consulta = (
            select(Job)
            .where(Job.usuario_id.is_(None))
            .order_by(Job.criado_em.desc())
            .limit(limite)
        )

        return sessao.exec(consulta).all()


def obter_relatorio_existente_para_processo(processo):
    """O Job de verdade bem-sucedido (status "sucesso" ou "revisao" — as
    duas formas de "gerou relatório", só muda o nível de confiança) mais
    recente pra esse número de processo, ou None. Usado pela checagem
    manual (core/pipeline_manual.py) pra saber ONDE o duplicado mora —
    `usuario_id` None = Motor ("Relatórios do Motor"), preenchido =
    manual ("Seus Relatórios") — Henrique, 2026-08-12: o botão "Ir ao
    relatório" estava sempre mandando pra "Seus Relatórios" mesmo quando
    o duplicado era do Motor, e lá ele nunca existe. Um Job com status
    "erro" NÃO conta (a tentativa falhou, não gerou nada)."""
    with obter_sessao() as sessao:
        consulta = (
            select(Job)
            .where(Job.processo == processo, Job.status.in_(["sucesso", "revisao"]))
            .order_by(Job.criado_em.desc())
        )
        return sessao.exec(consulta).first()


def existe_relatorio_gerado_para_processo(processo):
    """Já existe um Job de verdade bem-sucedido pra esse número de
    processo? Usado pela checagem da Fila do Motor (db/checagem_fila.py),
    que só precisa saber se existe, não onde."""
    return obter_relatorio_existente_para_processo(processo) is not None


def listar_erros_nao_resolvidos_do_motor():
    """Erros de PDF do Motor (usuario_id None — ver tratar_erro/
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


def listar_relatorios_manuais_nao_notificados_do_usuario(usuario_id):
    """Relatórios manuais do PRÓPRIO usuário (sucesso ou revisão) que
    ainda não tiveram a notificação dispensada — alimenta a aba "Minhas"
    do sininho (Henrique, 2026-08-13). "Sucesso" some com um X na
    própria notificação; "revisão" só sai daqui quando a pessoa clicar
    em "Marcar como revisado" no card do relatório (relatorios_prontos.
    html) — nunca pelo X, mesma exigência de "não pode sumir sozinho"
    que o erro do Motor já tinha. As duas chamam marcar_notificacao_
    resolvida por baixo."""
    with obter_sessao() as sessao:
        consulta = select(Job).where(
            Job.usuario_id == usuario_id,
            Job.status.in_(["sucesso", "revisao"]),
            Job.notificacao_resolvida == False,  # noqa: E712
        )
        return sessao.exec(consulta).all()


def marcar_notificacao_resolvida(job_id, usuario_id):
    """Dispensa a notificação de um relatório PRÓPRIO — X em "pronto" ou
    botão "Marcar como revisado" em "revisão", ambos chamam isso (mesmo
    campo por trás, `Job.notificacao_resolvida`). Só o dono do relatório
    pode; devolve False sem mudar nada se o job não existir ou não for
    dele — quem chama decide o que fazer com isso (404)."""
    with obter_sessao() as sessao:
        job = sessao.get(Job, job_id)

        if not job or job.usuario_id != usuario_id:
            return False

        job.notificacao_resolvida = True
        sessao.add(job)
        sessao.commit()

        avisar_mudanca()

        return True


def contar_por_status():
    contagem = {"sucesso": 0, "revisao": 0, "erro": 0}

    with obter_sessao() as sessao:
        for job in sessao.exec(select(Job)).all():
            contagem[job.status] = contagem.get(job.status, 0) + 1

    return contagem


def contar_jobs_manuais_do_usuario(usuario_id):
    """Quantos relatórios manuais o PRÓPRIO usuário logado solicitou —
    alimenta a contagem da aba "Seus Relatórios" na navegação
    (rotulos.py). Henrique, 2026-08-12: "o número flutuante... exibe a
    quantidade total, deve exibir somente a quantidade de relatórios
    realizados pelo usuário" — antes contava TODO mundo (contar_jobs_manuais,
    removida), destoando do que a própria tela mostra por padrão (o
    checkbox "Solicitados por mim" já vem marcado). Sem limite (diferente
    de listar_jobs_manuais, que pagina) — a aba precisa do número real."""
    with obter_sessao() as sessao:
        consulta = select(Job).where(Job.usuario_id == usuario_id)
        return len(sessao.exec(consulta).all())


def contar_relatorios_novos_do_usuario(usuario_id, desde):
    """Quantos relatórios manuais do PRÓPRIO usuário terminaram (sucesso
    ou revisão), cada categoria separada, desde `desde` — alimenta o
    badge duplo "+N" da aba "Seus Relatórios" (rotulos.py): um número na
    cor padrão (sucesso) e outro na cor de revisão, os dois podendo
    aparecer juntos (Henrique, 2026-08-13)."""
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


def contar_relatorios_motor_novos(desde):
    """Mesma ideia de `contar_relatorios_novos_do_usuario`, pros
    relatórios do Motor (usuario_id None) — alimenta o badge duplo da
    aba "Relatórios do Motor". A fila é compartilhada (não filtra por
    usuário), só o "desde" é pessoal — cada usuário vê como "novo" o que
    ainda não olhou, mesmo relatório sendo visível pra todo mundo."""
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
    admin, ver quanto cada login gastou e o total do sistema."""
    totais = {}

    with obter_sessao() as sessao:
        for job in sessao.exec(select(Job)).all():
            if not job.custo_estimado_usd:
                continue

            chave = job.usuario_id
            totais[chave] = totais.get(chave, 0.0) + job.custo_estimado_usd

    return totais
