import pytest
from sqlmodel import delete, select

from app.plataforma.db import seed
from app.plataforma.db.models import Ferramenta
from app.plataforma.db.session import obter_sessao


SLUG_TESTE = "teste-seed-sync"


@pytest.fixture
def limpar_ferramenta_teste():
    yield
    with obter_sessao() as sessao:
        sessao.exec(delete(Ferramenta).where(Ferramenta.slug == SLUG_TESTE))
        sessao.commit()


def _buscar(slug):
    with obter_sessao() as sessao:
        return sessao.exec(select(Ferramenta).where(Ferramenta.slug == slug)).first()


def test_garantir_ferramentas_padrao_cria_extratus_aburesi():
    # Chamado explicitamente (não confia em import de outro módulo de
    # teste já ter rodado o seed) — idempotente, seguro de repetir.
    seed.garantir_ferramentas_padrao()

    ferramenta = _buscar("extratus-aburesi")

    assert ferramenta is not None
    assert ferramenta.nome == "Extratus - Aburesi"
    assert ferramenta.url == "/extratus-aburesi/fila-robo"
    assert ferramenta.suporta_fila_robo is True


def test_garantir_ferramentas_padrao_renomeou_extratus_relatorios():
    seed.garantir_ferramentas_padrao()

    ferramenta = _buscar("extratus")

    assert ferramenta is not None
    assert ferramenta.nome == "Extratus - Relatórios"
    assert ferramenta.url == "/extratus/fila-robo"  # slug nunca muda; url segue a 1a aba
    assert ferramenta.suporta_fila_robo is True


def test_leitor_publicacoes_nao_suporta_fila_robo():
    seed.garantir_ferramentas_padrao()

    ferramenta = _buscar("leitor-publicacoes")

    assert ferramenta is not None
    assert ferramenta.suporta_fila_robo is False


def test_garantir_ferramentas_padrao_sincroniza_nome_de_ferramenta_existente(
    monkeypatch, limpar_ferramenta_teste
):
    lista_original = seed.FERRAMENTAS_PADRAO

    monkeypatch.setattr(
        seed,
        "FERRAMENTAS_PADRAO",
        lista_original + [{
            "nome": "Nome Original",
            "slug": SLUG_TESTE,
            "descricao": "descricao original",
            "url": "/teste-seed-sync/",
            "suporta_fila_robo": False,
        }],
    )
    seed.garantir_ferramentas_padrao()
    assert _buscar(SLUG_TESTE).nome == "Nome Original"

    monkeypatch.setattr(
        seed,
        "FERRAMENTAS_PADRAO",
        lista_original + [{
            "nome": "Nome Atualizado",
            "slug": SLUG_TESTE,
            "descricao": "descricao atualizada",
            "url": "/teste-seed-sync/",
            "suporta_fila_robo": False,
        }],
    )
    seed.garantir_ferramentas_padrao()

    atualizada = _buscar(SLUG_TESTE)
    assert atualizada.nome == "Nome Atualizado"
    assert atualizada.descricao == "descricao atualizada"
