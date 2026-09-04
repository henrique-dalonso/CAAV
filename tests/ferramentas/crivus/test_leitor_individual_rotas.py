import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.ferramentas.crivus.db.models import AnalisePublicacao, AnexoAnalise, ItemAcompanhamento, ItemAgendamento
from app.plataforma.db.models import CARGO_COLABORADOR, CARGO_COORDENADOR
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario, definir_ferramentas, excluir_usuario, listar_todas_ferramentas
from app.plataforma.web.main import app

SENHA_TESTE = "senhaTeste123"


def _dados_ia_fake(tem_alerta_critico=False):
    return {
        "processo": "0000000-00.0000.0.00.0000",
        "carteira": "OUTRA",
        "leitura_publicacao": "leitura de teste",
        "conclusao_operacional": "conclusão de teste",
        "nivel_confianca": "ALTO",
        "tem_alerta_critico": tem_alerta_critico,
        "texto_alerta_critico": "providência urgente de teste" if tem_alerta_critico else None,
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
    usuario = _criar_usuario_com_acesso("teste_crivus_rotas")
    dados, uso = _dados_ia_fake()
    monkeypatch.setattr(
        "app.ferramentas.crivus.web.routes.leitor_individual.analisar_publicacao",
        lambda teor, anexos=None: (dados, uso),
    )

    cliente = TestClient(app, follow_redirects=True)
    cliente.post("/login", data={"usuario_login": "teste_crivus_rotas", "senha": SENHA_TESTE})

    yield cliente, usuario

    _limpar_analises_do_usuario(usuario.id)
    excluir_usuario(usuario.id)


def test_pagina_inicial_exige_login():
    cliente = TestClient(app, follow_redirects=False)
    resposta = cliente.get("/crivus/leitor-individual")
    assert resposta.status_code in (302, 303)


def test_pagina_inicial_renderiza_formulario(cliente_logado):
    cliente, _ = cliente_logado
    resposta = cliente.get("/crivus/leitor-individual")
    assert resposta.status_code == 200
    assert "teor_publicacao" in resposta.text


def test_analisar_sem_teor_volta_com_erro(cliente_logado):
    cliente, _ = cliente_logado
    resposta = cliente.post("/crivus/leitor-individual/analisar", data={"npjur": "0119225", "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "   "})
    assert resposta.status_code == 200
    assert "Cole o teor" in resposta.text


def test_fluxo_completo_analisar_corrigir_e_concluir(cliente_logado):
    cliente, usuario = cliente_logado

    resposta = cliente.post("/crivus/leitor-individual/analisar", data={"npjur": "0119225", "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "teor de teste qualquer"})
    assert resposta.status_code == 200
    analise_id = int(str(resposta.url).rstrip("/").split("/")[-1])
    assert "PUBLICAÇÃO" in resposta.text or "MANIFESTA" in resposta.text

    with obter_sessao() as sessao:
        acomp = sessao.exec(select(ItemAcompanhamento).where(ItemAcompanhamento.analise_id == analise_id)).one()
        agend = sessao.exec(select(ItemAgendamento).where(ItemAgendamento.analise_id == analise_id)).one()

    # ainda não pode concluir - itens pendentes
    resposta = cliente.post(f"/crivus/leitor-individual/{analise_id}/concluir")
    assert "não é mais possível" not in resposta.text  # não é esse o erro aqui
    with obter_sessao() as sessao:
        analise_atual = sessao.get(AnalisePublicacao, analise_id)
        assert analise_atual.status != "concluido"

    cliente.post(f"/crivus/leitor-individual/{analise_id}/acompanhamento/{acomp.id}/salvar", data={"tipo": acomp.tipo})
    cliente.post(
        f"/crivus/leitor-individual/{analise_id}/agendamento/{agend.id}/salvar",
        data={"tipo": agend.tipo, "data_inicio": str(agend.data_inicio), "data_fim": str(agend.data_fim)},
    )

    resposta = cliente.post(f"/crivus/leitor-individual/{analise_id}/concluir")
    assert "sucesso" in str(resposta.url)

    with obter_sessao() as sessao:
        analise_atual = sessao.get(AnalisePublicacao, analise_id)
        assert analise_atual.status == "concluido"


def test_marcar_desnecessario_tambem_libera_conclusao(cliente_logado):
    """Henrique, 2026-09-06: Acompanhamento nunca pode virar
    "desnecessario" (sempre há exatamente 1, corrige-se em vez de
    descartar) — só o agendamento tem esse caminho; o acompanhamento
    precisa ser marcado "pronto" pra liberar a conclusão."""
    cliente, usuario = cliente_logado
    resposta = cliente.post("/crivus/leitor-individual/analisar", data={"npjur": "0119225", "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "teor de teste"})
    analise_id = int(str(resposta.url).rstrip("/").split("/")[-1])

    with obter_sessao() as sessao:
        acomp = sessao.exec(select(ItemAcompanhamento).where(ItemAcompanhamento.analise_id == analise_id)).one()
        agend = sessao.exec(select(ItemAgendamento).where(ItemAgendamento.analise_id == analise_id)).one()

    cliente.post(f"/crivus/leitor-individual/{analise_id}/acompanhamento/{acomp.id}/salvar", data={"tipo": acomp.tipo})
    cliente.post(f"/crivus/leitor-individual/{analise_id}/agendamento/{agend.id}/desnecessario")

    resposta = cliente.post(f"/crivus/leitor-individual/{analise_id}/concluir")
    assert "sucesso" in str(resposta.url)


def test_acompanhamento_nao_pode_ser_marcado_desnecessario(cliente_logado):
    cliente, usuario = cliente_logado
    resposta = cliente.post("/crivus/leitor-individual/analisar", data={"npjur": "0119225", "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "teor de teste"})
    analise_id = int(str(resposta.url).rstrip("/").split("/")[-1])

    with obter_sessao() as sessao:
        acomp = sessao.exec(select(ItemAcompanhamento).where(ItemAcompanhamento.analise_id == analise_id)).one()

    resposta = cliente.post(f"/crivus/leitor-individual/{analise_id}/acompanhamento/{acomp.id}/desnecessario")
    assert "não pode ser marcado como desnecessário" in resposta.text

    with obter_sessao() as sessao:
        acomp_atual = sessao.get(ItemAcompanhamento, acomp.id)
        assert acomp_atual.status == "sugerido"


def test_alerta_critico_bloqueia_conclusao_sem_ciencia(monkeypatch):
    usuario = _criar_usuario_com_acesso("teste_crivus_alerta")
    dados, uso = _dados_ia_fake(tem_alerta_critico=True)
    monkeypatch.setattr(
        "app.ferramentas.crivus.web.routes.leitor_individual.analisar_publicacao",
        lambda teor, anexos=None: (dados, uso),
    )

    cliente = TestClient(app, follow_redirects=True)
    cliente.post("/login", data={"usuario_login": "teste_crivus_alerta", "senha": SENHA_TESTE})

    try:
        resposta = cliente.post("/crivus/leitor-individual/analisar", data={"npjur": "0119225", "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "teor com alerta"})
        analise_id = int(str(resposta.url).rstrip("/").split("/")[-1])
        assert "🚨" in resposta.text or "Alerta" in resposta.text

        with obter_sessao() as sessao:
            acomp = sessao.exec(select(ItemAcompanhamento).where(ItemAcompanhamento.analise_id == analise_id)).one()
            agend = sessao.exec(select(ItemAgendamento).where(ItemAgendamento.analise_id == analise_id)).one()

        cliente.post(f"/crivus/leitor-individual/{analise_id}/acompanhamento/{acomp.id}/salvar", data={"tipo": acomp.tipo})
        cliente.post(
            f"/crivus/leitor-individual/{analise_id}/agendamento/{agend.id}/salvar",
            data={"tipo": agend.tipo, "data_inicio": str(agend.data_inicio), "data_fim": str(agend.data_fim)},
        )

        # todos prontos, mas sem marcar ciência do alerta -> não conclui
        resposta = cliente.post(f"/crivus/leitor-individual/{analise_id}/concluir")
        with obter_sessao() as sessao:
            assert sessao.get(AnalisePublicacao, analise_id).status != "concluido"

        cliente.post(f"/crivus/leitor-individual/{analise_id}/ciente-alerta")
        resposta = cliente.post(f"/crivus/leitor-individual/{analise_id}/concluir")
        assert "sucesso" in str(resposta.url)
    finally:
        _limpar_analises_do_usuario(usuario.id)
        excluir_usuario(usuario.id)


def test_usuario_nao_dono_recebe_404(cliente_logado):
    cliente, usuario = cliente_logado
    resposta = cliente.post("/crivus/leitor-individual/analisar", data={"npjur": "0119225", "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "teor de teste"})
    analise_id = int(str(resposta.url).rstrip("/").split("/")[-1])

    outro = _criar_usuario_com_acesso("teste_crivus_outro")
    try:
        cliente_outro = TestClient(app, follow_redirects=True)
        cliente_outro.post("/login", data={"usuario_login": "teste_crivus_outro", "senha": SENHA_TESTE})
        resposta = cliente_outro.get(f"/crivus/leitor-individual/{analise_id}")
        assert resposta.status_code == 404
    finally:
        excluir_usuario(outro.id)


def test_anexo_com_extensao_nao_aceita_e_rejeitado(cliente_logado):
    cliente, _ = cliente_logado
    resposta = cliente.post(
        "/crivus/leitor-individual/analisar",
        data={"npjur": "0119225", "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "teor de teste"},
        files={"arquivos": ("malicioso.exe", b"conteudo qualquer", "application/octet-stream")},
    )
    assert "não é um tipo de arquivo aceito" in resposta.text


def test_anexo_maior_que_limite_e_rejeitado(cliente_logado):
    cliente, _ = cliente_logado
    conteudo_grande = b"%PDF" + b"0" * (6 * 1024 * 1024)
    resposta = cliente.post(
        "/crivus/leitor-individual/analisar",
        data={"npjur": "0119225", "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "teor de teste"},
        files={"arquivos": ("grande.pdf", conteudo_grande, "application/pdf")},
    )
    assert "tem mais de" in resposta.text


def test_anexo_com_conteudo_nao_correspondente_a_extensao_e_rejeitado(cliente_logado):
    cliente, _ = cliente_logado
    resposta = cliente.post(
        "/crivus/leitor-individual/analisar",
        data={"npjur": "0119225", "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "teor de teste"},
        files={"arquivos": ("falso.pdf", b"isso nao e um pdf de verdade", "application/pdf")},
    )
    assert "não parece ser um arquivo válido" in resposta.text


def test_salvar_agendamento_com_tipo_vazio_mostra_erro_sem_quebrar(cliente_logado):
    """Henrique, 2026-09-06: achado real testando o botão de excluir de
    agendamento manual — um <select required> vazio nunca deveria chegar
    ao servidor, mas se chegasse (tipo=""), o FastAPI devolvia um 422 cru
    em vez do banner de erro normal (Form(...) tratava valor vazio como
    campo ausente). Trocado pra Form("") nas rotas de salvar; a validação
    de "precisa escolher um tipo" agora é responsabilidade da camada de
    negócio, que mostra a mensagem certa."""
    cliente, usuario = cliente_logado

    resposta = cliente.post(
        "/crivus/leitor-individual/analisar",
        data={"npjur": "0119225", "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "teor de teste"},
    )
    analise_id = int(str(resposta.url).rstrip("/").split("/")[-1])
    cliente.post(f"/crivus/leitor-individual/{analise_id}/agendamento/novo")

    with obter_sessao() as sessao:
        item = sessao.exec(
            select(ItemAgendamento).where(ItemAgendamento.analise_id == analise_id, ItemAgendamento.criado_manualmente == True)  # noqa: E712
        ).one()

    resposta = cliente.post(
        f"/crivus/leitor-individual/{analise_id}/agendamento/{item.id}/salvar",
        data={"tipo": "", "data_inicio": str(item.data_inicio), "data_fim": str(item.data_fim)},
    )
    assert resposta.status_code == 200
    assert "Selecione um tipo" in resposta.text


def test_colaborador_nao_pode_passar_do_limite_de_anexos(cliente_logado):
    cliente, _ = cliente_logado
    arquivos = [
        ("arquivos", (f"doc{i}.pdf", b"%PDF-conteudo", "application/pdf"))
        for i in range(4)
    ]
    resposta = cliente.post(
        "/crivus/leitor-individual/analisar",
        data={"npjur": "0119225", "processo": "0000000-00.0000.0.00.0000", "teor_publicacao": "teor de teste"},
        files=arquivos,
    )
    assert "Máximo de 3 anexos" in resposta.text
