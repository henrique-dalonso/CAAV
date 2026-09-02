from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import or_
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
    solicitante_id=None,
):
    """Registra um PDF que gerou relatório — status "sucesso" (confiança
    alta) ou "revisao" (confiança média/baixa, precisa de olho humano).

    `uso_ia`, se informado, é um dict com modelo/tokens_entrada/tokens_saida/
    custo_estimado_usd.
    `usuario_id` identifica quem disparou o processamento (upload/processar
    tudo) — fica None pra execuções via linha de comando/robô automático.
    `solicitante_id` — ver docstring de Job.solicitante_id (db/models.py):
    quem PEDIU, distinto de usuario_id (dono/origem), só preenchido pelo
    Robô.
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
            solicitante_id=solicitante_id,
        )

        sessao.add(job)
        sessao.commit()
        sessao.refresh(job)

        avisar_mudanca()

        return job


def registrar_erro(
    arquivo_pdf, processo, tipo_erro, erro_mensagem, destino_pdf=None, usuario_id=None, solicitante_id=None
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
            solicitante_id=solicitante_id,
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
    usado pela tela "Relatórios". Os do Robô (usuario_id None) têm sua
    própria tela, "Relatórios do Robô" (Henrique, 2026-08-08: "na
    aba manual só aparecerão os relatórios realizados manualmente...
    e na Relatórios do Robô será o repositório universal do robô").
    `listar_jobs()` continua sem filtro nenhum — Custos (admin) precisa
    ver tudo, Robô incluso."""
    with obter_sessao() as sessao:
        consulta = (
            select(Job)
            .where(Job.usuario_id.is_not(None))
            .order_by(Job.criado_em.desc())
            .limit(limite)
        )

        return sessao.exec(consulta).all()


def listar_jobs_robo(limite=100):
    """Só os relatórios (prontos, em revisão ou com erro) gerados pelo
    Robô (usuario_id None) — alimenta "Relatórios do Robô"."""
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
    `usuario_id` None = Robô ("Relatórios do Robô"), preenchido =
    manual ("Relatórios URGENTES") — Henrique, 2026-08-12: o botão "Ir ao
    relatório" estava sempre mandando pra "Seus Relatórios" (nome da tela
    na época) mesmo quando
    o duplicado era do Robô, e lá ele nunca existe. Um Job com status
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


def listar_jobs_robo_nao_notificados_de_outros(usuario_id):
    """Jobs do Robô (usuario_id None) de QUALQUER status (sucesso,
    revisão, erro) ainda não notificados, EXCETO os que o próprio
    usuário pediu — alimenta a aba "Ferramentas" do sininho (Henrique,
    diretoria, 2026-08-19: essa aba passou a cobrir tudo que o Robô
    gera, não só conferência/erro; Henrique, 2026-09-02: quem pediu um
    relatório passa a ver o aviso só em "Minhas" — ver
    listar_jobs_robo_nao_notificados_do_solicitante, o par desta — pro
    resto do escritório continua aparecendo aqui, sem saber quem pediu).
    Fila compartilhada pra quem sobra aqui — sem dono, sem filtro de
    acesso além do solicitante excluído."""
    with obter_sessao() as sessao:
        consulta = select(Job).where(
            Job.usuario_id.is_(None),
            Job.notificacao_resolvida == False,  # noqa: E712
            or_(Job.solicitante_id.is_(None), Job.solicitante_id != usuario_id),
        )
        return sessao.exec(consulta).all()


def listar_jobs_robo_nao_notificados_do_solicitante(usuario_id):
    """Jobs do Robô que o PRÓPRIO usuário pediu (Job.solicitante_id) e
    ainda não foram notificados — alimenta a aba "Minhas" do sininho,
    par de listar_jobs_robo_nao_notificados_de_outros (Henrique,
    2026-09-02). Jobs do Robô sem solicitante resolvido (pré-migração,
    ver resolver_solicitantes()) nunca caem aqui — continuam só em
    "Ferramentas", sem dono."""
    with obter_sessao() as sessao:
        consulta = select(Job).where(
            Job.usuario_id.is_(None),
            Job.solicitante_id == usuario_id,
            Job.notificacao_resolvida == False,  # noqa: E712
        )
        return sessao.exec(consulta).all()


