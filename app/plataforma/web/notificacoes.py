from app.ferramentas.extratus.web.notificacoes import (
    listar_notificacoes as listar_notificacoes_extratus,
    listar_notificacoes_pessoais as listar_notificacoes_pessoais_extratus,
)
from app.ferramentas.extratus_aburesi.web.notificacoes import (
    listar_notificacoes as listar_notificacoes_extratus_aburesi,
    listar_notificacoes_pessoais as listar_notificacoes_pessoais_extratus_aburesi,
)
from app.plataforma.db.usuarios import usuario_tem_acesso, usuario_tem_acesso_fila_motor


# Um registro simples (slug + nome de exibição da ferramenta -> funções
# que listam as pendências dela) em vez de alguma abstração de plugin —
# mesmo padrão já usado em main.py pros watchers do Motor/checagem, cada
# ferramenta nova entra aqui na mão. Nome de exibição repetido aqui (em
# vez de consultar Ferramenta no banco a cada notificação) porque o
# registro já é mantido à mão mesmo — mesmos nomes de `seed.py`.
REGISTRO_NOTIFICACOES = [
    ("extratus", "Extratus - Relatórios", listar_notificacoes_extratus, listar_notificacoes_pessoais_extratus),
    ("extratus-aburesi", "Extratus - Aburesi", listar_notificacoes_extratus_aburesi, listar_notificacoes_pessoais_extratus_aburesi),
]


def notificacoes_do_usuario(usuario):
    """Notificações de todas as ferramentas do usuário, de 2 famílias
    com permissões diferentes (Henrique, 2026-08-13):
    - Fila do Motor (abas "Sistema"/"Conferências" no sino) — só pra
      quem tem acesso à Fila do Motor daquela ferramenta
      (usuario_tem_acesso_fila_motor), como já era.
    - Pessoais do fluxo manual (aba "Minhas") — pra qualquer um com
      acesso à ferramenta em si, sem depender de Fila do Motor: "a aba
      minha é justamente pra abrigar os alertas do modo manual, que
      fazem jus às pessoas, tambem, que nao tem acesso às outras abas."

    Cada item ganha "ferramenta" (nome de exibição) aqui, não em cada
    módulo — Henrique pediu (2026-08-06/07) que toda notificação deixe
    claro de qual ferramenta ela veio, pensando em quando existirem
    muitas ferramentas e as notificações começarem a se misturar."""
    notificacoes = []

    for slug, nome_ferramenta, listar, listar_pessoais in REGISTRO_NOTIFICACOES:
        if usuario_tem_acesso_fila_motor(usuario, slug):
            for item in listar():
                notificacoes.append({**item, "ferramenta": nome_ferramenta})

        if usuario_tem_acesso(usuario, slug):
            for item in listar_pessoais(usuario.id):
                notificacoes.append({**item, "ferramenta": nome_ferramenta})

    return notificacoes
