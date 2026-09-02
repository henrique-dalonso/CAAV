from datetime import datetime

import pytest
from sqlmodel import delete

from app.ferramentas.extratus_aburesi.db.checagem_fila import (
    APROVADO,
    DUPLICADO_RELATORIO,
    PENDENTE,
)
from app.ferramentas.extratus_aburesi.db.jobs import (
    marcar_notificacao_resolvida,
    marcar_notificacao_resolvida_robo,
    registrar_erro,
    registrar_processado,
)
from app.ferramentas.extratus_aburesi.db.models import ChecagemFila, Job, TriagemManual
from app.ferramentas.extratus_aburesi.db.triagem_manual import NAO_ENCONTRADO, atualizar_apos_triagem, criar_registro, marcar_erro
from app.ferramentas.extratus_aburesi.web.notificacoes import listar_notificacoes, listar_notificacoes_pessoais
from app.plataforma.db.session import obter_sessao


PREFIXO_TESTE = "teste_notif_aburesi_"

# Ver comentário equivalente em tests/ferramentas/extratus/test_notificacoes.py
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

    itens = listar_notificacoes(USUARIO_TESTE)
    achado = next((i for i in itens if nome in i["mensagem"]), None)

    assert achado is not None
    assert achado["tipo"] == "triagem"
    assert achado["link"] == "/extratus-aburesi/fila-robo"


def test_status_aprovado_e_pendente_nao_viram_notificacao(limpar_notificacoes_teste):
    nome_aprovado = f"{PREFIXO_TESTE}aprovado.pdf"
    nome_pendente = f"{PREFIXO_TESTE}pendente.pdf"
    _criar_checagem(nome_aprovado, APROVADO)
    _criar_checagem(nome_pendente, PENDENTE)

    itens = listar_notificacoes(USUARIO_TESTE)
    mensagens = " ".join(i["mensagem"] for i in itens)

    assert nome_aprovado not in mensagens
    assert nome_pendente not in mensagens


def test_erro_do_robo_vira_notificacao(limpar_notificacoes_teste):
    nome = f"{PREFIXO_TESTE}erro_robo.pdf"
    registrar_erro(nome, None, "erro_pdf", "PDF corrompido", usuario_id=None)

    itens = listar_notificacoes(USUARIO_TESTE)
    achado = next((i for i in itens if nome in i["mensagem"]), None)

    assert achado is not None
    assert achado["tipo"] == "erro"
    assert achado["link"] == "/extratus-aburesi/relatorios-robo"


def test_erro_do_robo_com_processo_vira_notificacao_com_deep_link(limpar_notificacoes_teste):
    # Ver comentário equivalente em tests/ferramentas/extratus/test_notificacoes.py
    # — mesma lógica.
    nome = f"{PREFIXO_TESTE}erro_robo_com_processo.pdf"
    registrar_erro(nome, "0000000-00.2026.8.00.9999", "erro_ia", "processo grande demais", usuario_id=None)

    itens = listar_notificacoes(USUARIO_TESTE)
    achado = next((i for i in itens if nome in i["mensagem"]), None)

    assert achado is not None
    assert achado["link"] == "/extratus-aburesi/relatorios-robo?processo=0000000-00.2026.8.00.9999"


def test_notificacao_de_triagem_carrega_criado_em_valido(limpar_notificacoes_teste):
    # Ver comentário equivalente em tests/ferramentas/extratus/test_notificacoes.py
    nome = f"{PREFIXO_TESTE}com_timestamp.pdf"
    _criar_checagem(nome, DUPLICADO_RELATORIO)

    itens = listar_notificacoes(USUARIO_TESTE)
    achado = next((i for i in itens if nome in i["mensagem"]), None)

    assert achado is not None
    assert datetime.fromisoformat(achado["criado_em"])


def test_notificacao_de_erro_do_robo_carrega_criado_em_valido(limpar_notificacoes_teste):
    nome = f"{PREFIXO_TESTE}erro_com_timestamp.pdf"
    registrar_erro(nome, None, "erro_pdf", "PDF corrompido", usuario_id=None)

    itens = listar_notificacoes(USUARIO_TESTE)
    achado = next((i for i in itens if nome in i["mensagem"]), None)

    assert achado is not None
    assert datetime.fromisoformat(achado["criado_em"])


