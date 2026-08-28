from datetime import datetime

from sqlmodel import func, select, update

from app.ferramentas.extratus.db.models import ChecagemFila, ItemLoteRobo, LoteRobo, UploadFilaRobo
from app.plataforma.db.session import obter_sessao
from app.plataforma.web.eventos_sse import avisar_mudanca


# Valores possíveis de ChecagemFila.status — só "aprovado" deixa um
# arquivo elegível pro Robô reivindicar. Qualquer outro (inclusive
# NAO_ENCONTRADO) trava o arquivo até o painel de Conferências (ainda
# não construído) resolver, de propósito — ver docstring de ChecagemFila.
PENDENTE = "pendente"
APROVADO = "aprovado"
DUPLICADO_RELATORIO = "duplicado_relatorio"
DUPLICADO_EM_ANDAMENTO = "duplicado_em_andamento"
NAO_ENCONTRADO = "processo_nao_encontrado"

# Todo status que NÃO seja aprovado/pendente representa uma inconsistência
# real, à espera do painel de Conferências.
STATUS_INCONSISTENCIA = {DUPLICADO_RELATORIO, DUPLICADO_EM_ANDAMENTO, NAO_ENCONTRADO}

# Frase pronta por tipo — usada tanto pelo sininho de notificações
# (web/notificacoes.py) quanto pelo painel de Conferências (fila.py), pra
# nunca ter duas versões do mesmo texto flutuando pelo código.
MENSAGENS_INCONSISTENCIA = {
    DUPLICADO_RELATORIO: "já existe um relatório gerado para esse processo",
    DUPLICADO_EM_ANDAMENTO: "esse processo já está sendo processado por outro arquivo na fila",
    NAO_ENCONTRADO: "não foi possível identificar o número do processo",
}


def registrar_upload(nome_arquivo, usuario_id):
    """Grava PRA SEMPRE quem enviou esse arquivo pela tela da Fila do
    Robô — ver docstring de UploadFilaRobo (db/models.py) pro porquê
    de ser uma tabela própria, não um campo em ChecagemFila. Auditoria
    PURA: cobre até arquivo que nunca vira Job (ex: descartado em
    Conferências por duplicidade) — diferente de
    `registrar_pendente`/`ChecagemFila.solicitante_id` abaixo, que só
    sobrevive enquanto o arquivo estiver na fila."""
    with obter_sessao() as sessao:
        sessao.add(UploadFilaRobo(nome_arquivo=nome_arquivo, usuario_id=usuario_id))
        sessao.commit()


def registrar_pendente(nome_arquivo, solicitante_id):
    """Cria a linha da Fila do Robô (`ChecagemFila`) pra esse arquivo JÁ
    com quem enviou — direto na hora do upload (`web/routes/fila.py`),
    antes até do próximo ciclo do watcher (`sincronizar_registros`)
    precisar criar uma linha sem essa informação.

    Henrique, diretoria, 2026-08-27: a diretoria perguntou "o coordenador
    fulano colocou os processos que pedi no robô?" e não dava pra
    responder. Tentativa anterior (achar isso por dedução depois, casando
    nome de arquivo + horário) foi substituída por isto — carregar
    `solicitante_id` desde a origem, por toda a esteira (ChecagemFila ->
    ItemLoteRobo -> Job), sem precisar adivinhar nada depois.

    Se a linha já existir (raro: o watcher rodou entre o arquivo cair no
    disco e essa chamada) só preenche `solicitante_id` se ainda estiver
    vazio — nunca sobrescreve um valor já presente."""
    with obter_sessao() as sessao:
        existente = sessao.exec(
            select(ChecagemFila).where(ChecagemFila.nome_arquivo == nome_arquivo)
        ).first()

        if existente:
            if existente.solicitante_id is None:
                existente.solicitante_id = solicitante_id
                sessao.add(existente)
                sessao.commit()
                # commit() expira os atributos do objeto por padrão — sem
                # refresh, ler qualquer atributo depois que a sessão
                # fechar (fora deste `with`) explode com
                # DetachedInstanceError.
                sessao.refresh(existente)
            return existente

        registro = ChecagemFila(nome_arquivo=nome_arquivo, status=PENDENTE, solicitante_id=solicitante_id)
        sessao.add(registro)
        sessao.commit()
        sessao.refresh(registro)

        return registro


