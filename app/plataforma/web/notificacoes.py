from app.ferramentas.extratus.web.notificacoes import (
    listar_notificacoes as listar_notificacoes_extratus,
    listar_notificacoes_pessoais as listar_notificacoes_pessoais_extratus,
)
from app.ferramentas.extratus_aburesi.web.notificacoes import (
    listar_notificacoes as listar_notificacoes_extratus_aburesi,
    listar_notificacoes_pessoais as listar_notificacoes_pessoais_extratus_aburesi,
)
from app.plataforma.db.usuarios import usuario_tem_acesso


# Um registro simples (slug + nome de exibição da ferramenta -> funções
# que listam as pendências dela) em vez de alguma abstração de plugin —
# mesmo padrão já usado em main.py pros watchers do Robô/checagem, cada
# ferramenta nova entra aqui na mão. Nome de exibição repetido aqui (em
# vez de consultar Ferramenta no banco a cada notificação) porque o
# registro já é mantido à mão mesmo — mesmos nomes de `seed.py`.
REGISTRO_NOTIFICACOES = [
    ("extratus", "Extratus - Relatórios", listar_notificacoes_extratus, listar_notificacoes_pessoais_extratus),
    ("extratus-aburesi", "Extratus - Aburesi", listar_notificacoes_extratus_aburesi, listar_notificacoes_pessoais_extratus_aburesi),
]


def _com_ponto_final(mensagem):
    """Cada módulo monta sua própria mensagem (dict fixo ou f-string) sem
    se preocupar com pontuação final — normaliza aqui, no único lugar por
    onde toda notificação passa antes de chegar no sino, em vez de mexer
    string por string em cada módulo."""
    if mensagem and mensagem[-1] not in ".!?":
        return mensagem + "."
    return mensagem


def notificacoes_do_usuario(usuario):
    """Notificações de todas as ferramentas do usuário, de 2 famílias
    (Henrique, 2026-08-13; ajustado 2026-08-19 quando Fila do Robô
    virou acesso padrão):
    - Fila do Robô (aba "Ferramentas" no sino) — pra qualquer um com
      acesso à ferramenta, já que a Fila do Robô não exige mais uma flag
      própria. Henrique, 2026-09-02: quem PEDIU o relatório (Job.
      solicitante_id) não entra mais aqui, só em "Minhas" — por isso
      `listar` agora recebe usuario.id também.
    - Pessoais do fluxo manual (aba "Minhas") — pra qualquer um com
      acesso à ferramenta em si, sem depender de acesso_manual: "a aba
      minha é justamente pra abrigar os alertas do modo manual, que
      fazem jus às pessoas, tambem, que nao tem acesso às outras abas."
      Na prática fica vazia pra quem não tem acesso_manual, já que essa
      pessoa nunca gera nada no fluxo manual pra ter notificação sobre.

    Cada item ganha "ferramenta" (nome de exibição) aqui, não em cada
    módulo — Henrique pediu (2026-08-06/07) que toda notificação deixe
    claro de qual ferramenta ela veio, pensando em quando existirem
    muitas ferramentas e as notificações começarem a se misturar."""
    notificacoes = []

    for slug, nome_ferramenta, listar, listar_pessoais in REGISTRO_NOTIFICACOES:
        if not usuario_tem_acesso(usuario, slug):
            continue

        for item in listar(usuario.id):
            notificacoes.append({**item, "mensagem": _com_ponto_final(item["mensagem"]), "ferramenta": nome_ferramenta})

        for item in listar_pessoais(usuario.id):
            notificacoes.append({**item, "mensagem": _com_ponto_final(item["mensagem"]), "ferramenta": nome_ferramenta})

    return notificacoes
