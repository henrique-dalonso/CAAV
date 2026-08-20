from datetime import datetime

from sqlmodel import func, select, update

from app.ferramentas.extratus_aburesi.db.models import ChecagemFila, ItemLoteRobo, LoteRobo, UploadFilaRobo
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
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    checagem_fila.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        sessao.add(UploadFilaRobo(nome_arquivo=nome_arquivo, usuario_id=usuario_id))
        sessao.commit()


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

        # Ver comentário equivalente em app/ferramentas/extratus/db/
        # checagem_fila.py (Extratus - Relatórios) — mesma lógica.
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
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    checagem_fila.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        return sessao.exec(select(ChecagemFila).where(ChecagemFila.nome_arquivo == nome_arquivo)).first()


def listar_inconsistencias():
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    checagem_fila.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = select(ChecagemFila).where(ChecagemFila.status.in_(STATUS_INCONSISTENCIA))
        return sessao.exec(consulta).all()


def contar_inconsistencias_ativas():
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    checagem_fila.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = select(func.count()).select_from(ChecagemFila).where(
            ChecagemFila.status.in_(STATUS_INCONSISTENCIA)
        )
        return sessao.exec(consulta).one()


def contar_inconsistencias_novas(desde):
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    checagem_fila.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = select(func.count()).select_from(ChecagemFila).where(
            ChecagemFila.status.in_(STATUS_INCONSISTENCIA),
            ChecagemFila.atualizado_em > desde,
        )
        return sessao.exec(consulta).one()


def aprovar_manualmente(registro_id, processo_manual=None):
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    checagem_fila.py (Extratus - Relatórios) — mesma lógica."""
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
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    checagem_fila.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        registro = sessao.get(ChecagemFila, registro_id)

        if not registro:
            return

        era_inconsistencia = registro.status in STATUS_INCONSISTENCIA

        sessao.delete(registro)
        sessao.commit()

        if era_inconsistencia:
            avisar_mudanca()
