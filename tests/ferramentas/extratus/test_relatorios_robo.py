import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.ferramentas.extratus.db.checagem_fila import registrar_upload
from app.ferramentas.extratus.db.jobs import registrar_processado
from app.ferramentas.extratus.db.models import Job, UploadFilaRobo
from app.plataforma.db.models import Ferramenta, Usuario, UsuarioFerramenta
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_TESTE = "teste_relatorios_robo"
NOME_USUARIO_SEM_FILA = "teste_relrobo_sem_fila"
SENHA = "senhaTeste123"

# ID negativo de propósito — usuario_id real nunca é negativo (ver
# mesmo padrão em tests/ferramentas/extratus/test_jobs.py).
USUARIO_TESTE = -9010


@pytest.fixture
def cliente_logado():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Relatórios do Robô",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_relatorios_robo@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA})

    yield cliente

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


@pytest.fixture
def limpar_jobs_criados():
    ids_criados = []

    yield ids_criados

    if ids_criados:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.id.in_(ids_criados)))
            sessao.commit()


def test_pagina_relatorios_robo_exige_login():
    cliente = TestClient(app)

    resp = cliente.get("/extratus/relatorios-robo", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_pagina_relatorios_robo_so_lista_jobs_do_robo(cliente_logado, limpar_jobs_criados):
    job_robo = registrar_processado(
        arquivo_pdf="teste_pagina_relatorios_robo.pdf",
        processo="0000000-00.2026.8.00.0040",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    job_manual = registrar_processado(
        arquivo_pdf="teste_pagina_relatorios_robo_manual.pdf",
        processo="0000000-00.2026.8.00.0041",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE,
    )
    limpar_jobs_criados.extend([job_robo.id, job_manual.id])

    resp = cliente_logado.get("/extratus/relatorios-robo")

    assert resp.status_code == 200
    assert "teste_pagina_relatorios_robo.pdf" in resp.text
    assert "teste_pagina_relatorios_robo_manual.pdf" not in resp.text


def test_pagina_relatorios_robo_mostra_quem_solicitou(cliente_logado, limpar_jobs_criados):
    """Achado real (Henrique, diretoria, 2026-08-27): a diretoria
    perguntou quem colocou um processo no Robô e não dava pra responder
    — "Robô automático" sozinho não diz quem pediu. `solicitante_id`
    carregado direto desde o upload (ver checagem_fila.registrar_pendente),
    não mais deduzido depois — não precisa simular upload nenhum aqui,
    só passar o campo direto."""
    with obter_sessao() as sessao:
        usuario_id_logado = sessao.exec(
            select(Usuario.id).where(Usuario.nome_usuario == NOME_USUARIO_TESTE)
        ).first()

    job_robo = registrar_processado(
        arquivo_pdf="teste_relrobo_solicitante.pdf",
        processo="0000000-00.2026.8.00.0043",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
        solicitante_id=usuario_id_logado,
    )
    limpar_jobs_criados.append(job_robo.id)

    resp = cliente_logado.get("/extratus/relatorios-robo")

    assert resp.status_code == 200
    assert "Solicitado por: Teste Relatórios do Robô" in resp.text
    assert f'value="{usuario_id_logado}"' in resp.text  # opção do dropdown "Solicitado por"


def test_pagina_relatorios_robo_mostra_quem_solicitou_por_fallback(cliente_logado, limpar_jobs_criados):
    """Henrique, mesmo dia (2026-08-27): "os relatórios que já estavam
    prontos agora estão como não identificado... manter aquela solução
    de antes como fallback". Job de ANTES da coluna solicitante_id
    existir (aqui simulado com solicitante_id=None) ainda tem que
    mostrar o nome de quem pediu, deduzido pelo upload registrado na
    Fila do Robô."""
    with obter_sessao() as sessao:
        usuario_id_logado = sessao.exec(
            select(Usuario.id).where(Usuario.nome_usuario == NOME_USUARIO_TESTE)
        ).first()

    registrar_upload("teste_relrobo_solicitante_fallback.pdf", usuario_id_logado)

    job_robo = registrar_processado(
        arquivo_pdf="teste_relrobo_solicitante_fallback.pdf",
        processo="0000000-00.2026.8.00.0044",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
        solicitante_id=None,
    )
    limpar_jobs_criados.append(job_robo.id)

    resp = cliente_logado.get("/extratus/relatorios-robo")

    assert resp.status_code == 200
    assert "Solicitado por: Teste Relatórios do Robô" in resp.text

    with obter_sessao() as sessao:
        sessao.exec(delete(UploadFilaRobo).where(UploadFilaRobo.nome_arquivo == "teste_relrobo_solicitante_fallback.pdf"))
        sessao.commit()


def test_pagina_relatorios_robo_acessivel_sem_acesso_a_fila():
    """Henrique, 2026-08-11: ver o acervo do Robô não deveria mais exigir
    acesso à Fila do Robô — só acesso à ferramenta, igual "Seus
    Relatórios". Testa exatamente o caso que antes dava 403: usuário com
    a ferramenta liberada, mas sem `fila_robo`."""
    with obter_sessao() as sessao:
        usuario_antigo = sessao.exec(select(Usuario.id).where(Usuario.nome_usuario == NOME_USUARIO_SEM_FILA)).first()
        if usuario_antigo:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_antigo))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_SEM_FILA))
        sessao.commit()
        extratus_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "extratus")).first()

    criar_usuario(
        nome="Teste RelRobo Sem Fila",
        nome_usuario=NOME_USUARIO_SEM_FILA,
        email="teste_relrobo_sem_fila@example.com",
        senha=SENHA,
        eh_admin=False,
        ferramenta_ids=[extratus_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_SEM_FILA, "senha": SENHA})

    resp = cliente.get("/extratus/relatorios-robo")

    assert resp.status_code == 200

    with obter_sessao() as sessao:
        usuario_id = sessao.exec(select(Usuario.id).where(Usuario.nome_usuario == NOME_USUARIO_SEM_FILA)).first()
        if usuario_id:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_SEM_FILA))
        sessao.commit()


