import pytest
from sqlmodel import delete

from app.ferramentas.extratus.db.checagem_fila import (
    APROVADO,
    DUPLICADO_RELATORIO,
    PENDENTE,
)
from app.ferramentas.extratus.db.jobs import registrar_erro
from app.ferramentas.extratus.db.models import ChecagemFila, Job
from app.ferramentas.extratus.web.notificacoes import listar_notificacoes
from app.plataforma.db.session import obter_sessao


PREFIXO_TESTE = "teste_notif_"


@pytest.fixture
def limpar_notificacoes_teste():
    yield
    with obter_sessao() as sessao:
        sessao.exec(delete(ChecagemFila).where(ChecagemFila.nome_arquivo.like(f"{PREFIXO_TESTE}%")))
        sessao.exec(delete(Job).where(Job.arquivo_pdf.like(f"{PREFIXO_TESTE}%")))
        sessao.commit()


def _criar_checagem(nome, status):
    with obter_sessao() as sessao:
        sessao.add(ChecagemFila(nome_arquivo=nome, status=status))
        sessao.commit()


def test_inconsistencia_de_triagem_vira_notificacao(limpar_notificacoes_teste):
    nome = f"{PREFIXO_TESTE}duplicado.pdf"
    _criar_checagem(nome, DUPLICADO_RELATORIO)

    itens = listar_notificacoes()
    achado = next((i for i in itens if nome in i["mensagem"]), None)

    assert achado is not None
    assert achado["tipo"] == "triagem"
    assert achado["link"] == "/extratus/fila"


def test_status_aprovado_e_pendente_nao_viram_notificacao(limpar_notificacoes_teste):
    nome_aprovado = f"{PREFIXO_TESTE}aprovado.pdf"
    nome_pendente = f"{PREFIXO_TESTE}pendente.pdf"
    _criar_checagem(nome_aprovado, APROVADO)
    _criar_checagem(nome_pendente, PENDENTE)

    itens = listar_notificacoes()
    mensagens = " ".join(i["mensagem"] for i in itens)

    assert nome_aprovado not in mensagens
    assert nome_pendente not in mensagens


def test_erro_do_motor_vira_notificacao(limpar_notificacoes_teste):
    nome = f"{PREFIXO_TESTE}erro_motor.pdf"
    registrar_erro(nome, None, "erro_pdf", "PDF corrompido", usuario_id=None)

    itens = listar_notificacoes()
    achado = next((i for i in itens if nome in i["mensagem"]), None)

    assert achado is not None
    assert achado["tipo"] == "erro"
    assert achado["link"] == "/extratus/erros"


def test_erro_do_fluxo_manual_nao_vira_notificacao(limpar_notificacoes_teste):
    """usuario_id preenchido = fluxo síncrono manual — a pessoa já viu o
    erro na hora, não precisa do sininho pra descobrir."""
    nome = f"{PREFIXO_TESTE}erro_manual.pdf"
    registrar_erro(nome, None, "erro_pdf", "PDF corrompido", usuario_id=1)

    itens = listar_notificacoes()

    assert not any(nome in i["mensagem"] for i in itens)


def test_erro_marcado_resolvido_nao_vira_notificacao(limpar_notificacoes_teste):
    nome = f"{PREFIXO_TESTE}erro_resolvido.pdf"
    job = registrar_erro(nome, None, "erro_pdf", "PDF corrompido", usuario_id=None)

    with obter_sessao() as sessao:
        registro = sessao.get(Job, job.id)
        registro.notificacao_resolvida = True
        sessao.add(registro)
        sessao.commit()

    itens = listar_notificacoes()

    assert not any(nome in i["mensagem"] for i in itens)