def marcar_notificacao_resolvida_robo(job_id):
    """Dispensa a notificação de um Job do Robô — compartilhado, sem
    dono, então qualquer um com acesso à ferramenta pode dispensar (ao
    contrário de marcar_notificacao_resolvida, que só o dono do
    relatório manual pode). Hoje só usado pelo X de "sucesso" do Robô —
    "revisão" e "erro" continuam sem dispensa própria de propósito
    (mesma exigência de "não pode sumir sozinho sem alguém tratar" que
    já existia)."""
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
    """Relatórios manuais do PRÓPRIO usuário (sucesso ou revisão) que
    ainda não tiveram a notificação dispensada — alimenta a aba "Minhas"
    do sininho (Henrique, 2026-08-13). "Sucesso" some com um X na
    própria notificação; "revisão" só sai daqui quando a pessoa clicar
    em "Marcar como revisado" no card do relatório (relatorios_manuais.
    html) — nunca pelo X, mesma exigência de "não pode sumir sozinho"
    que o erro do Robô já tinha. As duas chamam marcar_notificacao_
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


def obter_job(job_id):
    """Busca um job pelo id, sem exigir dono — usado pela rota de "ver
    PDF de origem" nas telas de Relatórios prontos (manual e Robô,
    Henrique 2026-08-21), que são acervo compartilhado do escritório,
    diferente da fila pessoal de Conferências."""
    with obter_sessao() as sessao:
        return sessao.get(Job, job_id)


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


def contar_relatorios_robo_concluidos():
    """Quantos relatórios do Robô (usuario_id None) já foram gerados de
    verdade — "sucesso" ou "revisão" contam (as duas formas de "saiu um
    documento", só muda o nível de confiança); "erro" não conta (não
    produziu nada). Usado como estatística na tela de Configurações
    (admin) — Henrique, 2026-08-25: "preciso saber quantos relatórios
    foram concluídos no total, não só lotes" (lote é o conceito do Batch
    API, pode ter vários PDFs — isso aqui é contagem de documento real)."""
    with obter_sessao() as sessao:
        consulta = (
            select(Job.status, func.count())
            .where(
                Job.usuario_id.is_(None),
                Job.status.in_(["sucesso", "revisao"]),
            )
            .group_by(Job.status)
        )
        contagem = dict(sessao.exec(consulta).all())

    return contagem.get("sucesso", 0) + contagem.get("revisao", 0)


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
    """Quantos relatórios manuais o PRÓPRIO usuário logado solicitou —
    alimenta a contagem da aba "Relatórios URGENTES" na navegação
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
    badge duplo "+N" da aba "Relatórios URGENTES" (rotulos.py): um número na
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


