from datetime import datetime

from sqlmodel import select

from app.ferramentas.extratus.db.models import ItemLoteRobo, LoteRobo
from app.plataforma.db.session import obter_sessao


def criar_lote(batch_id, itens):
    """Registra um novo lote enviado ao Batch API, com um `ItemLoteRobo`
    por PDF incluído nele. `itens` é uma lista de dicts com custom_id,
    arquivo_pdf, processo_detectado, confianca_nivel, confianca_motivo,
    custo_transcricao_usd (opcional, ver ItemLoteRobo em db/models.py).
    """
    with obter_sessao() as sessao:
        lote = LoteRobo(batch_id=batch_id, status="enviado")
        sessao.add(lote)
        sessao.commit()
        sessao.refresh(lote)

        for item in itens:
            sessao.add(
                ItemLoteRobo(
                    lote_id=lote.id,
                    custom_id=item["custom_id"],
                    arquivo_pdf=item["arquivo_pdf"],
                    processo_detectado=item.get("processo_detectado"),
                    confianca_nivel=item.get("confianca_nivel"),
                    confianca_motivo=item.get("confianca_motivo"),
                    custo_transcricao_usd=item.get("custo_transcricao_usd") or 0.0,
                )
            )

        sessao.commit()
        sessao.refresh(lote)

        return lote


def listar_lotes_em_andamento():
    with obter_sessao() as sessao:
        consulta = select(LoteRobo).where(LoteRobo.status == "enviado")
        return sessao.exec(consulta).all()


def obter_estatisticas_lotes():
    """Resumo rápido pra tela de Configurações (admin) — total de lotes já
    concluídos e quando foi o último, sem precisar abrir Relatórios do
    Robô pra ter essa noção. `None` em ultimo_concluido_em quando o Robô
    nunca terminou um lote ainda (site novo, ou nunca foi ligado)."""
    with obter_sessao() as sessao:
        total_concluidos = sessao.exec(
            select(LoteRobo).where(LoteRobo.status == "concluido")
        ).all()

        ultimo_concluido_em = max(
            (lote.finalizado_em for lote in total_concluidos if lote.finalizado_em),
            default=None,
        )

        return {
            "total_concluidos": len(total_concluidos),
            "ultimo_concluido_em": ultimo_concluido_em,
        }


def listar_itens_do_lote(lote_id):
    with obter_sessao() as sessao:
        consulta = select(ItemLoteRobo).where(ItemLoteRobo.lote_id == lote_id)
        return sessao.exec(consulta).all()


def listar_arquivos_ja_reivindicados():
    """Nomes de arquivo com um `ItemLoteRobo` num lote AINDA em andamento
    (`LoteRobo.status == "enviado"`) — evita reenviar o mesmo PDF pra um
    lote novo enquanto ele ainda está em voo.

    Lote já concluído NÃO conta (bug real, Henrique 2026-08-11: "tem uns
    documentos... está lá a dias processando"). Antes, esta função
    devolvia TODO nome que já apareceu em QUALQUER lote, mesmo concluído
    há dias — um PDF processado com sucesso é removido de
    `robo_pasta_entrada` (`finalizar_processamento`), mas se um arquivo
    NOVO reaparecer depois com o MESMO NOME (reenvio, teste, um caso
    novo com nome genérico igual), ele ficava "reivindicado" pra sempre
    por um lote que não tem nada a ver com ele — nunca mais entrava em
    checagem nem em lote nenhum, preso como "processando" na tela pra
    sempre. Só o lote "enviado" (em voo de verdade) precisa bloquear um
    reenvio; um lote "concluído" já liberou seu arquivo fisicamente, o
    nome deveria estar livre de novo (se for duplicata de um processo já
    processado, `existe_relatorio_gerado_para_processo` pega isso na
    checagem, de forma visível — Conferências — não silenciosa)."""
    with obter_sessao() as sessao:
        consulta = (
            select(ItemLoteRobo.arquivo_pdf)
            .join(LoteRobo, LoteRobo.id == ItemLoteRobo.lote_id)
            .where(LoteRobo.status == "enviado")
        )
        return set(sessao.exec(consulta).all())


def marcar_item_concluido(item_id, status):
    with obter_sessao() as sessao:
        item = sessao.get(ItemLoteRobo, item_id)

        if item:
            item.status = status
            sessao.add(item)
            sessao.commit()


def marcar_lote_concluido(lote_id):
    with obter_sessao() as sessao:
        lote = sessao.get(LoteRobo, lote_id)

        if lote:
            lote.status = "concluido"
            lote.finalizado_em = datetime.now()
            sessao.add(lote)
            sessao.commit()