def sincronizar_registros(nomes_no_disco):
    """Garante uma linha "pendente" pra todo nome novo em
    robo_pasta_entrada (upload pelo site OU qualquer outro jeito do
    arquivo aparecer ali) e apaga a linha de quem já saiu da pasta
    (removido manualmente, ou já reivindicado por um lote — nesse ponto
    a checagem já cumpriu seu papel). Devolve as linhas com status
    "pendente" de verdade, prontas pra checar."""
    with obter_sessao() as sessao:
        existentes = {c.nome_arquivo: c for c in sessao.exec(select(ChecagemFila)).all()}

        for nome in nomes_no_disco:
            if nome not in existentes:
                sessao.add(ChecagemFila(nome_arquivo=nome, status=PENDENTE))

        # Só importa pro sininho quando quem sai era uma inconsistência
        # de verdade (uma Conferência ficando órfã, ex: alguém apagou o
        # PDF por fora, ou o /fila/remover-varios de outra aba já cuidou
        # disso na hora) — arquivo pendente comum saindo daqui é rotina,
        # não é notificação de nada.
        sumiu_inconsistencia = any(
            nome not in nomes_no_disco and registro.status in STATUS_INCONSISTENCIA
            for nome, registro in existentes.items()
        )

        for nome, registro in existentes.items():
            if nome not in nomes_no_disco:
                sessao.delete(registro)

        sessao.commit()

        if sumiu_inconsistencia:
            avisar_mudanca()

        consulta = select(ChecagemFila).where(ChecagemFila.status == PENDENTE)
        return sessao.exec(consulta).all()


def atualizar_apos_checagem(registro_id, status, processo_detectado, confianca_nivel, confianca_motivo):
    with obter_sessao() as sessao:
        registro = sessao.get(ChecagemFila, registro_id)

        if not registro:
            return

        registro.status = status
        registro.processo_detectado = processo_detectado
        registro.confianca_nivel = confianca_nivel
        registro.confianca_motivo = confianca_motivo
        registro.atualizado_em = datetime.now()

        sessao.add(registro)
        sessao.commit()

        # Único lugar onde a checagem de verdade muda o status de um
        # arquivo (as 3 inconsistências + aprovado) — avisa o sininho na
        # hora em vez de esperar o próximo poll (Henrique, 2026-08-08).
        avisar_mudanca()


def existe_conflito_de_processo(processo, exceto_nome_arquivo):
    """Esse número de processo já está "em andamento" em outro arquivo
    (qualquer um exceto o próprio, sob checagem agora) — seja porque já
    foi aprovado na checagem (esperando o robô pegar) ou porque já foi
    reivindicado por um lote que ainda não terminou. Não olha lotes já
    concluídos aqui — se um relatório já saiu, isso é
    DUPLICADO_RELATORIO (ver db/jobs.py), categoria diferente."""
    with obter_sessao() as sessao:
        aprovado_em_outro_arquivo = sessao.exec(
            select(ChecagemFila).where(
                ChecagemFila.processo_detectado == processo,
                ChecagemFila.status == APROVADO,
                ChecagemFila.nome_arquivo != exceto_nome_arquivo,
            )
        ).first()

        if aprovado_em_outro_arquivo:
            return True

        em_lote_ativo = sessao.exec(
            select(ItemLoteRobo)
            .join(LoteRobo, LoteRobo.id == ItemLoteRobo.lote_id)
            .where(
                ItemLoteRobo.processo_detectado == processo,
                LoteRobo.status == "enviado",
            )
        ).first()

        return em_lote_ativo is not None


def estado_por_nome():
    """{nome_arquivo: status} pra tela/polling saberem qual bolinha
    mostrar. Um nome sem linha nenhuma (checagem ainda nem rodou o
    primeiro ciclo pra ele) é tratado como "pendente" por quem chama
    isso, não aqui — ver web/routes/fila.py."""
    with obter_sessao() as sessao:
        return {
            registro.nome_arquivo: registro.status
            for registro in sessao.exec(select(ChecagemFila)).all()
        }


def listar_aprovados_por_nome():
    """{nome_arquivo: ChecagemFila} só dos aprovados — usado pelo Robô
    (robo_lote.py) pra saber quem pode entrar num lote novo, reaproveitando
    o processo/confiança já detectados aqui (não detecta de novo)."""
    with obter_sessao() as sessao:
        consulta = select(ChecagemFila).where(ChecagemFila.status == APROVADO)
        return {registro.nome_arquivo: registro for registro in sessao.exec(consulta).all()}


def obter_registro(registro_id):
    with obter_sessao() as sessao:
        return sessao.get(ChecagemFila, registro_id)


def obter_registro_por_nome(nome_arquivo):
    """Usado por /fila/remover-varios pra limpar a linha de checagem na
    hora, sem esperar o próximo ciclo do watcher (Henrique, 2026-08-08:
    "quero que seja instantâneo") — remover um pendente que tinha uma
    conferência aberta é, na prática, um descarte, só que feito por um
    caminho diferente do painel de Conferências."""
    with obter_sessao() as sessao:
        return sessao.exec(select(ChecagemFila).where(ChecagemFila.nome_arquivo == nome_arquivo)).first()


