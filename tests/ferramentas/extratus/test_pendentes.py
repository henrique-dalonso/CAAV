import pytest
from sqlmodel import delete

from app.ferramentas.extratus.db.models import ArquivoPendente
from app.ferramentas.extratus.db.pendentes import (
    listar_nomes_pendentes_do_usuario,
    registrar_pendente,
    remover_pendente,
)
from app.plataforma.db.session import obter_sessao


# IDs negativos de propósito — não colidem com usuário real (autoincremento
# a partir de 1), mesmo padrão de tests/ferramentas/extratus/test_jobs.py.
USUARIO_TESTE_A = -9101
USUARIO_TESTE_B = -9102


@pytest.fixture
def limpar_pendentes_teste():
    yield
    with obter_sessao() as sessao:
        sessao.exec(
            delete(ArquivoPendente).where(
                ArquivoPendente.usuario_id.in_([USUARIO_TESTE_A, USUARIO_TESTE_B])
            )
        )
        sessao.commit()


def test_usuario_so_ve_os_proprios_pendentes(limpar_pendentes_teste):
    registrar_pendente("processo_a.pdf", USUARIO_TESTE_A)
    registrar_pendente("processo_b.pdf", USUARIO_TESTE_B)

    assert listar_nomes_pendentes_do_usuario(USUARIO_TESTE_A) == {"processo_a.pdf"}
    assert listar_nomes_pendentes_do_usuario(USUARIO_TESTE_B) == {"processo_b.pdf"}


def test_remover_pendente_tira_so_do_dono(limpar_pendentes_teste):
    registrar_pendente("processo_a.pdf", USUARIO_TESTE_A)

    # usuário errado tentando remover não deve afetar o registro do dono.
    remover_pendente("processo_a.pdf", USUARIO_TESTE_B)
    assert listar_nomes_pendentes_do_usuario(USUARIO_TESTE_A) == {"processo_a.pdf"}

    remover_pendente("processo_a.pdf", USUARIO_TESTE_A)
    assert listar_nomes_pendentes_do_usuario(USUARIO_TESTE_A) == set()
