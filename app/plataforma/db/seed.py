from sqlmodel import select

from app.plataforma.db.models import Ferramenta
from app.plataforma.db.session import obter_sessao


# Cores None = usa o azul padrão da plataforma (ver fallback em
# base.css), não precisa repetir o valor aqui pra isso acontecer.
_SEM_COR_PROPRIA = {
    "cor_acento": None,
    "cor_acento_hover": None,
    "cor_acento_fraco": None,
    "cor_acento_escuro": None,
    "cor_acento_hover_escuro": None,
    "cor_acento_fraco_escuro": None,
}

FERRAMENTAS_PADRAO = [
    {
        # slug NUNCA muda — permissões e favoritos de usuários já
        # existentes estão amarrados a "extratus". nome/descrição/url são
        # livres pra ajustar (ver garantir_ferramentas_padrao abaixo);
        # nenhum dos dois é lido por permissão/favorito (esses usam
        # slug/ferramenta_id), url é só o link de entrada do ícone.
        "nome": "Extratus - Relatórios",
        "slug": "extratus",
        "descricao": "Produção de relatório completo de processo judicial para o cliente, com parecer.",
        # Henrique, 2026-08-20: clicar no ícone deve levar direto pra
        # primeira aba na ordem de navegação (Fila do Robô — ver
        # nav_abas_extratus em _macros_extratus.html), não pra "Gerar
        # Relatório URGENTE" (2026-09-02: renomeada de raiz "/extratus/"
        # pra "/extratus/fila-urgentes" na sanitização de URLs).
        "url": "/extratus/fila-robo",
        "suporta_fila_robo": True,
        **_SEM_COR_PROPRIA,
    },
    {
        "nome": "Extratus - Aburesi",
        "slug": "extratus-aburesi",
        "descricao": "Resumo rápido de processo judicial para uso interno no atendimento do cliente Aburesi.",
        "url": "/extratus-aburesi/fila-robo",
        "suporta_fila_robo": True,
        # Copiado 1:1 do :root que existia em
        # extratus_aburesi/web/static/extratus.css antes de virar campo
        # de banco — a cor em si não mudou, só de onde ela vem agora.
        "cor_acento": "#0d9488",
        "cor_acento_hover": "#0f766e",
        "cor_acento_fraco": "#f0fdfa",
        "cor_acento_escuro": "#2dd4bf",
        "cor_acento_hover_escuro": "#5eead4",
        "cor_acento_fraco_escuro": "#134e4a",
    },
    {
        "nome": "Crivus",
        # slug NUNCA muda (mesma regra do "extratus" acima) — mesmo com o
        # nome comercial batizado como "Crivus" (2026-09-02), o
        # identificador técnico continua "leitor-publicacoes" pra não
        # romper permissão/favorito de quem já tiver acesso concedido.
        "slug": "leitor-publicacoes",
        "descricao": "Pré-análise por IA de publicações, com sugestão de agendamento para revisão do advogado.",
        "url": "/crivus/",
        "suporta_fila_robo": False,
        **_SEM_COR_PROPRIA,
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

            for campo in (
                "nome", "descricao", "url", "suporta_fila_robo",
                "cor_acento", "cor_acento_hover", "cor_acento_fraco",
                "cor_acento_escuro", "cor_acento_hover_escuro", "cor_acento_fraco_escuro",
            ):
                # .get (não dados[campo]): as cores são opcionais — um
                # dict de ferramenta sem nenhuma delas (ex: em testes, ou
                # uma ferramenta futura sem identidade própria ainda)
                # simplesmente cai em None, sem precisar repetir
                # _SEM_COR_PROPRIA em todo lugar que monta esse dict.
                setattr(existente, campo, dados.get(campo))

            sessao.add(existente)

        sessao.commit()
