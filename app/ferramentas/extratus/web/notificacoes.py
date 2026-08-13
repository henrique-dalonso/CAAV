from app.ferramentas.extratus.db.checagem_fila import (
    MENSAGENS_INCONSISTENCIA,
    listar_inconsistencias,
)
from app.ferramentas.extratus.db.jobs import (
    listar_erros_nao_resolvidos_do_motor,
    listar_relatorios_manuais_nao_notificados_do_usuario,
)
from app.ferramentas.extratus.db.triagem_manual import (
    MENSAGENS_INCONSISTENCIA as MENSAGENS_INCONSISTENCIA_MANUAL,
    listar_erros_do_usuario,
    listar_inconsistencias_do_usuario,
)


def listar_notificacoes():
    """Pendências ativas da Fila do Motor deste módulo, pro sininho de
    notificações (ver app/plataforma/web/notificacoes.py, que agrega isso
    com o do outro módulo e filtra por quem tem acesso).

    Duas fontes, com comportamento bem diferente de propósito (Henrique,
    2026-08-06):
    - Inconsistências da triagem: somem sozinhas quando o arquivo é
      corrigido/removido da fila (a linha em ChecagemFila deixa de
      existir) — sem ação manual nenhuma.
    - Erros de PDF do Motor: ficam até alguém marcar como resolvido na
      futura tela dedicada de Erros (ainda não construída, mesmo
      tratamento "inacabado de propósito" já usado na triagem/
      Conferências) — por isso sem janela de tempo, um erro não pode
      sumir sozinho.
    """
    notificacoes = []

    for registro in listar_inconsistencias():
        motivo = MENSAGENS_INCONSISTENCIA.get(registro.status, "pendência na triagem")
        notificacoes.append({
            "mensagem": f'"{registro.nome_arquivo}": {motivo}',
            "tipo": "triagem",
            "link": "/extratus/fila",
        })

    for job in listar_erros_nao_resolvidos_do_motor():
        motivo = job.erro_mensagem or job.tipo_erro or "falha desconhecida"
        notificacoes.append({
            "mensagem": f'"{job.arquivo_pdf}": erro ao processar ({motivo})',
            "tipo": "erro",
            "link": "/extratus/erros",
        })

    return notificacoes


def listar_notificacoes_pessoais(usuario_id):
    """Pendências do PRÓPRIO usuário no fluxo manual, pra aba "Minhas" do
    sininho (Henrique, 2026-08-13: "a aba minha é justamente pra abrigar
    os alertas do modo manual, que fazem jus às pessoas, tambem, que nao
    tem acesso às outras abas"). Diferente de listar_notificacoes (Fila
    do Motor), essas NUNCA dependem de acesso à Fila do Motor — só de
    acesso à ferramenta em si (ver app/plataforma/web/notificacoes.py).

    4 fontes, 2 famílias de comportamento:
    - Conferência pendente / erro (TriagemManual): ficam visíveis
      enquanto o registro existir — somem sozinhas quando resolvidas na
      própria tela (Conferências, ou o "×" de dispensar um erro). Nunca
      têm X aqui.
    - Pronto / revisão (Job): "pronto" tem X (`descartavel`), dispensa
      na hora. "Revisão" não tem X — só sai daqui quando a pessoa clicar
      em "Marcar como revisado" no card do relatório
      (relatorios_prontos.html) — uma notificação importante não pode
      sumir sozinha, mesma exigência que já existia pro erro do Motor.
      As duas usam o mesmo campo por baixo, `Job.notificacao_resolvida`.
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
        })

    for registro in listar_erros_do_usuario(usuario_id):
        notificacoes.append({
            "mensagem": f'"{registro.nome_arquivo}": falha ao gerar o relatório',
            "tipo": "erro_manual",
            "link": "/extratus/",
            "pessoal": True,
            "descartavel": False,
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
            })
        else:
            notificacoes.append({
                "mensagem": f'"{job.arquivo_pdf}": relatório pronto, mas precisa de revisão',
                "tipo": "revisao",
                "link": "/extratus/relatorios",
                "pessoal": True,
                "descartavel": False,
            })

    return notificacoes
