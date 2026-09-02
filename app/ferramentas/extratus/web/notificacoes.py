from urllib.parse import quote

from app.ferramentas.extratus.db.checagem_fila import (
    MENSAGENS_INCONSISTENCIA,
    listar_inconsistencias,
)
from app.ferramentas.extratus.db.jobs import (
    listar_jobs_robo_nao_notificados_de_outros,
    listar_jobs_robo_nao_notificados_do_solicitante,
    listar_relatorios_manuais_nao_notificados_do_usuario,
)
from app.ferramentas.extratus.db.triagem_manual import (
    MENSAGENS_INCONSISTENCIA as MENSAGENS_INCONSISTENCIA_MANUAL,
    listar_erros_do_usuario,
    listar_inconsistencias_do_usuario,
)


def listar_notificacoes(usuario_id):
    """Pendências ativas do Robô deste módulo, pra aba "Ferramentas" do
    sininho (ver app/plataforma/web/notificacoes.py, que agrega isso com
    o do outro módulo e filtra por quem tem acesso).

    Henrique, diretoria, 2026-08-19: essa aba passou a cobrir TUDO que o
    Robô gera — antes só triagem+erro, agora também sucesso/revisão. A
    aba "Sistema" ficou reservada pra comunicados administrativos
    (feature futura, ainda não construída — nenhuma fonte aqui emite
    tipo "comunicado" ainda, então aquela aba fica vazia até nascer, sem
    precisar de nenhum código provisório).

    Henrique, 2026-09-02: quem PEDIU um relatório do Robô (Job.
    solicitante_id) não vê mais o aviso aqui — só em "Minhas" (ver
    listar_notificacoes_pessoais). `usuario_id` é só pra excluir esses
    itens da consulta (listar_jobs_robo_nao_notificados_de_outros);
    "Ferramentas" continua sem filtro de acesso além disso.

    4 comportamentos de propósito diferentes:
    - Inconsistências da triagem: somem sozinhas quando o arquivo é
      corrigido/removido da fila — sem ação manual nenhuma.
    - Erro do Robô: sem ação de resolver ainda (mesma lacuna de sempre,
      catalogada — não pode sumir sozinho).
    - Revisão do Robô: mesma coisa — sem ação de "marcar como revisado"
      pro Robô ainda, então também não pode sumir sozinho.
    - Sucesso do Robô: SEM X aqui (Henrique, 2026-09-02: "Ferramentas" é
      dos outros — só quem pediu, em "Minhas", pode dispensar; um job
      sem solicitante resolvido também aparece aqui, também sem X, até
      alguém tratar pelo fluxo real).
    """
    notificacoes = []

    for registro in listar_inconsistencias():
        motivo = MENSAGENS_INCONSISTENCIA.get(registro.status, "pendência na triagem")
        notificacoes.append({
            "mensagem": f'"{registro.nome_arquivo}": {motivo}',
            "tipo": "triagem",
            "link": "/extratus/fila",
            "criado_em": registro.atualizado_em.isoformat(),
        })

    for job in listar_jobs_robo_nao_notificados_de_outros(usuario_id):
        # Achado 2026-08-13: apontava pra "/extratus/erros", uma tela
        # dedicada que nunca chegou a ser construída (404 sempre) — manda
        # pra "Relatórios do Robô" (já mostra tudo isso, com abas
        # Sucesso/Revisão/Erro). Com "?processo=..." reaproveita o MESMO
        # mecanismo de deep-link que "Ir ao relatório" já usa ali
        # (relatorios_robo.js) — troca pra aba certa sozinho e dá
        # scroll/destaque no item, sem precisar de parâmetro novo.
        link = "/extratus/relatorios-robo"
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
    """Pendências do PRÓPRIO usuário no fluxo manual, pra aba "Minhas" do
    sininho (Henrique, 2026-08-13: "a aba minha é justamente pra abrigar
    os alertas do modo manual, que fazem jus às pessoas, tambem, que nao
    tem acesso às outras abas"). Diferente de listar_notificacoes (Fila
    do Robô), essas NUNCA dependem de acesso à Fila do Robô — só de
    acesso à ferramenta em si (ver app/plataforma/web/notificacoes.py).

    4 fontes, 2 famílias de comportamento:
    - Conferência pendente / erro (TriagemManual): ficam visíveis
      enquanto o registro existir — somem sozinhas quando resolvidas na
      própria tela (Conferências, ou o "×" de dispensar um erro). Nunca
      têm X aqui.
    - Pronto / revisão (Job, fluxo manual): "pronto" tem X
      (`descartavel`), dispensa na hora. "Revisão" não tem X — só sai
      daqui quando a pessoa clicar em "Marcar como revisado" no card do
      relatório (relatorios_manuais.html) — uma notificação importante
      não pode sumir sozinha, mesma exigência que já existia pro erro do
      Robô. As duas usam o mesmo campo por baixo, `Job.
      notificacao_resolvida`.

    Henrique, 2026-09-02: 5ª fonte — Job do ROBÔ que o próprio usuário
    pediu (Job.solicitante_id), mesma regra de "pronto tem X, resto não"
    (ver listar_notificacoes, que exclui esses jobs de "Ferramentas" pra
    não duplicar). O X aqui chama o MESMO resolver do Robô
    (marcar_notificacao_resolvida_robo, flag compartilhada sem dono) —
    Henrique pediu explicitamente que a flag continue única/simples, só
    a aba que muda por solicitante.
    """
    notificacoes = []

    for registro in listar_inconsistencias_do_usuario(usuario_id):
        motivo = MENSAGENS_INCONSISTENCIA_MANUAL.get(registro.status, "pendência na triagem")
        notificacoes.append({
            "mensagem": f'"{registro.nome_arquivo}": {motivo}',
            "tipo": "conferencia_manual",
            "link": "/extratus/",
            "pessoal": True,
            "descartavel": False,
            "criado_em": registro.atualizado_em.isoformat(),
        })

    for registro in listar_erros_do_usuario(usuario_id):
        notificacoes.append({
            "mensagem": f'"{registro.nome_arquivo}": falha ao gerar o relatório',
            "tipo": "erro_manual",
            "link": "/extratus/",
            "pessoal": True,
            "descartavel": False,
            "criado_em": registro.atualizado_em.isoformat(),
        })

    for job in listar_relatorios_manuais_nao_notificados_do_usuario(usuario_id):
        if job.status == "sucesso":
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": relatório pronto',
                "tipo": "pronto",
                "link": "/extratus/relatorios",
                "pessoal": True,
                "descartavel": True,
                "resolver": f"/extratus/relatorios/{job.id}/marcar-notificacao-resolvida",
                "criado_em": job.criado_em.isoformat(),
            })
        else:
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": relatório pronto, mas precisa de revisão',
                "tipo": "revisao",
                "link": "/extratus/relatorios",
                "pessoal": True,
                "descartavel": False,
                "criado_em": job.criado_em.isoformat(),
            })

    for job in listar_jobs_robo_nao_notificados_do_solicitante(usuario_id):
        link = "/extratus/relatorios-robo"
        if job.processo:
            link += "?processo=" + quote(job.processo)

        if job.status == "erro":
            motivo = job.erro_mensagem or job.tipo_erro or "falha desconhecida"
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": erro ao processar ({motivo})',
                "tipo": "erro",
                "link": link,
                "pessoal": True,
                "descartavel": False,
                "criado_em": job.criado_em.isoformat(),
            })
        elif job.status == "sucesso":
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": relatório do Robô pronto',
                "tipo": "pronto",
                "link": link,
                "pessoal": True,
                "descartavel": True,
                "resolver": f"/extratus/relatorios-robo/{job.id}/marcar-notificacao-resolvida",
                "criado_em": job.criado_em.isoformat(),
            })
        else:  # "revisao"
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": relatório do Robô pronto, mas precisa de revisão',
                "tipo": "revisao",
                "link": link,
                "pessoal": True,
                "descartavel": False,
                "criado_em": job.criado_em.isoformat(),
            })

    return notificacoes