def contar_relatorios_robo_novos(usuario_id, desde):
    """Mesma ideia de `contar_relatorios_novos_do_usuario`, pros
    relatórios do Robô (usuario_id None) — alimenta o badge duplo da aba
    "Relatórios do Robô". Henrique, 2026-09-02: só conta os que o
    PRÓPRIO usuário pediu (Job.solicitante_id) — mesma regra de
    "Ferramentas" é dos outros, "Minhas"/pessoal é seu que já vale pro
    sino de notificações; antes contava a fila inteira, compartilhada,
    então um relatório pedido por um colega também "acendia" +1 pra
    todo mundo. Job sem solicitante resolvido (pré-migração) não conta
    pra ninguém — mesma lacuna conhecida do sino."""
    with obter_sessao() as sessao:
        consulta = (
            select(Job.status, func.count())
            .where(
                Job.usuario_id.is_(None),
                Job.solicitante_id == usuario_id,
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


def _mes_menos(ano, mes, quantidade):
    """Aritmética de mês sem depender de datetime.replace (que quebra ao
    cruzar janeiro) — devolve (ano, mês) de `quantidade` meses ANTES de
    ano/mês dados."""
    indice = (ano * 12 + (mes - 1)) - quantidade
    return indice // 12, indice % 12 + 1


def resumo_mes_atual():
    """Custo, quantidade de casos e custo médio por caso do mês CORRENTE
    (reinicia sozinho todo dia 1º) + o mesmo do mês anterior, pra dar
    noção de subida/queda — dashboard de Custos (admin), Henrique,
    diretoria, 2026-08-26. Só conta Job com custo > 0, mesmo critério de
    `somar_custo_por_usuario` (um erro, que nunca tem custo real
    registrado, não deveria inflar nem diluir a média)."""
    agora = datetime.now()
    inicio_mes_atual = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ano_anterior, mes_anterior = _mes_menos(inicio_mes_atual.year, inicio_mes_atual.month, 1)
    inicio_mes_anterior = inicio_mes_atual.replace(year=ano_anterior, month=mes_anterior)

    with obter_sessao() as sessao:
        quantidade_atual, custo_atual = sessao.exec(
            select(func.count(), func.sum(Job.custo_estimado_usd))
            .where(Job.custo_estimado_usd > 0, Job.criado_em >= inicio_mes_atual)
        ).first()

        quantidade_anterior, custo_anterior = sessao.exec(
            select(func.count(), func.sum(Job.custo_estimado_usd))
            .where(
                Job.custo_estimado_usd > 0,
                Job.criado_em >= inicio_mes_anterior,
                Job.criado_em < inicio_mes_atual,
            )
        ).first()

    quantidade_atual = quantidade_atual or 0
    quantidade_anterior = quantidade_anterior or 0
    custo_atual = custo_atual or 0.0
    custo_anterior = custo_anterior or 0.0

    return {
        "custo_mes": custo_atual,
        "quantidade_mes": quantidade_atual,
        "custo_medio_mes": (custo_atual / quantidade_atual) if quantidade_atual else 0.0,
        "custo_mes_anterior": custo_anterior,
        "quantidade_mes_anterior": quantidade_anterior,
        "custo_medio_mes_anterior": (custo_anterior / quantidade_anterior) if quantidade_anterior else 0.0,
    }


# Períodos aceitos por `serie_temporal_custo` — dias de janela, exceto
# "1a" que usa granularidade de MÊS (365 pontos diários seria ilegível
# num gráfico pequeno).
PERIODOS_SERIE_TEMPORAL = {"7d": 7, "15d": 15, "30d": 30, "1a": 365}


def serie_temporal_custo(periodo):
    """Gasto agregado por dia (períodos "7d"/"15d"/"30d") ou por mês
    ("1a", últimos 12 meses) — alimenta o gráfico da tela de Custos.
    Sempre devolve um ponto por dia/mês do intervalo inteiro, mesmo sem
    nenhum custo naquele dia/mês (fica em 0) — um gráfico com buracos
    pulando datas seria enganoso."""
    if periodo not in PERIODOS_SERIE_TEMPORAL:
        raise ValueError(f"Período inválido: {periodo!r}")

    agora = datetime.now()
    granularidade_mensal = periodo == "1a"

    if granularidade_mensal:
        inicio_mes_atual = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ano_corte, mes_corte = _mes_menos(inicio_mes_atual.year, inicio_mes_atual.month, 11)
        corte = inicio_mes_atual.replace(year=ano_corte, month=mes_corte)
    else:
        dias = PERIODOS_SERIE_TEMPORAL[periodo]
        corte = (agora - timedelta(days=dias - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    with obter_sessao() as sessao:
        linhas = sessao.exec(
            select(Job.criado_em, Job.custo_estimado_usd)
            .where(Job.custo_estimado_usd > 0, Job.criado_em >= corte)
        ).all()

    agregados = {}
    for criado_em, custo in linhas:
        chave = criado_em.strftime("%Y-%m") if granularidade_mensal else criado_em.strftime("%Y-%m-%d")
        agregados[chave] = agregados.get(chave, 0.0) + custo

    pontos = []
    if granularidade_mensal:
        for i in range(11, -1, -1):
            ano, mes = _mes_menos(agora.year, agora.month, i)
            chave = f"{ano:04d}-{mes:02d}"
            pontos.append({"rotulo": f"{mes:02d}/{ano}", "custo": round(agregados.get(chave, 0.0), 4)})
    else:
        for i in range(PERIODOS_SERIE_TEMPORAL[periodo] - 1, -1, -1):
            dia = agora - timedelta(days=i)
            chave = dia.strftime("%Y-%m-%d")
            pontos.append({"rotulo": dia.strftime("%d/%m"), "custo": round(agregados.get(chave, 0.0), 4)})

    return pontos


def detalhar_custo_e_quantidade_por_usuario():
    """Igual `somar_custo_por_usuario`, mas também traz a QUANTIDADE de
    relatórios solicitados e o custo médio por relatório de cada
    usuário — Henrique, diretoria, 2026-08-26: "custo por usuário
    detalhado (com quantidade de relatórios solicitados, intensidade de
    uso)"."""
    with obter_sessao() as sessao:
        linhas = sessao.exec(
            select(Job.usuario_id, func.count(), func.sum(Job.custo_estimado_usd))
            .where(Job.custo_estimado_usd > 0)
            .group_by(Job.usuario_id)
        ).all()

    return {
        usuario_id: {
            "quantidade": quantidade,
            "custo": custo,
            "custo_medio": (custo / quantidade) if quantidade else 0.0,
        }
        for usuario_id, quantidade, custo in linhas
    }


def resumo_por_status_com_custo():
    """Quantidade E custo agregados por status (sucesso/revisão/erro) —
    "erro" quase sempre fica com custo 0 (a chamada que teria custo real
    não chegou a terminar com sucesso), mas a quantidade ainda importa
    pra ver proporção de falha."""
    resultado = {status: {"quantidade": 0, "custo": 0.0} for status in ("sucesso", "revisao", "erro")}

    with obter_sessao() as sessao:
        linhas = sessao.exec(
            select(Job.status, func.count(), func.sum(Job.custo_estimado_usd)).group_by(Job.status)
        ).all()

    for status, quantidade, custo in linhas:
        if status in resultado:
            resultado[status] = {"quantidade": quantidade, "custo": custo or 0.0}

    return resultado


def resumo_por_modelo():
    """Quantidade e custo agregados por modelo de IA que respondeu de
    verdade (Sonnet padrão vs Haiku, ver MODELO_PEDACO em ia_cliente.py)
    — só conta Job com custo > 0."""
    with obter_sessao() as sessao:
        linhas = sessao.exec(
            select(Job.modelo_ia, func.count(), func.sum(Job.custo_estimado_usd))
            .where(Job.custo_estimado_usd > 0)
            .group_by(Job.modelo_ia)
        ).all()

    return [
        {"modelo": modelo or "Desconhecido", "quantidade": quantidade, "custo": custo}
        for modelo, quantidade, custo in linhas
    ]
