from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import func, select, update

from app.ferramentas.extratus_aburesi.db.models import TriagemManual
from app.plataforma.db.session import obter_sessao
from app.plataforma.web.eventos_sse import avisar_mudanca


# Mesmo vocabulário de status que db/checagem_fila.py usa pra Fila do
# Motor — ver TriagemManual (db/models.py) pro porquê de ser uma tabela
# separada (aqui é pessoal por usuário, e também acompanha a geração em
# si, coisa que ChecagemFila nunca precisou fazer).
PENDENTE = "pendente"
PROCESSANDO = "processando"
CONCLUIDO = "concluido"
ERRO = "erro"
DUPLICADO_RELATORIO = "duplicado_relatorio"
DUPLICADO_EM_ANDAMENTO = "duplicado_em_andamento"
NAO_ENCONTRADO = "processo_nao_encontrado"
# Ver comentário equivalente em app/ferramentas/extratus/db/triagem_manual.py
# (Extratus - Relatórios) — falha ao LER o PDF trava em Pendentes (bolinha
# vermelha) igual às outras inconsistências, até Conferências resolver.
FALHA_LEITURA = "falha_leitura"

STATUS_INCONSISTENCIA = {DUPLICADO_RELATORIO, DUPLICADO_EM_ANDAMENTO, NAO_ENCONTRADO, FALHA_LEITURA}

STATUS_EXIGE_PROCESSO_MANUAL = {NAO_ENCONTRADO, FALHA_LEITURA}

MENSAGENS_INCONSISTENCIA = {
    DUPLICADO_RELATORIO: "já existe um relatório gerado para esse processo",
    DUPLICADO_EM_ANDAMENTO: "esse processo já está sendo processado por outro arquivo",
    NAO_ENCONTRADO: "não foi possível identificar o número do processo",
    FALHA_LEITURA: "não foi possível ler esse PDF",
}


def criar_registro(nome_arquivo, caminho_pdf, usuario_id):
    with obter_sessao() as sessao:
        registro = TriagemManual(
            nome_arquivo=nome_arquivo,
            caminho_pdf=str(caminho_pdf),
            usuario_id=usuario_id,
        )
        sessao.add(registro)
        sessao.commit()
        sessao.refresh(registro)

        return registro


def obter_registro(registro_id):
    with obter_sessao() as sessao:
        return sessao.get(TriagemManual, registro_id)


def atualizar_apos_triagem(registro_id, status, processo_detectado, confianca_nivel, confianca_motivo, origem_duplicado=None):
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    triagem_manual.py (Extratus - Relatórios) — mesma lógica, incluindo
    a trava do índice único parcial (db/session.py) contra 2 arquivos
    virando "processando" pro mesmo processo ao mesmo tempo."""
    with obter_sessao() as sessao:
        registro = sessao.get(TriagemManual, registro_id)

        if not registro:
            return None

        registro.status = status
        registro.processo_detectado = processo_detectado
        registro.confianca_nivel = confianca_nivel
        registro.confianca_motivo = confianca_motivo
        registro.origem_duplicado = origem_duplicado
        registro.atualizado_em = datetime.now()

        sessao.add(registro)
        try:
            sessao.commit()
        except IntegrityError:
            sessao.rollback()
            registro = sessao.get(TriagemManual, registro_id)
            registro.status = DUPLICADO_EM_ANDAMENTO
            registro.processo_detectado = processo_detectado
            registro.confianca_nivel = confianca_nivel
            registro.confianca_motivo = "Esse número de processo já está sendo processado por outro arquivo."
            registro.origem_duplicado = None
            registro.atualizado_em = datetime.now()
            sessao.add(registro)
            sessao.commit()

        sessao.refresh(registro)

        avisar_mudanca()

        return registro


def concluir(registro_id, job_id):
    with obter_sessao() as sessao:
        registro = sessao.get(TriagemManual, registro_id)

        if not registro:
            return None

        registro.status = CONCLUIDO
        registro.job_id = job_id
        registro.atualizado_em = datetime.now()

        sessao.add(registro)
        sessao.commit()
        sessao.refresh(registro)

        avisar_mudanca()

        return registro


def marcar_erro(registro_id, mensagem):
    with obter_sessao() as sessao:
        registro = sessao.get(TriagemManual, registro_id)

        if not registro:
            return None

        registro.status = ERRO
        registro.erro_mensagem = str(mensagem)
        registro.atualizado_em = datetime.now()

        sessao.add(registro)
        sessao.commit()
        sessao.refresh(registro)

        avisar_mudanca()

        return registro


def aprovar_manualmente(registro_id, processo_manual=None):
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    triagem_manual.py (Extratus - Relatórios) — mesma lógica: UPDATE
    condicional (trava contra clique duplo em "Aprovar") + tratamento do
    índice único parcial (trava contra outro arquivo já "processando"
    esse mesmo número de processo)."""
    with obter_sessao() as sessao:
        valores = {
            "status": PROCESSANDO,
            "confianca_nivel": "revisao",
            "confianca_motivo": "Liberado manualmente via Conferências, por cima de uma inconsistência da triagem.",
            "atualizado_em": datetime.now(),
        }
        if processo_manual:
            valores["processo_detectado"] = processo_manual

        try:
            resultado = sessao.exec(
                update(TriagemManual)
                .where(TriagemManual.id == registro_id, TriagemManual.status.in_(STATUS_INCONSISTENCIA))
                .values(**valores)
            )
            sessao.commit()
        except IntegrityError:
            sessao.rollback()
            registro = sessao.get(TriagemManual, registro_id)
            if not registro:
                return None
            registro.status = DUPLICADO_EM_ANDAMENTO
            if processo_manual:
                registro.processo_detectado = processo_manual
            registro.confianca_motivo = "Esse número de processo já está sendo processado por outro arquivo."
            registro.atualizado_em = datetime.now()
            sessao.add(registro)
            sessao.commit()
            avisar_mudanca()
            return None

        if resultado.rowcount == 0:
            return None

        registro = sessao.get(TriagemManual, registro_id)
        avisar_mudanca()

        return registro


