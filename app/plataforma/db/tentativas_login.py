from datetime import datetime, timedelta

from sqlmodel import delete, select

from app.plataforma.db.models import TentativaLoginFalha
from app.plataforma.db.session import obter_sessao

# Henrique, 2026-08-11: 5 nomes de usuário diferentes tentados pela mesma
# máquina/rede em 15 minutos bloqueia aquela rede por 15 minutos (nenhum
# login passa dali, nem com senha certa) — pensado pra pegar alguém
# varrendo várias contas, não um colega errando a própria senha (isso já
# é coberto por Usuario.bloqueado, a trava por usuário).
JANELA_MINUTOS = 15
LIMITE_CONTAS_DISTINTAS = 5


def registrar_tentativa_falha(ip, nome_usuario_tentado):
    limite_retencao = datetime.now() - timedelta(minutes=JANELA_MINUTOS)

    with obter_sessao() as sessao:
        # Só a janela dos últimos 15 minutos importa pra decisão de
        # bloqueio — poda tudo mais velho a cada novo registro, assim a
        # tabela nunca cresce sem limite (não tem outra rotina de limpeza).
        sessao.exec(delete(TentativaLoginFalha).where(TentativaLoginFalha.criado_em < limite_retencao))
        sessao.add(TentativaLoginFalha(ip=ip, nome_usuario_tentado=nome_usuario_tentado))
        sessao.commit()


def ip_esta_bloqueado(ip):
    limite = datetime.now() - timedelta(minutes=JANELA_MINUTOS)

    with obter_sessao() as sessao:
        nomes_tentados = sessao.exec(
            select(TentativaLoginFalha.nome_usuario_tentado).where(
                TentativaLoginFalha.ip == ip,
                TentativaLoginFalha.criado_em >= limite,
            )
        ).all()

    return len(set(nomes_tentados)) >= LIMITE_CONTAS_DISTINTAS