def test_erro_do_fluxo_manual_nao_vira_notificacao(limpar_notificacoes_teste):
    nome = f"{PREFIXO_TESTE}erro_manual.pdf"
    registrar_erro(nome, None, "erro_pdf", "PDF corrompido", usuario_id=1)

    itens = listar_notificacoes(USUARIO_TESTE)

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
    assert achado["resolver"] == f"/extratus-aburesi/relatorios-urgentes/{job.id}/marcar-notificacao-resolvida"


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


def test_sucesso_do_robo_vira_notificacao_nao_descartavel_em_ferramentas(limpar_notificacoes_teste):
    job = registrar_processado(
        arquivo_pdf=f"{PREFIXO_TESTE}sucesso_robo.pdf",
        processo="0000000-00.2026.8.00.0070",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )

    itens = listar_notificacoes(USUARIO_TESTE)
    achado = next((i for i in itens if job.arquivo_pdf in i["mensagem"]), None)

    assert achado is not None
    assert achado["tipo"] == "pronto"
    assert "descartavel" not in achado
    assert "resolver" not in achado


def test_sucesso_do_robo_do_solicitante_vai_pra_minhas_e_e_descartavel(limpar_notificacoes_teste):
    job = registrar_processado(
        arquivo_pdf=f"{PREFIXO_TESTE}sucesso_robo_solicitado.pdf",
        processo="0000000-00.2026.8.00.0073",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
        solicitante_id=USUARIO_TESTE,
    )

    itens_pessoais = listar_notificacoes_pessoais(USUARIO_TESTE)
    achado = next((i for i in itens_pessoais if job.arquivo_pdf in i["mensagem"]), None)

    assert achado is not None
    assert achado["tipo"] == "pronto"
    assert achado["pessoal"] is True
    assert achado["descartavel"] is True
    assert achado["resolver"] == f"/extratus-aburesi/relatorios-robo/{job.id}/marcar-notificacao-resolvida"

    itens_ferramentas = listar_notificacoes(USUARIO_TESTE)
    assert not any(job.arquivo_pdf in i["mensagem"] for i in itens_ferramentas)

    OUTRO_USUARIO = -9005
    itens_ferramentas_de_outro = listar_notificacoes(OUTRO_USUARIO)
    achado_outro = next((i for i in itens_ferramentas_de_outro if job.arquivo_pdf in i["mensagem"]), None)
    assert achado_outro is not None
    assert "descartavel" not in achado_outro

    assert not any(job.arquivo_pdf in i["mensagem"] for i in listar_notificacoes_pessoais(OUTRO_USUARIO))


def test_revisao_do_robo_vira_notificacao_nao_descartavel(limpar_notificacoes_teste):
    job = registrar_processado(
        arquivo_pdf=f"{PREFIXO_TESTE}revisao_robo.pdf",
        processo="0000000-00.2026.8.00.0071",
        relatorio_path=None,
        destino_pdf=None,
        confianca="media",
        usuario_id=None,
    )

    itens = listar_notificacoes(USUARIO_TESTE)
    achado = next((i for i in itens if job.arquivo_pdf in i["mensagem"]), None)

    assert achado is not None
    assert achado["tipo"] == "revisao"
    assert "descartavel" not in achado
    assert "resolver" not in achado


def test_sucesso_do_robo_resolvido_nao_vira_notificacao(limpar_notificacoes_teste):
    job = registrar_processado(
        arquivo_pdf=f"{PREFIXO_TESTE}sucesso_robo_resolvido.pdf",
        processo="0000000-00.2026.8.00.0072",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )

    assert marcar_notificacao_resolvida_robo(job.id) is True

    itens = listar_notificacoes(USUARIO_TESTE)
    assert not any(job.arquivo_pdf in i["mensagem"] for i in itens)


def test_erro_marcado_resolvido_nao_vira_notificacao(limpar_notificacoes_teste):
    nome = f"{PREFIXO_TESTE}erro_resolvido.pdf"
    job = registrar_erro(nome, None, "erro_pdf", "PDF corrompido", usuario_id=None)

    with obter_sessao() as sessao:
        registro = sessao.get(Job, job.id)
        registro.notificacao_resolvida = True
        sessao.add(registro)
        sessao.commit()

    itens = listar_notificacoes(USUARIO_TESTE)

    assert not any(nome in i["mensagem"] for i in itens)
