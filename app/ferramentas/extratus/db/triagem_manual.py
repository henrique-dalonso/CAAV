from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import func, select, update

from app.ferramentas.extratus.db.models import TriagemManual
from app.plataforma.db.session import obter_sessao
from app.plataforma.web.eventos_sse import avisar_mudanca


# Mesmo vocabulário de status que db/checagem_fila.py usa pra Fila do
# Robô — ver TriagemManual (db/models.py) pro porquê de ser uma tabela
# separada (aqui é pessoal por usuário, e também acompanha a geração em
# si, coisa que ChecagemFila nunca precisou fazer).
PENDENTE = "pendente"
PROCESSANDO = "processando"
CONCLUIDO = "concluido"
ERRO = "erro"
DUPLICADO_RELATORIO = "duplicado_relatorio"
DUPLICADO_EM_ANDAMENTO = "duplicado_em_andamento"
NAO_ENCONTRADO = "processo_nao_encontrado"
# Henrique, 2026-08-12: falha ao LER o PDF (arquivo corrompido/ilegível)
# não pode virar erro definitivo na hora — trava em Pendentes (bolinha
# vermelha) igual às outras 3 inconsistências, até alguém decidir em
# Conferências (Aprovar informando o processo na mão, ou Descartar).
# Antes disso, uma falha de leitura ia direto pra Job "erro" e sumia da
# tela sem chance de decisão humana — igual à Fila do Robô JÁ faz pras
# inconsistências de duplicidade/processo não encontrado.
FALHA_LEITURA = "falha_leitura"

STATUS_INCONSISTENCIA = {DUPLICADO_RELATORIO, DUPLICADO_EM_ANDAMENTO, NAO_ENCONTRADO, FALHA_LEITURA}

# Igual a NAO_ENCONTRADO na tela: nenhum processo foi detectado, então
# Conferências exige digitar o número na mão pra Aprovar — ver
# web/routes/gerar_relatorio.py e web/static/gerar_relatorio.js.
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
    """Resultado da checagem de duplicidade (mesma lógica de
    core/checagem_lote.py, reaproveitada em core/pipeline_manual.py) —
    usada tanto pras inconsistências (trava, espera Conferências) quanto
    pro caso aprovado (status=PROCESSANDO direto — aqui não existe um
    estado "aprovado" à parte esperando o Robô pegar depois, então o
    próprio pipeline_manual.py já segue pra geração em seguida).

    `origem_duplicado` ("robô" ou "manual") só é usado quando
    status=DUPLICADO_RELATORIO — diz pro botão "Ir ao relatório" (web/
    routes/gerar_relatorio.py) se o duplicado mora em "Relatórios do Robô" ou
    "Relatórios URGENTES".

    Henrique, 2026-08-13: quando `status` é PROCESSANDO, essa gravação
    esbarra no índice único parcial (db/session.py) que garante que só
    UM arquivo por vez fica "processando" pra um mesmo número de
    processo — a trava real contra 2 arquivos (2 uploads quase juntos,
    ou o mesmo caso enviado 2x) chamando a IA em duplicidade pro mesmo
    processo. Se acontecer, o SQLite recusa a gravação (IntegrityError)
    e aqui vira DUPLICADO_EM_ANDAMENTO, igual a quando a checagem já
    pega isso de antemão."""
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
    """Ação "Prosseguir" do painel de Conferências manual — mesma ideia
    de checagem_fila.aprovar_manualmente: pula a trava automática,
    confiança sempre forçada pra "revisão" (nunca herda alta confiança
    silenciosamente por cima de uma inconsistência). Quem chama
    (core/pipeline_manual.py) segue direto pra geração na sequência —
    aqui também a aprovação já é o próprio gatilho.

    Henrique, 2026-08-13: UPDATE condicional (só grava se o registro
    ainda estiver numa inconsistência) em vez de ler-e-gravar — trava
    real contra clique duplo em "Aprovar" (2 requisições quase juntas
    pro mesmo registro): a segunda não acha mais nenhuma linha pra
    atualizar (rowcount 0) e sai sem gerar o relatório 2x. Também pode
    esbarrar no índice único parcial (db/session.py, ver
    atualizar_apos_triagem) se outro arquivo diferente já estiver
    "processando" esse mesmo número — vira DUPLICADO_EM_ANDAMENTO em vez
    de estourar erro."""
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
            # Não retorna o registro pro chamador (core/pipeline_manual.py)
            # seguir gerando — ele só olha "veio algo?", não o status. Igual
            # ao rowcount==0 logo abaixo: devolve None, quem chamou já sabe
            # não seguir pra geração nesse caso.
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
    """{"pendentes": [...], "processando": [...]} — todos os registros
    ativos do próprio usuário. Henrique, 2026-08-12: uma inconsistência
    (trava a triagem, espera Conferências) NÃO some de Pendentes — ela
    continua lá, com bolinha vermelha, exatamente como a Fila do Robô já
    faz (ver web/routes/fila.py::_estado_atual_fila). Só sai de Pendentes
    quando é resolvida de verdade (Aprovar move pra "processando";
    Descartar apaga a linha). Concluído/erro entram em "processando"
    (o front mostra o badge final antes de dispensar)."""
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
    """Registros de erro do PRÓPRIO usuário no fluxo manual — alimenta a
    aba "Minhas" do sininho (Henrique, 2026-08-13). Fica visível enquanto
    o registro existir — some sozinho quando a pessoa dispensa com o "×"
    já existente na tela de Gerar Relatório URGENTE (descartar), nunca por
    uma notificação "lida"."""
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
    """Quantas Conferências do PRÓPRIO usuário estão pendentes AGORA, sem
    filtro de tempo — alimenta o badge "+N" da aba "Gerar Relatório URGENTE".
    Henrique, 2026-08-13: "não pode sumir só de entrar [na aba],
    permanece até alguém aprovar ou negar" — diferente de
    contar_inconsistencias_novas_do_usuario (abaixo), que zera ao visitar
    a aba (pensada originalmente pra esse badge, mas o comportamento
    certo pra Conferência é ficar ligado até resolver de verdade, igual
    já vale pro sininho de notificações)."""
    with obter_sessao() as sessao:
        consulta = select(func.count()).select_from(TriagemManual).where(
            TriagemManual.usuario_id == usuario_id,
            TriagemManual.status.in_(STATUS_INCONSISTENCIA),
        )
        return sessao.exec(consulta).one()


def contar_inconsistencias_novas_do_usuario(usuario_id, desde):
    """Quantas Conferências do PRÓPRIO usuário (inconsistência esperando
    decisão em "Gerar Relatório URGENTE") surgiram desde `desde` — alimenta o
    badge "+N" (cor de revisão, único número dessa aba) em rotulos.py.
    `atualizado_em`, não `criado_em`: é o instante em que o registro virou
    uma inconsistência de verdade (a triagem já rodou), não quando o
    arquivo foi só recebido — enquanto uma inconsistência continua aberta
    ela nunca é reescrita de novo, então essa data não se move sozinha."""
    with obter_sessao() as sessao:
        consulta = select(func.count()).select_from(TriagemManual).where(
            TriagemManual.usuario_id == usuario_id,
            TriagemManual.status.in_(STATUS_INCONSISTENCIA),
            TriagemManual.atualizado_em > desde,
        )
        return sessao.exec(consulta).one()
