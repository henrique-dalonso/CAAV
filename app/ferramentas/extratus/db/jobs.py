from sqlmodel import select

from app.ferramentas.extratus.db.models import Job
from app.plataforma.db.session import obter_sessao


def registrar_processado(
    arquivo_pdf,
    processo,
    relatorio_path,
    destino_pdf,
    confianca,
    motivo_confianca=None,
    uso_ia=None,
):
    """Registra um PDF que gerou relatório — status "sucesso" (confiança
    alta) ou "revisao" (confiança média/baixa, precisa de olho humano).

    `uso_ia`, se informado, é um dict com modelo/tokens_entrada/tokens_saida/
    custo_estimado_usd — vem vazio quando o relatório ainda é simulado.
    """
    status = "sucesso" if str(confianca).strip().lower() == "alta" else "revisao"
    uso_ia = uso_ia or {}

    with obter_sessao() as sessao:
        job = Job(
            arquivo_pdf=str(arquivo_pdf),
            processo=processo,
            status=status,
            confianca=confianca,
            motivo_confianca=motivo_confianca,
            relatorio_path=str(relatorio_path) if relatorio_path else None,
            destino_pdf=str(destino_pdf) if destino_pdf else None,
            modelo_ia=uso_ia.get("modelo"),
            tokens_entrada=uso_ia.get("tokens_entrada"),
            tokens_saida=uso_ia.get("tokens_saida"),
            custo_estimado_usd=uso_ia.get("custo_estimado_usd"),
        )

        sessao.add(job)
        sessao.commit()
        sessao.refresh(job)

        return job


def registrar_erro(arquivo_pdf, processo, tipo_erro, erro_mensagem, destino_pdf=None):
    with obter_sessao() as sessao:
        job = Job(
            arquivo_pdf=str(arquivo_pdf),
            processo=processo,
            status="erro",
            tipo_erro=tipo_erro,
            erro_mensagem=str(erro_mensagem),
            destino_pdf=str(destino_pdf) if destino_pdf else None,
        )

        sessao.add(job)
        sessao.commit()
        sessao.refresh(job)

        return job


def listar_jobs(limite=100):
    with obter_sessao() as sessao:
        consulta = (
            select(Job)
            .order_by(Job.criado_em.desc())
            .limit(limite)
        )

        return sessao.exec(consulta).all()


def contar_por_status():
    contagem = {"sucesso": 0, "revisao": 0, "erro": 0}

    with obter_sessao() as sessao:
        for job in sessao.exec(select(Job)).all():
            contagem[job.status] = contagem.get(job.status, 0) + 1

    return contagem
