import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.ferramentas.crivus.db.models import AnalisePublicacao, AnexoAnalise, ItemAcompanhamento, ItemAgendamento
from app.plataforma.db.models import CARGO_COLABORADOR
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario, definir_ferramentas, excluir_usuario, listar_todas_ferramentas
from app.plataforma.web.main import app

SENHA_TESTE = "senhaTeste123"


def _dados_ia_fake():
    return {
        "processo": "0000000-00.0000.0.00.0000",
        "carteira": "OUTRA",
        "leitura_publicacao": "leitura de teste",
        "conclusao_operacional": "conclusão de teste",
        "nivel_confianca": "ALTO",
        "tem_alerta_critico": False,
        "texto_alerta_critico": None,
        "acompanhamentos": [{"tipo": "PUBLICAÇÃO"}],
        "agendamentos": [{"tipo": "MANIFESTAÇÃO", "dias_inicio": 5, "dias_fim": 10}],
    }, {"modelo": "claude-sonnet-5", "tokens_entrada": 1000, "tokens_saida": 200, "custo_estimado_usd": 0.05}


def _limpar_analises_do_usuario(usuario_id):
    with obter_sessao() as sessao:
        analises = sessao.exec(select(AnalisePublicacao).where(AnalisePublicacao.usuario_id == usuario_id)).all()
        for analise in analises:
            sessao.exec(delete(ItemAcompanhamento).where(ItemAcompanhamento.analise_id == analise.id))
            sessao.exec(delete(ItemAgendamento).where(ItemAgendamento.analise_id == analise.id))
            sessao.exec(delete(AnexoAnalise).where(AnexoAnalise.analise_id == analise.id))
        sessao.exec(delete(AnalisePublicacao).where(AnalisePublicacao.usuario_id == usuario_id))
        sessao.commit()


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


@pytest.fixture
def cliente_logado(monkeypatch):
    usuario = _criar_usuario_com_acesso("teste_crivus_producao")
    dados, uso = _dados_ia_fake()
    monkeypatch.setattr(
        "app.ferramentas.crivus.web.routes.leitor_individual.analisar_publicacao",
        lambda teor, anexos=None: (dados, uso),
    )

    cliente = TestClient(app, follow_redirects=True)
    cliente.post("/login", data={"usuario_login": "teste_crivus_producao", "senha": SENHA_TESTE})

    yield cliente, usuario

    _limpar_analises_do_usuario(usuario.id)
    excluir_usuario(usuario.id)


def _criar_caso(cliente, npjur="0119225"):
    resposta = cliente.post(
        "/crivus/leitor-individual/analisar",
        data={"npjur": npjur, "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "teor de teste"},
    )
    analise_id = int(str(resposta.url).rstrip("/").split("/")[-1])
    return analise_id


def _concluir_caso(analise_id):
    with obter_sessao() as sessao:
        item_acomp = sessao.exec(
            select(ItemAcompanhamento).where(ItemAcompanhamento.analise_id == analise_id)
        ).first()
        item_agend = sessao.exec(
            select(ItemAgendamento).where(ItemAgendamento.analise_id == analise_id)
        ).first()
    from app.ferramentas.crivus.db.analises import concluir_analise, marcar_item_pronto
    marcar_item_pronto(analise_id, "acompanhamento", item_acomp.id)
    marcar_item_pronto(analise_id, "agendamento", item_agend.id)
    concluir_analise(analise_id)


def test_producao_exige_login():
    cliente = TestClient(app, follow_redirects=False)
    resposta = cliente.get("/crivus/producao")
    assert resposta.status_code in (302, 303)


def test_producao_renderiza_individuais_pendentes_default(cliente_logado):
    cliente, _ = cliente_logado
    analise_id = _criar_caso(cliente, npjur="0119225")

    resposta = cliente.get("/crivus/producao")
    assert resposta.status_code == 200
    assert "0119225" in resposta.text
    assert f"/crivus/leitor-individual/{analise_id}" in resposta.text


def test_producao_filtra_por_query_params(cliente_logado):
    cliente, _ = cliente_logado
    pendente_id = _criar_caso(cliente, npjur="0111111")
    concluido_id = _criar_caso(cliente, npjur="0222222")
    _concluir_caso(concluido_id)

    resposta_pendentes = cliente.get("/crivus/producao?aba=individuais&filtro=pendentes")
    assert "0111111" in resposta_pendentes.text
    assert "0222222" not in resposta_pendentes.text

    resposta_concluidos = cliente.get("/crivus/producao?aba=individuais&filtro=concluidos")
    assert "0222222" in resposta_concluidos.text
    assert "0111111" not in resposta_concluidos.text


def test_producao_lotes_mostra_estado_vazio(cliente_logado):
    cliente, _ = cliente_logado
    _criar_caso(cliente, npjur="0333333")

    resposta = cliente.get("/crivus/producao?aba=lotes&filtro=pendentes")
    assert resposta.status_code == 200
    assert "0333333" not in resposta.text
    assert "Processamento em Lote" in resposta.text


def test_producao_valores_invalidos_caem_no_default(cliente_logado):
    cliente, _ = cliente_logado
    resposta = cliente.get("/crivus/producao?aba=lixo&filtro=lixo")
    assert resposta.status_code == 200


def test_usuario_b_pode_abrir_e_agir_em_caso_aberto_de_usuario_a(cliente_logado):
    """Prova a mudança de comportamento central desta tela: o acervo é do
    escritório inteiro, não do criador — qualquer colega pode retomar um
    caso individual ainda em aberto de outra pessoa."""
    cliente_a, _ = cliente_logado
    analise_id = _criar_caso(cliente_a, npjur="0444444")

    usuario_b = _criar_usuario_com_acesso("teste_crivus_producao_b")
    try:
        cliente_b = TestClient(app, follow_redirects=True)
        cliente_b.post("/login", data={"usuario_login": "teste_crivus_producao_b", "senha": SENHA_TESTE})

        resposta = cliente_b.get(f"/crivus/leitor-individual/{analise_id}")
        assert resposta.status_code == 200

        with obter_sessao() as sessao:
            item = sessao.exec(
                select(ItemAcompanhamento).where(ItemAcompanhamento.analise_id == analise_id)
            ).first()

        resposta = cliente_b.post(
            f"/crivus/leitor-individual/{analise_id}/acompanhamento/{item.id}/salvar",
            data={"tipo": "PUBLICAÇÃO"},
        )
        assert resposta.status_code == 200
        with obter_sessao() as sessao:
            assert sessao.get(ItemAcompanhamento, item.id).status == "pronto"
    finally:
        excluir_usuario(usuario_b.id)


def test_producao_lista_casos_de_todos_os_usuarios(cliente_logado):
    """A listagem não é filtrada por quem está logado — vale pra qualquer
    pessoa do escritório ver o acervo inteiro."""
    cliente_a, _ = cliente_logado
    _criar_caso(cliente_a, npjur="0555555")

    usuario_b = _criar_usuario_com_acesso("teste_crivus_producao_c")
    try:
        cliente_b = TestClient(app, follow_redirects=True)
        cliente_b.post("/login", data={"usuario_login": "teste_crivus_producao_c", "senha": SENHA_TESTE})

        resposta = cliente_b.get("/crivus/producao?aba=individuais&filtro=pendentes")
        assert "0555555" in resposta.text
    finally:
        excluir_usuario(usuario_b.id)
