from sqlmodel import select

from app.plataforma.db.models import Ferramenta
from app.plataforma.db.session import obter_sessao


FERRAMENTAS_PADRAO = [
    {
        "nome": "Extratus",
        "slug": "extratus",
        "descricao": "Resumo automático de processos judiciais em relatório curto com parecer.",
        "url": "/extratus/",
    },
    {
        "nome": "Leitor de Publicações",
        "slug": "leitor-publicacoes",
        "descricao": "Pré-análise por IA de publicações, com sugestão de agendamento para revisão do advogado.",
        "url": "/leitor-publicacoes/",
    },
]


def garantir_ferramentas_padrao():
    """Garante que as ferramentas do sistema existam na tabela Ferramenta.

    Idempotente — pode ser chamado toda vez que o app inicia sem duplicar nada.
    """
    with obter_sessao() as sessao:
        for dados in FERRAMENTAS_PADRAO:
            existente = sessao.exec(
                select(Ferramenta).where(Ferramenta.slug == dados["slug"])
            ).first()

            if not existente:
                sessao.add(Ferramenta(**dados))

        sessao.commit()