def descartar(registro_id):
    with obter_sessao() as sessao:
        registro = sessao.get(TriagemManual, registro_id)

        if not registro:
            return

        sessao.delete(registro)
        sessao.commit()

        avisar_mudanca()


def listar_estado_do_usuario(usuario_id):
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    triagem_manual.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = select(TriagemManual).where(TriagemManual.usuario_id == usuario_id)
        registros = sessao.exec(consulta).all()

        return {
            "pendentes": [r for r in registros if r.status == PENDENTE or r.status in STATUS_INCONSISTENCIA],
            "processando": [r for r in registros if r.status not in STATUS_INCONSISTENCIA and r.status != PENDENTE],
        }


def listar_inconsistencias_do_usuario(usuario_id):
    with obter_sessao() as sessao:
        consulta = select(TriagemManual).where(
            TriagemManual.usuario_id == usuario_id,
            TriagemManual.status.in_(STATUS_INCONSISTENCIA),
        )
        return sessao.exec(consulta).all()


def listar_erros_do_usuario(usuario_id):
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    triagem_manual.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = select(TriagemManual).where(
            TriagemManual.usuario_id == usuario_id,
            TriagemManual.status == ERRO,
        )
        return sessao.exec(consulta).all()


def contar_registros_recentes_do_usuario(usuario_id, desde):
    """Quantos arquivos esse usuário enviou (aceitos, viraram registro de
    triagem) desde `desde` — usado pra limitar repetição na rota de
    upload (duplo clique, várias abas, script), já que cada registro
    aceito dispara uma chamada de IA cobrada."""
    with obter_sessao() as sessao:
        consulta = select(func.count()).select_from(TriagemManual).where(
            TriagemManual.usuario_id == usuario_id,
            TriagemManual.criado_em > desde,
        )
        return sessao.exec(consulta).one()


def contar_inconsistencias_ativas_do_usuario(usuario_id):
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    triagem_manual.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = select(func.count()).select_from(TriagemManual).where(
            TriagemManual.usuario_id == usuario_id,
            TriagemManual.status.in_(STATUS_INCONSISTENCIA),
        )
        return sessao.exec(consulta).one()


def contar_inconsistencias_novas_do_usuario(usuario_id, desde):
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    triagem_manual.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        consulta = select(func.count()).select_from(TriagemManual).where(
            TriagemManual.usuario_id == usuario_id,
            TriagemManual.status.in_(STATUS_INCONSISTENCIA),
            TriagemManual.atualizado_em > desde,
        )
        return sessao.exec(consulta).one()
