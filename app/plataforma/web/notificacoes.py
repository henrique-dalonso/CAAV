from app.ferramentas.extratus.web.notificacoes import listar_notificacoes as listar_notificacoes_extratus
from app.ferramentas.extratus_aburesi.web.notificacoes import (
    listar_notificacoes as listar_notificacoes_extratus_aburesi,
)
from app.plataforma.db.usuarios import usuario_tem_acesso_fila_motor


# Um registro simples (slug + nome de exibição da ferramenta -> função
# que lista as pendências dela) em vez de alguma abstração de plugin —
# mesmo padrão já usado em main.py pros watchers do Motor/checagem, cada
# ferramenta nova entra aqui na mão. Só ferramentas com Fila do Motor
# (triagem + erros do Motor) têm notificação hoje — quem não tiver
# simplesmente nunca aparece pra ninguém. Nome de exibição repetido aqui
# (em vez de consultar Ferramenta no banco a cada notificação) porque o
# registro já é mantido à mão mesmo — mesmos nomes de `seed.py`.
REGISTRO_NOTIFICACOES = [
    ("extratus", "Extratus - Relatórios", listar_notificacoes_extratus),
    ("extratus-aburesi", "Extratus - Aburesi", listar_notificacoes_extratus_aburesi),
]


def notificacoes_do_usuario(usuario):
    """Notificações de todas as ferramentas que esse usuário tem acesso
    à Fila do Motor — mesma permissão que já libera a aba Fila hoje
    (usuario_tem_acesso_fila_motor), sem regra nova. Um colaborador sem
    acesso à Fila de uma ferramenta nunca vê as pendências dela aqui.

    Cada item ganha "ferramenta" (nome de exibição) aqui, não em cada
    módulo — Henrique pediu (2026-08-06/07) que toda notificação deixe
    claro de qual ferramenta ela veio, pensando em quando existirem
    muitas ferramentas e as notificações começarem a se misturar."""
    notificacoes = []

    for slug, nome_ferramenta, listar in REGISTRO_NOTIFICACOES:
        if usuario_tem_acesso_fila_motor(usuario, slug):
            for item in listar():
                notificacoes.append({**item, "ferramenta": nome_ferramenta})

    return notificacoes
