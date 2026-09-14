"""Acesso a dados do Processamento em Lote — LoteCrivus e as
AnalisePublicacao (`origem="lote"`) que ele agrupa. Nomeação paralela a
`nucleo_relatorios/db/lotes.py`, mas pro model próprio do Crivus (ver
docstring de LoteCrivus em db/models.py)."""

from datetime import datetime

from sqlmodel import select

from app.ferramentas.crivus.db.analises import _preencher_analise_com_resultado_ia
from app.ferramentas.crivus.db.models import AnalisePublicacao, LoteCrivus
from app.plataforma.db.session import obter_sessao

# Henrique, 2026-09-14: 10 mil+ linhas de uma vez é trabalho real —
# commits em blocos em vez de 1 commit gigante no final, pra não segurar
# a transação/travar outras escritas no SQLite por tempo demais.
TAMANHO_BLOCO_INSERCAO = 500


def criar_lote(usuario_id, nome_arquivo, linhas):
    """`linhas` no formato de `lote_manager.ler_linhas_planilha` — cria o
    LoteCrivus e 1 AnalisePublicacao por linha, já com status
    "processando" (nasce assim, é o default do model) e origem="lote".
    `data_publicacao_original` alimenta a decisão de atraso em
    lote_batch.py; `data_importacao_original` é só guardada como
    registro do dado bruto (ignorada 100% nas decisões, ver docstring
    de lote_batch.py)."""
    with obter_sessao() as sessao:
        lote = LoteCrivus(criado_por=usuario_id, nome_arquivo=nome_arquivo, total_linhas=len(linhas))
        sessao.add(lote)
        sessao.commit()
        sessao.refresh(lote)

        for indice, linha in enumerate(linhas):
            sessao.add(AnalisePublicacao(
                usuario_id=usuario_id,
                origem="lote",
                lote_id=lote.id,
                teor_publicacao=linha["teor"],
                npjur=linha["npjur"],
                data_publicacao_original=linha["data_publicacao"],
                data_importacao_original=linha["data_importacao"],
            ))
            if (indice + 1) % TAMANHO_BLOCO_INSERCAO == 0:
                sessao.commit()

        sessao.commit()
        sessao.refresh(lote)
        return lote


def obter_lote(lote_id):
    with obter_sessao() as sessao:
        return sessao.get(LoteCrivus, lote_id)


def listar_lotes():
    with obter_sessao() as sessao:
        return sessao.exec(select(LoteCrivus).order_by(LoteCrivus.criado_em.desc())).all()


def listar_pendentes_de_despacho(lote_id=None):
    """A fila que o roteamento por atraso avalia a cada tick do robô —
    linhas de lote que ainda não foram nem marcadas como atrasadas, nem
    submetidas pra API de Lote da Anthropic."""
    with obter_sessao() as sessao:
        consulta = select(AnalisePublicacao).where(
            AnalisePublicacao.origem == "lote",
            AnalisePublicacao.status == "processando",
            AnalisePublicacao.batch_id.is_(None),
        )
        if lote_id is not None:
            consulta = consulta.where(AnalisePublicacao.lote_id == lote_id)
        return sessao.exec(consulta.order_by(AnalisePublicacao.criado_em.asc())).all()


def listar_batch_ids_em_andamento():
    with obter_sessao() as sessao:
        resultado = sessao.exec(
            select(AnalisePublicacao.batch_id).where(
                AnalisePublicacao.origem == "lote",
                AnalisePublicacao.status == "processando",
                AnalisePublicacao.batch_id.is_not(None),
            )
        ).all()
        return sorted(set(resultado))


def listar_analises_do_batch(batch_id):
    with obter_sessao() as sessao:
        return sessao.exec(
            select(AnalisePublicacao).where(AnalisePublicacao.batch_id == batch_id)
        ).all()


def marcar_batch_id(analise_ids, batch_id):
    with obter_sessao() as sessao:
        for analise_id in analise_ids:
            analise = sessao.get(AnalisePublicacao, analise_id)
            analise.batch_id = batch_id
            sessao.add(analise)
        sessao.commit()


def concluir_analise_de_lote(analise_id, dados_ia, uso_ia):
    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, analise_id)
        return _preencher_analise_com_resultado_ia(sessao, analise, dados_ia, uso_ia)


def marcar_analise_de_lote_com_erro(analise_id, mensagem):
    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, analise_id)
        analise.status = "erro"
        analise.erro_mensagem = mensagem
        sessao.add(analise)
        sessao.commit()
        sessao.refresh(analise)
        return analise


def marcar_analise_atrasada(analise_id, mensagem):
    """Henrique, coordenador, 2026-09-14: linha com 2+ dias de atraso
    (ver `eh_atrasado` em lote_batch.py) — excluída DE PROPÓSITO do
    processamento automático, nunca chega a chamar a IA. `mensagem` vira
    o MOTIVO na planilha de saída (ver gerar_planilha_saida)."""
    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, analise_id)
        analise.status = "atrasado"
        analise.erro_mensagem = mensagem
        sessao.add(analise)
        sessao.commit()
        sessao.refresh(analise)
        return analise


def lote_ainda_tem_linha_processando(lote_id):
    with obter_sessao() as sessao:
        return sessao.exec(
            select(AnalisePublicacao.id).where(
                AnalisePublicacao.lote_id == lote_id,
                AnalisePublicacao.status == "processando",
            )
        ).first() is not None


def marcar_lote_concluido(lote_id, caminho_planilha_saida):
    with obter_sessao() as sessao:
        lote = sessao.get(LoteCrivus, lote_id)

        contagens = sessao.exec(
            select(AnalisePublicacao.status).where(AnalisePublicacao.lote_id == lote_id)
        ).all()
        lote.linhas_sucesso = sum(1 for status in contagens if status not in ("erro", "atrasado"))
        lote.linhas_erro = sum(1 for status in contagens if status == "erro")
        lote.linhas_atrasadas = sum(1 for status in contagens if status == "atrasado")

        lote.status = "concluido"
        lote.finalizado_em = datetime.now()
        lote.caminho_planilha_saida = str(caminho_planilha_saida)
        sessao.add(lote)
        sessao.commit()
        sessao.refresh(lote)
        return lote
