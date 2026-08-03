from sqlmodel import select

from app.plataforma.db.models import Ferramenta
from app.plataforma.db.session import obter_sessao


FERRAMENTAS_PADRAO = [
    {
        # slug/url NUNCA mudam — permissões e favoritos de usuários já
        # existentes estão amarrados a "extratus". Só nome/descrição são
        # livres pra ajustar (ver garantir_ferramentas_padrao abaixo).
        "nome": "Extratus - Relatórios",
        "slug": "extratus",
        "descricao": "Produção de relatório completo de processo judicial para o cliente, com parecer.",
        "url": "/extratus/",
        "suporta_fila_motor": True,
    },
    {
        "nome": "Extratus - Aburesi",
        "slug": "extratus-aburesi",
        "descricao": "Resumo rápido de processo judicial para uso interno no atendimento do cliente Aburesi.",
        "url": "/extratus-aburesi/",
        "suporta_fila_motor": True,
    },
    {
        "nome": "Leitor de Publicações",
        "slug": "leitor-publicacoes",
        "descricao": "Pré-análise por IA de publicações, com sugestão de agendamento para revisão do advogado.",
        "url": "/leitor-publicacoes/",
        "suporta_fila_motor": False,
    },
]


def garantir_ferramentas_padrao():
    """Garante que as ferramentas do sistema existam na tabela Ferramenta,
    e mantém nome/descrição/url sincronizados com FERRAMENTAS_PADRAO pra
    quem já existe (ex: renomear "Extratus" pra "Extratus - Relatórios"
    precisa aparecer sozinho, sem exigir um ajuste manual no banco).

    Idempotente — pode ser chamado toda vez que o app inicia sem duplicar nada.
    """
    with obter_sessao() as sessao:
        for dados in FERRAMENTAS_PADRAO:
            existente = sessao.exec(
                select(Ferramenta).where(Ferramenta.slug == dados["slug"])
            ).first()

            if not existente:
                sessao.add(Ferramenta(**dados))
                continue

            for campo in ("nome", "descricao", "url", "suporta_fila_motor"):
                setattr(existente, campo, dados[campo])

            sessao.add(existente)

        sessao.commit()
