from datetime import date

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlmodel import delete, select

from app.ferramentas.crivus.db.models import AnalisePublicacao, AnexoAnalise, ItemAcompanhamento, ItemAgendamento, LoteCrivus
from app.plataforma.db.models import CARGO_COLABORADOR
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario, definir_ferramentas, excluir_usuario, listar_todas_ferramentas
from app.plataforma.web.main import app

SENHA_TESTE = "senhaTeste123"


def _planilha_valida_bytes(linhas=2):
    pasta_trabalho = Workbook()
    planilha = pasta_trabalho.active
    planilha.append(["NPJUR", "DATA DA PUBLICAÇÃO", "DATA DA IMPORTAÇÃO DA PUBLICAÇÃO", "TEOR PUBLICAÇÃO"])
    for indice in range(linhas):
        planilha.append([f"01000{indice:02d}", "10/09/2026", "11/09/2026", f"teor da linha {indice}"])

    from io import BytesIO
    buffer = BytesIO()
    pasta_trabalho.save(buffer)
    return buffer.getvalue()


def _criar_usuario_com_acesso(nome_usuario, cargo=CARGO_COLABORADOR):
    usuario = criar_usuario(
        nome=f"Teste {nome_usuario}",
        nome_usuario=nome_usuario,
        email=f"{nome_usuario}@example.com",
        senha=SENHA_TESTE,
        eh_admin=False,
        cargo=cargo,
    )
    ferramentas = listar_todas_ferramentas()
    crivus_id = next(f.id for f in ferramentas if f.slug == "leitor-publicacoes")
    definir_ferramentas(usuario.id, [crivus_id])
    return usuario


def _limpar_lotes_do_usuario(usuario_id):
    with obter_sessao() as sessao:
        analises = sessao.exec(select(AnalisePublicacao).where(AnalisePublicacao.usuario_id == usuario_id)).all()
        for analise in analises:
            sessao.exec(delete(ItemAcompanhamento).where(ItemAcompanhamento.analise_id == analise.id))
            sessao.exec(delete(ItemAgendamento).where(ItemAgendamento.analise_id == analise.id))
            sessao.exec(delete(AnexoAnalise).where(AnexoAnalise.analise_id == analise.id))
        sessao.exec(delete(AnalisePublicacao).where(AnalisePublicacao.usuario_id == usuario_id))
        sessao.exec(delete(LoteCrivus).where(LoteCrivus.criado_por == usuario_id))
        sessao.commit()


@pytest.fixture
def cliente_logado():
    usuario = _criar_usuario_com_acesso("teste_crivus_lote_rotas")

    cliente = TestClient(app, follow_redirects=True)
    cliente.post("/login", data={"usuario_login": "teste_crivus_lote_rotas", "senha": SENHA_TESTE})

    yield cliente, usuario

    _limpar_lotes_do_usuario(usuario.id)
    excluir_usuario(usuario.id)


def test_lote_exige_login():
    cliente = TestClient(app, follow_redirects=False)
    resposta = cliente.get("/crivus/lote")
    assert resposta.status_code in (302, 303)


def test_pagina_lote_lista_vazio(cliente_logado):
    cliente, _ = cliente_logado
    resposta = cliente.get("/crivus/lote")
    assert resposta.status_code == 200
    assert "Nenhuma planilha enviada" in resposta.text


def test_upload_planilha_valida_cria_lote(cliente_logado):
    cliente, usuario = cliente_logado
    conteudo = _planilha_valida_bytes(linhas=3)

    resposta = cliente.post(
        "/crivus/lote/upload",
        files={"arquivo": ("planilha.xlsx", conteudo, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert resposta.status_code == 200
    assert "3 publicações na fila" in resposta.text

    with obter_sessao() as sessao:
        lote = sessao.exec(select(LoteCrivus).where(LoteCrivus.criado_por == usuario.id)).first()
        analises = sessao.exec(select(AnalisePublicacao).where(AnalisePublicacao.lote_id == lote.id)).all()

    assert lote.total_linhas == 3
    assert len(analises) == 3
    assert all(a.origem == "lote" for a in analises)
    assert all(a.data_publicacao_original == date(2026, 9, 10) for a in analises)


def test_upload_rejeita_extensao_errada(cliente_logado):
    cliente, _ = cliente_logado
    resposta = cliente.post(
        "/crivus/lote/upload",
        files={"arquivo": ("planilha.txt", b"conteudo qualquer", "text/plain")},
    )
    assert resposta.status_code == 200
    assert "não é uma planilha .xlsx" in resposta.text


def test_upload_rejeita_assinatura_invalida(cliente_logado):
    cliente, _ = cliente_logado
    resposta = cliente.post(
        "/crivus/lote/upload",
        files={"arquivo": ("planilha.xlsx", b"isso nao e um zip de verdade", "application/octet-stream")},
    )
    assert resposta.status_code == 200
    assert "não parece ser uma planilha" in resposta.text


def test_upload_rejeita_planilha_sem_coluna_obrigatoria(cliente_logado):
    cliente, _ = cliente_logado
    pasta_trabalho = Workbook()
    planilha = pasta_trabalho.active
    planilha.append(["NPJUR", "TEOR PUBLICAÇÃO"])
    planilha.append(["0100000", "teor sem as datas"])

    from io import BytesIO
    buffer = BytesIO()
    pasta_trabalho.save(buffer)

    resposta = cliente.post(
        "/crivus/lote/upload",
        files={"arquivo": ("planilha.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resposta.status_code == 200
    assert "precisa ter a" in resposta.text


def test_download_planilha_lote_nao_encontrado(cliente_logado):
    cliente, _ = cliente_logado
    resposta = cliente.get("/crivus/lote/999999/planilha")
    assert resposta.status_code == 200
    assert "Lote não encontrado" in resposta.text


def test_download_planilha_lote_ainda_processando(cliente_logado):
    cliente, usuario = cliente_logado
    conteudo = _planilha_valida_bytes(linhas=1)
    cliente.post(
        "/crivus/lote/upload",
        files={"arquivo": ("planilha.xlsx", conteudo, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    with obter_sessao() as sessao:
        lote = sessao.exec(select(LoteCrivus).where(LoteCrivus.criado_por == usuario.id)).first()

    resposta = cliente.get(f"/crivus/lote/{lote.id}/planilha")
    assert resposta.status_code == 200
    assert "ainda não terminou" in resposta.text