def test_pagina_relatorios_manual_nao_lista_jobs_do_robo(cliente_logado, limpar_jobs_criados):
    job_robo = registrar_processado(
        arquivo_pdf="teste_pagina_relatorios_manual_robo.pdf",
        processo="0000000-00.2026.8.00.0042",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.append(job_robo.id)

    resp = cliente_logado.get("/extratus/relatorios")

    assert resp.status_code == 200
    assert "teste_pagina_relatorios_manual_robo.pdf" not in resp.text


def test_marcar_notificacao_resolvida_robo_route_funciona_sem_dono(cliente_logado, limpar_jobs_criados):
    # Henrique, diretoria, 2026-08-19: X do "sucesso" do Robô na aba
    # "Ferramentas" do sino — diferente do equivalente manual, não tem
    # dono, então qualquer um com acesso à ferramenta consegue dispensar.
    job = registrar_processado(
        arquivo_pdf="teste_relrobo_marcar_resolvida.pdf",
        processo="0000000-00.2026.8.00.0090",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.append(job.id)

    resp = cliente_logado.post(f"/extratus/relatorios-robo/{job.id}/marcar-notificacao-resolvida")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    with obter_sessao() as sessao:
        atualizado = sessao.get(Job, job.id)
        assert atualizado.notificacao_resolvida is True


def test_marcar_notificacao_resolvida_robo_route_job_inexistente_da_404(cliente_logado):
    resp = cliente_logado.post("/extratus/relatorios-robo/999999999/marcar-notificacao-resolvida")

    assert resp.status_code == 404


def test_excluir_relatorio_robo_admin_apaga_de_verdade(cliente_logado):
    job = registrar_processado(
        arquivo_pdf="teste_excluir_relatorio_robo_admin.pdf",
        processo="0000000-00.2026.8.00.0914",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=None,
    )

    resp = cliente_logado.post(f"/extratus/relatorios-robo/{job.id}/excluir", follow_redirects=False)

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]

    with obter_sessao() as sessao:
        assert sessao.get(Job, job.id) is None


def test_excluir_relatorio_robo_inexistente_redireciona_com_erro(cliente_logado):
    resp = cliente_logado.post("/extratus/relatorios-robo/999999999/excluir", follow_redirects=False)

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]


def test_excluir_relatorio_robo_recusa_nao_admin():
    """Mesma regra do equivalente manual: só admin da plataforma exclui,
    mesmo tendo acesso normal à tela de Relatórios do Robô (qualquer um
    com a ferramenta liberada tem essa, sem precisar de fila_robo)."""
    nome_usuario = "teste_relrobo_excluir_nao_admin"

    with obter_sessao() as sessao:
        usuario_antigo = sessao.exec(select(Usuario.id).where(Usuario.nome_usuario == nome_usuario)).first()
        if usuario_antigo:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_antigo))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == nome_usuario))
        sessao.commit()
        extratus_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "extratus")).first()

    criar_usuario(
        nome="Teste RelRobo Excluir Não-Admin", nome_usuario=nome_usuario,
        email="teste_relrobo_excluir_nao_admin@example.com", senha=SENHA, eh_admin=False,
        ferramenta_ids=[extratus_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": nome_usuario, "senha": SENHA})

    job = registrar_processado(
        arquivo_pdf="teste_excluir_relatorio_robo_nao_admin.pdf",
        processo="0000000-00.2026.8.00.0915",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=None,
    )

    resp = cliente.post(f"/extratus/relatorios-robo/{job.id}/excluir")

    assert resp.status_code == 403

    with obter_sessao() as sessao:
        assert sessao.get(Job, job.id) is not None
        sessao.exec(delete(Job).where(Job.id == job.id))
        usuario_id = sessao.exec(select(Usuario.id).where(Usuario.nome_usuario == nome_usuario)).first()
        if usuario_id:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == nome_usuario))
        sessao.commit()


def test_ver_pdf_relatorio_robo_abre_o_arquivo_de_origem(cliente_logado, tmp_path):
    pdf_origem = tmp_path / "processo_robo_original.pdf"
    pdf_origem.write_bytes(b"%PDF-1.4 conteudo de teste robo")

    job = registrar_processado(
        arquivo_pdf="processo_robo_original.pdf",
        processo="0000000-00.2026.8.00.0921",
        relatorio_path=None, destino_pdf=str(pdf_origem), confianca="alta",
        usuario_id=None,
    )

    resp = cliente_logado.get(f"/extratus/relatorios-robo/{job.id}/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == b"%PDF-1.4 conteudo de teste robo"

    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.id == job.id))
        sessao.commit()


def test_ver_pdf_relatorio_robo_sem_destino_pdf_da_404(cliente_logado):
    job = registrar_processado(
        arquivo_pdf="processo_robo_sem_pdf.pdf",
        processo="0000000-00.2026.8.00.0922",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=None,
    )

    resp = cliente_logado.get(f"/extratus/relatorios-robo/{job.id}/pdf")

    assert resp.status_code == 404

    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.id == job.id))
        sessao.commit()


def test_ver_pdf_relatorio_robo_job_inexistente_da_404(cliente_logado):
    resp = cliente_logado.get("/extratus/relatorios-robo/999999999/pdf")

    assert resp.status_code == 404