def listar_inconsistencias():
    """Toda linha esperando decisão humana no painel de Conferências —
    usado tanto pela própria tela (web/routes/fila.py) quanto pelo
    sininho de notificações (web/notificacoes.py), única fonte pra não
    duplicar a consulta em dois lugares."""
    with obter_sessao() as sessao:
        consulta = select(ChecagemFila).where(ChecagemFila.status.in_(STATUS_INCONSISTENCIA))
        return sessao.exec(consulta).all()


def contar_inconsistencias_ativas():
    """Quantas Conferências da Fila do Robô estão pendentes AGORA, sem
    filtro de tempo — alimenta o badge "+N" da aba. Henrique, 2026-08-13:
    "não pode sumir só de entrar [na aba], permanece até alguém aprovar
    ou negar" — diferente de contar_inconsistencias_novas (abaixo), que
    zera ao visitar a aba (pensada originalmente pra esse badge, mas o
    comportamento certo pra Conferência é ficar ligado até resolver de
    verdade, igual já vale pro sininho de notificações)."""
    with obter_sessao() as sessao:
        consulta = select(func.count()).select_from(ChecagemFila).where(
            ChecagemFila.status.in_(STATUS_INCONSISTENCIA)
        )
        return sessao.exec(consulta).one()


def contar_inconsistencias_novas(desde):
    """Quantas Conferências da Fila do Robô (compartilhada, não é por
    usuário) surgiram desde `desde` — alimenta o badge "+N" (cor de
    revisão, único número dessa aba) em rotulos.py. `atualizado_em`, não
    `criado_em`, pelo mesmo motivo de `triagem_manual.
    contar_inconsistencias_novas_do_usuario`: é quando o registro virou
    inconsistência de verdade, e não muda sozinho enquanto continuar
    aberta."""
    with obter_sessao() as sessao:
        consulta = select(func.count()).select_from(ChecagemFila).where(
            ChecagemFila.status.in_(STATUS_INCONSISTENCIA),
            ChecagemFila.atualizado_em > desde,
        )
        return sessao.exec(consulta).one()


def aprovar_manualmente(registro_id, processo_manual=None):
    """Ação "Prosseguir" do painel de Conferências — pula as travas
    automáticas e libera o arquivo pro Robô pegar no próximo ciclo,
    exatamente como um "aprovado" comum (robo_lote.py não precisa saber
    que essa aprovação veio de um humano, não de checagem_lote.py).

    `processo_manual` só é usado no caso "processo não encontrado" (a
    pessoa digita o número na tela, ver web/routes/fila.py) — nos outros
    dois tipos de inconsistência o processo já tinha sido detectado
    certo, então o registro existente é mantido como está.

    Confiança forçada pra "revisão", nunca herda o nível antigo — mesmo
    princípio já usado em todo outro lugar do sistema onde uma trava de
    segurança automática é pulada (chunking de PDF grande, filtro de
    anexo de terceiros): uma aprovação manual por cima de um bloqueio
    automático sempre merece um novo par de olhos no relatório final,
    nunca deveria virar "alta confiança" silenciosamente. O motivo vira
    rastreável no Job final (motivo_confianca), já que quem chama
    registra a decisão de verdade em RegistroConferencia (db/conferencias.py).

    UPDATE condicional (só grava se o registro ainda estiver numa
    inconsistência) em vez de ler-e-gravar — trava contra clique duplo
    em "Aprovar": a segunda chamada não acha mais nenhuma linha pra
    atualizar (rowcount 0), devolve None, e quem chama sabe não
    duplicar o registro de auditoria (RegistroConferencia)."""
    with obter_sessao() as sessao:
        valores = {
            "status": APROVADO,
            "confianca_nivel": "revisao",
            "confianca_motivo": "Liberado manualmente via Conferências, por cima de uma inconsistência da triagem.",
            "atualizado_em": datetime.now(),
        }
        if processo_manual:
            valores["processo_detectado"] = processo_manual

        resultado = sessao.exec(
            update(ChecagemFila)
            .where(ChecagemFila.id == registro_id, ChecagemFila.status.in_(STATUS_INCONSISTENCIA))
            .values(**valores)
        )
        sessao.commit()

        if resultado.rowcount == 0:
            return None

        registro = sessao.get(ChecagemFila, registro_id)
        avisar_mudanca()

        return registro


def descartar(registro_id):
    """Ação "Descartar" do painel de Conferências — só apaga a linha da
    checagem. Quem chama (web/routes/fila.py) cuida de apagar o PDF de
    verdade da pasta antes disso, mesmo padrão já usado em
    /fila/remover-varios."""
    with obter_sessao() as sessao:
        registro = sessao.get(ChecagemFila, registro_id)

        if not registro:
            return

        era_inconsistencia = registro.status in STATUS_INCONSISTENCIA

        sessao.delete(registro)
        sessao.commit()

        # Só avisa o sininho se isso de fato tirava uma Conferência da
        # tela — descartar um pendente comum (via /fila/remover-varios)
        # não muda nada que o sininho mostre.
        if era_inconsistencia:
            avisar_mudanca()
