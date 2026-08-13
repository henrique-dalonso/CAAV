import pytest
from sqlmodel import delete

from app.ferramentas.extratus.db.checagem_fila import (
    APROVADO,
    DUPLICADO_RELATORIO,
    PENDENTE,
)
from app.ferramentas.extratus.db.jobs import marcar_notificacao_resolvida, registrar_erro, registrar_processado
from app.ferramentas.extratus.db.models import ChecagemFila, Job, TriagemManual
from app.ferramentas.extratus.db.triagem_manual import NAO_ENCONTRADO, atualizar_apos_triagem, criar_registro, marcar_erro
from app.ferramentas.extratus.web.notificacoes import listar_notificacoes, listar_notificacoes_pessoais
from app.plataforma.db.session import obter_sessao


PREFIXO_TESTE = "teste_notif_"

# Ver comentário equivalente em tests/ferramentas/extratus/test_jobs.py —
# ID negativo de propósito, não colide com usuário real.
USUARIO_TESTE = -9004


@pytest.fixture
def limpar_notificacoes_teste():
    yield
    with obter_sessao() as sessao:
        sessao.exec(delete(ChecagemFila).where(ChecagemFila.nome_arquivo.like(f"{PREFIXO_TESTE}%")))
        sessao.exec(delete(Job).where(Job.arquivo_pdf.like(f"{PREFIXO_TESTE}%")))
        sessao.exec(delete(TriagemManual).where(TriagemManual.nome_arquivo.like(f"{PREFIXO_TESTE}%")))
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


def test_conferencia_pendente_do_usuario_vira_notificacao_pessoal(limpar_notificacoes_teste):
    nome = f"{PREFIXO_TESTE}minhas_conferencia.pdf"
    registro = criar_registro(nome, f"/tmp/{nome}", USUARIO_TESTE)
    atualizar_apos_triagem(registro.id, NAO_ENCONTRADO, None, "revisao", "não achou nada")

    itens = listar_notificacoes_pessoais(USUARIO_TESTE)
    achado = next((i for i in itens if nome in i["mensagem"]), None)

    assert achado is not None
    assert achado["tipo"] == "conferencia_manual"
    assert achado["pessoal"] is True
    assert achado["descartavel"] is False


def test_erro_manual_do_usuario_vira_notificacao_pessoal(limpar_notificacoes_teste):
    nome = f"{PREFIXO_TESTE}minhas_erro.pdf"
    registro = criar_registro(nome, f"/tmp/{nome}", USUARIO_TESTE)
    marcar_erro(registro.id, "Falha ao gerar o relatório.")

    itens = listar_notificacoes_pessoais(USUARIO_TESTE)
    achado = next((i for i in itens if nome in i["mensagem"]), None)

    assert achado is not None
    assert achado["tipo"] == "erro_manual"
    assert achado["descartavel"] is False


def test_relatorio_pronto_do_usuario_vira_notificacao_descartavel(limpar_notificacoes_teste):
    job = registrar_processado(
        arquivo_pdf=f"{PREFIXO_TESTE}minhas_pronto.pdf",
        processo="0000000-00.2026.8.00.0050",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE,
    )

    itens = listar_notificacoes_pessoais(USUARIO_TESTE)
    achado = next((i for i in itens if job.arquivo_pdf in i["mensagem"]), None)

    assert achado is not None
    assert achado["tipo"] == "pronto"
    assert achado["descartavel"] is True
    assert achado["resolver"] == f"/extratus/relatorios/{job.id}/marcar-notificacao-resolvida"


def test_relatorio_em_revisao_do_usuario_vira_notificacao_nao_descartavel(limpar_notificacoes_teste):
    job = registrar_processado(
        arquivo_pdf=f"{PREFIXO_TESTE}minhas_revisao.pdf",
        processo="0000000-00.2026.8.00.0051",
        relatorio_path=None,
        destino_pdf=None,
        confianca="media",
        usuario_id=USUARIO_TESTE,
    )

    itens = listar_notificacoes_pessoais(USUARIO_TESTE)
    achado = next((i for i in itens if job.arquivo_pdf in i["mensagem"]), None)

    assert achado is not None
    assert achado["tipo"] == "revisao"
    assert achado["descartavel"] is False
    assert "resolver" not in achado


def test_relatorio_ja_notificado_nao_aparece_de_novo(limpar_notificacoes_teste):
    job = registrar_processado(
        arquivo_pdf=f"{PREFIXO_TESTE}minhas_ja_notificado.pdf",
        processo="0000000-00.2026.8.00.0052",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE,
    )
    marcar_notificacao_resolvida(job.id, USUARIO_TESTE)

    itens = listar_notificacoes_pessoais(USUARIO_TESTE)

    assert not any(job.arquivo_pdf in i["mensagem"] for i in itens)


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
