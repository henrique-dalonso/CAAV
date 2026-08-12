from app.ferramentas.extratus.db.checagem_fila import (
    MENSAGENS_INCONSISTENCIA,
    listar_inconsistencias,
)
from app.ferramentas.extratus.db.jobs import listar_erros_nao_resolvidos_do_motor


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
