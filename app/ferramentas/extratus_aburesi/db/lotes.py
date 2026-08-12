from datetime import datetime

from sqlmodel import select

from app.ferramentas.extratus_aburesi.db.models import ItemLoteMotor, LoteMotor
from app.plataforma.db.session import obter_sessao


def criar_lote(batch_id, itens):
    """Registra um novo lote enviado ao Batch API, com um `ItemLoteMotor`
    por PDF incluído nele. `itens` é uma lista de dicts com custom_id,
    arquivo_pdf, processo_detectado, confianca_nivel, confianca_motivo.
    """
    with obter_sessao() as sessao:
        lote = LoteMotor(batch_id=batch_id, status="enviado")
        sessao.add(lote)
        sessao.commit()
        sessao.refresh(lote)

        for item in itens:
            sessao.add(
                ItemLoteMotor(
                    lote_id=lote.id,
                    custom_id=item["custom_id"],
                    arquivo_pdf=item["arquivo_pdf"],
                    processo_detectado=item.get("processo_detectado"),
                    confianca_nivel=item.get("confianca_nivel"),
                    confianca_motivo=item.get("confianca_motivo"),
                )
            )

        sessao.commit()
        sessao.refresh(lote)

        return lote


def listar_lotes_em_andamento():
    with obter_sessao() as sessao:
        consulta = select(LoteMotor).where(LoteMotor.status == "enviado")
        return sessao.exec(consulta).all()


def listar_itens_do_lote(lote_id):
    with obter_sessao() as sessao:
        consulta = select(ItemLoteMotor).where(ItemLoteMotor.lote_id == lote_id)
        return sessao.exec(consulta).all()


def listar_arquivos_ja_reivindicados():
    """Ver docstring equivalente em app/ferramentas/extratus/db/lotes.py
    (Extratus - Relatórios) — mesmo bug real, mesma correção (Henrique,
    2026-08-11): só lote "enviado" (em voo) reivindica um nome; lote já
    concluído libera o nome de novo, senão um arquivo novo com o mesmo
    nome de um já processado fica preso pra sempre como "processando"."""
    with obter_sessao() as sessao:
        consulta = (
            select(ItemLoteMotor.arquivo_pdf)
            .join(LoteMotor, LoteMotor.id == ItemLoteMotor.lote_id)
            .where(LoteMotor.status == "enviado")
        )
        return set(sessao.exec(consulta).all())


def marcar_item_concluido(item_id, status):
    with obter_sessao() as sessao:
        item = sessao.get(ItemLoteMotor, item_id)

        if item:
            item.status = status
            sessao.add(item)
            sessao.commit()


def marcar_lote_concluido(lote_id):
    with obter_sessao() as sessao:
        lote = sessao.get(LoteMotor, lote_id)

        if lote:
            lote.status = "concluido"
            lote.finalizado_em = datetime.now()
            sessao.add(lote)
            sessao.commit()
