from datetime import datetime

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


def test_producao_renderiza_individuais_pendentes(cliente_logado):
    cliente, _ = cliente_logado
    analise_id = _criar_caso(cliente, npjur="0119225")

    resposta = cliente.get("/crivus/producao?aba=individuais&filtro=pendentes")
    assert resposta.status_code == 200
    assert "0119225" in resposta.text
    assert f"/crivus/leitor-individual/{analise_id}" in resposta.text


def test_link_do_caso_carrega_aba_e_filtro_atuais_como_origem(cliente_logado):
    """Henrique, 2026-09-13: o link de cada caso precisa levar a URL
    EXATA da Produção (aba+filtro), não um destino genérico — senão
    "Descartar"/"Concluir Caso" voltam pro estado padrão em vez de onde
    a pessoa realmente estava."""
    cliente, _ = cliente_logado
    analise_id = _criar_caso(cliente, npjur="0119225")

    resposta = cliente.get("/crivus/producao?aba=individuais&filtro=pendentes")
    assert (
        f"/crivus/leitor-individual/{analise_id}"
        "?origem=/crivus/producao%3Faba%3Dindividuais%26filtro%3Dpendentes"
        in resposta.text
    )


def test_producao_default_e_lotes_pendentes(cliente_logado):
    """Henrique, 2026-09-13: Lotes vira a aba padrão de Produção (antes
    era Individuais) — acessar /crivus/producao sem parâmetro nenhum já
    cai direto no estado vazio de Lotes, não mostra casos individuais."""
    cliente, _ = cliente_logado
    _criar_caso(cliente, npjur="0119225")

    resposta = cliente.get("/crivus/producao")
    assert resposta.status_code == 200
    assert "Processamento em Lote" in resposta.text
    assert "0119225" not in resposta.text


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


def test_producao_busca_filtra_por_npjur_ou_processo(cliente_logado):
    """Henrique, diretoria, 2026-09-15: "faltando busca e filtros, igual
    o Extratus" — busca livre bate tanto em NPJUR quanto em Nº CNJ."""
    cliente, _ = cliente_logado
    _criar_caso(cliente, npjur="0111111")
    _criar_caso(cliente, npjur="0222222")

    resposta = cliente.get("/crivus/producao?aba=individuais&filtro=pendentes&busca=0111111")
    assert "0111111" in resposta.text
    assert "0222222" not in resposta.text

    # a mesma busca bate pelo Nº CNJ (todos os casos de teste usam o
    # mesmo processo fake) — confirma que o campo processo também é
    # varrido, não só npjur
    resposta_processo = cliente.get("/crivus/producao?aba=individuais&filtro=pendentes&busca=0000000-00.0000.0.00.0000")
    assert "0111111" in resposta_processo.text
    assert "0222222" in resposta_processo.text


def test_producao_filtra_por_intervalo_de_data(cliente_logado):
    cliente, _ = cliente_logado
    antigo_id = _criar_caso(cliente, npjur="0333333")
    recente_id = _criar_caso(cliente, npjur="0444444")

    with obter_sessao() as sessao:
        antigo = sessao.get(AnalisePublicacao, antigo_id)
        antigo.criado_em = datetime(2020, 1, 1)
        sessao.add(antigo)
        sessao.commit()

    resposta = cliente.get("/crivus/producao?aba=individuais&filtro=pendentes&data_de=2026-01-01")
    assert "0444444" in resposta.text
    assert "0333333" not in resposta.text


def test_producao_filtra_por_solicitante(cliente_logado):
    cliente, usuario = cliente_logado
    _criar_caso(cliente, npjur="0555555")

    resposta_deste_usuario = cliente.get(f"/crivus/producao?aba=individuais&filtro=pendentes&solicitante_id={usuario.id}")
    assert "0555555" in resposta_deste_usuario.text

    resposta_outro_usuario = cliente.get("/crivus/producao?aba=individuais&filtro=pendentes&solicitante_id=999999")
    assert "0555555" not in resposta_outro_usuario.text


def test_producao_dropdown_solicitante_so_mostra_quem_tem_caso(cliente_logado):
    """Henrique, diretoria, 2026-09-15: "mesmo comportamento do Extratus"
    — o dropdown "Solicitado por" só oferece quem de fato tem caso nessa
    aba+filtro, não a base de usuários inteira (a maioria nunca mandou
    nada pra essa aba)."""
    cliente, usuario = cliente_logado
    _criar_caso(cliente, npjur="0666666")

    sem_caso_nenhum = _criar_usuario_com_acesso("teste_crivus_producao_sem_caso")
    try:
        resposta = cliente.get("/crivus/producao?aba=individuais&filtro=pendentes")
        assert f'value="{usuario.id}"' in resposta.text
        assert f'value="{sem_caso_nenhum.id}"' not in resposta.text
    finally:
        excluir_usuario(sem_caso_nenhum.id)


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
