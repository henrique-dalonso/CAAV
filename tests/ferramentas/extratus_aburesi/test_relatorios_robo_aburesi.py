import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.ferramentas.extratus_aburesi.db.checagem_fila import registrar_upload
from app.ferramentas.extratus_aburesi.db.jobs import registrar_erro, registrar_processado
from app.ferramentas.extratus_aburesi.db.models import Job, UploadFilaRobo
from app.plataforma.db.models import Ferramenta, Usuario, UsuarioFerramenta
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_TESTE = "teste_relatorios_robo_aburesi"
NOME_USUARIO_SEM_FILA = "teste_relrobo_sem_fila_aburesi"
SENHA = "senhaTeste123"

# Ver comentário equivalente em tests/ferramentas/extratus/
# test_relatorios_robo.py (Extratus - Relatórios) — mesma lógica.
USUARIO_TESTE = -9010


@pytest.fixture
def cliente_logado():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Relatórios do Robô Aburesi",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_relatorios_robo_aburesi@example.com",
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
def cliente_nao_admin_logado():
    """Ver docstring equivalente em tests/ferramentas/extratus/
    test_relatorios_robo.py (Extratus - Relatórios) — mesma lógica."""
    nome_usuario = "teste_relrobo_nao_admin_padrao_aburesi"

    with obter_sessao() as sessao:
        usuario_antigo = sessao.exec(select(Usuario.id).where(Usuario.nome_usuario == nome_usuario)).first()
        if usuario_antigo:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_antigo))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == nome_usuario))
        sessao.commit()
        extratus_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "extratus-aburesi")).first()

    usuario = criar_usuario(
        nome="Teste RelRobo Não-Admin Padrão Aburesi", nome_usuario=nome_usuario,
        email="teste_relrobo_nao_admin_padrao_aburesi@example.com", senha=SENHA, eh_admin=False,
        ferramenta_ids=[extratus_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": nome_usuario, "senha": SENHA})

    yield cliente, usuario.id

    with obter_sessao() as sessao:
        sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario.id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == nome_usuario))
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

    resp = cliente.get("/extratus-aburesi/relatorios-robo", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_pagina_relatorios_robo_so_lista_jobs_do_robo(cliente_logado, limpar_jobs_criados):
    job_robo = registrar_processado(
        arquivo_pdf="teste_pagina_relatorios_robo_aburesi.pdf",
        processo="0000000-00.2026.8.00.0043",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    job_manual = registrar_processado(
        arquivo_pdf="teste_pagina_relatorios_robo_manual_aburesi.pdf",
        processo="0000000-00.2026.8.00.0044",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=USUARIO_TESTE,
    )
    limpar_jobs_criados.extend([job_robo.id, job_manual.id])

    resp = cliente_logado.get("/extratus-aburesi/relatorios-robo")

    assert resp.status_code == 200
    assert "teste_pagina_relatorios_robo_aburesi.pdf" in resp.text
    assert "teste_pagina_relatorios_robo_manual_aburesi.pdf" not in resp.text


def test_pagina_relatorios_robo_mostra_quem_solicitou(cliente_logado, limpar_jobs_criados):
    """Ver docstring equivalente em tests/ferramentas/extratus/
    test_relatorios_robo.py (Extratus - Relatórios)."""
    with obter_sessao() as sessao:
        usuario_id_logado = sessao.exec(
            select(Usuario.id).where(Usuario.nome_usuario == NOME_USUARIO_TESTE)
        ).first()

    job_robo = registrar_processado(
        arquivo_pdf="teste_relrobo_solicitante_aburesi.pdf",
        processo="0000000-00.2026.8.00.0045",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
        solicitante_id=usuario_id_logado,
    )
    limpar_jobs_criados.append(job_robo.id)

    resp = cliente_logado.get("/extratus-aburesi/relatorios-robo")

    assert resp.status_code == 200
    assert "Solicitado por: Teste Relatórios do Robô Aburesi" in resp.text
    assert f'value="{usuario_id_logado}"' in resp.text


def test_pagina_relatorios_robo_mostra_quem_solicitou_por_fallback(cliente_logado, limpar_jobs_criados):
    """Ver docstring equivalente em tests/ferramentas/extratus/
    test_relatorios_robo.py (Extratus - Relatórios)."""
    with obter_sessao() as sessao:
        usuario_id_logado = sessao.exec(
            select(Usuario.id).where(Usuario.nome_usuario == NOME_USUARIO_TESTE)
        ).first()

    registrar_upload("teste_relrobo_solicitante_fallback_aburesi.pdf", usuario_id_logado)

    job_robo = registrar_processado(
        arquivo_pdf="teste_relrobo_solicitante_fallback_aburesi.pdf",
        processo="0000000-00.2026.8.00.0046",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
        solicitante_id=None,
    )
    limpar_jobs_criados.append(job_robo.id)

    resp = cliente_logado.get("/extratus-aburesi/relatorios-robo")

    assert resp.status_code == 200
    assert "Solicitado por: Teste Relatórios do Robô Aburesi" in resp.text

    with obter_sessao() as sessao:
        sessao.exec(delete(UploadFilaRobo).where(UploadFilaRobo.nome_arquivo == "teste_relrobo_solicitante_fallback_aburesi.pdf"))
        sessao.commit()


def test_pagina_relatorios_robo_acessivel_sem_acesso_a_fila():
    """Ver comentário equivalente em tests/ferramentas/extratus/
    test_relatorios_robo.py (Extratus - Relatórios) — mesma lógica."""
    with obter_sessao() as sessao:
        usuario_antigo = sessao.exec(select(Usuario.id).where(Usuario.nome_usuario == NOME_USUARIO_SEM_FILA)).first()
        if usuario_antigo:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_antigo))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_SEM_FILA))
        sessao.commit()
        extratus_aburesi_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "extratus-aburesi")).first()

    criar_usuario(
        nome="Teste RelRobo Sem Fila Aburesi",
        nome_usuario=NOME_USUARIO_SEM_FILA,
        email="teste_relrobo_sem_fila_aburesi@example.com",
        senha=SENHA,
        eh_admin=False,
        ferramenta_ids=[extratus_aburesi_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_SEM_FILA, "senha": SENHA})

    resp = cliente.get("/extratus-aburesi/relatorios-robo")

    assert resp.status_code == 200

    with obter_sessao() as sessao:
        usuario_id = sessao.exec(select(Usuario.id).where(Usuario.nome_usuario == NOME_USUARIO_SEM_FILA)).first()
        if usuario_id:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_SEM_FILA))
        sessao.commit()


def test_pagina_relatorios_manual_nao_lista_jobs_do_robo(cliente_logado, limpar_jobs_criados):
    job_robo = registrar_processado(
        arquivo_pdf="teste_pagina_relatorios_manual_robo_aburesi.pdf",
        processo="0000000-00.2026.8.00.0045",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.append(job_robo.id)

    resp = cliente_logado.get("/extratus-aburesi/relatorios")

    assert resp.status_code == 200
    assert "teste_pagina_relatorios_manual_robo_aburesi.pdf" not in resp.text


def test_marcar_notificacao_resolvida_robo_route_funciona_sem_dono(cliente_logado, limpar_jobs_criados):
    job = registrar_processado(
        arquivo_pdf="teste_relrobo_marcar_resolvida_aburesi.pdf",
        processo="0000000-00.2026.8.00.0091",
        relatorio_path=None,
        destino_pdf=None,
        confianca="alta",
        usuario_id=None,
    )
    limpar_jobs_criados.append(job.id)

    resp = cliente_logado.post(f"/extratus-aburesi/relatorios-robo/{job.id}/marcar-notificacao-resolvida")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    with obter_sessao() as sessao:
        atualizado = sessao.get(Job, job.id)
        assert atualizado.notificacao_resolvida is True


def test_marcar_notificacao_resolvida_robo_route_job_inexistente_da_404(cliente_logado):
    resp = cliente_logado.post("/extratus-aburesi/relatorios-robo/999999999/marcar-notificacao-resolvida")

    assert resp.status_code == 404


def test_excluir_relatorio_robo_admin_apaga_de_verdade(cliente_logado):
    job = registrar_processado(
        arquivo_pdf="teste_excluir_relatorio_robo_admin_aburesi.pdf",
        processo="0000000-00.2026.8.00.0914",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=None,
    )

    resp = cliente_logado.post(f"/extratus-aburesi/relatorios-robo/{job.id}/excluir", follow_redirects=False)

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]

    with obter_sessao() as sessao:
        assert sessao.get(Job, job.id) is None


def test_excluir_relatorio_robo_inexistente_redireciona_com_erro(cliente_logado):
    resp = cliente_logado.post("/extratus-aburesi/relatorios-robo/999999999/excluir", follow_redirects=False)

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]


def test_excluir_relatorio_robo_recusa_nao_admin():
    """Ver docstring equivalente em tests/ferramentas/extratus/
    test_relatorios_robo.py (Extratus - Relatórios) — mesma lógica."""
    nome_usuario = "teste_relrobo_excluir_nao_admin_aburesi"

    with obter_sessao() as sessao:
        usuario_antigo = sessao.exec(select(Usuario.id).where(Usuario.nome_usuario == nome_usuario)).first()
        if usuario_antigo:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_antigo))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == nome_usuario))
        sessao.commit()
        extratus_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "extratus-aburesi")).first()

    criar_usuario(
        nome="Teste RelRobo Excluir Não-Admin Aburesi", nome_usuario=nome_usuario,
        email="teste_relrobo_excluir_nao_admin_aburesi@example.com", senha=SENHA, eh_admin=False,
        ferramenta_ids=[extratus_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": nome_usuario, "senha": SENHA})

    job = registrar_processado(
        arquivo_pdf="teste_excluir_relatorio_robo_nao_admin_aburesi.pdf",
        processo="0000000-00.2026.8.00.0915",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=None,
    )

    resp = cliente.post(f"/extratus-aburesi/relatorios-robo/{job.id}/excluir")

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
    pdf_origem = tmp_path / "processo_robo_original_aburesi.pdf"
    pdf_origem.write_bytes(b"%PDF-1.4 conteudo de teste robo aburesi")

    job = registrar_processado(
        arquivo_pdf="processo_robo_original_aburesi.pdf",
        processo="0000000-00.2026.8.00.0921",
        relatorio_path=None, destino_pdf=str(pdf_origem), confianca="alta",
        usuario_id=None,
    )

    resp = cliente_logado.get(f"/extratus-aburesi/relatorios-robo/{job.id}/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == b"%PDF-1.4 conteudo de teste robo aburesi"

    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.id == job.id))
        sessao.commit()


def test_ver_pdf_relatorio_robo_sem_destino_pdf_da_404(cliente_logado):
    job = registrar_processado(
        arquivo_pdf="processo_robo_sem_pdf_aburesi.pdf",
        processo="0000000-00.2026.8.00.0922",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=None,
    )

    resp = cliente_logado.get(f"/extratus-aburesi/relatorios-robo/{job.id}/pdf")

    assert resp.status_code == 404

    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.id == job.id))
        sessao.commit()


def test_ver_pdf_relatorio_robo_job_inexistente_da_404(cliente_logado):
    resp = cliente_logado.get("/extratus-aburesi/relatorios-robo/999999999/pdf")

    assert resp.status_code == 404


# --- Filtro padrão "Solicitado por" + aviso de "sem solicitações"
# (Henrique, 2026-09-02) — ver docstrings equivalentes em
# tests/ferramentas/extratus/test_relatorios_robo.py. ---

def test_nao_admin_com_solicitacao_ve_filtro_padrao_preenchido(cliente_nao_admin_logado, limpar_jobs_criados):
    cliente, usuario_id = cliente_nao_admin_logado

    job = registrar_processado(
        arquivo_pdf="teste_relrobo_padrao_preenchido_aburesi.pdf",
        processo="0000000-00.2026.8.00.0951",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=None, solicitante_id=usuario_id,
    )
    limpar_jobs_criados.append(job.id)

    resp = cliente.get("/extratus-aburesi/relatorios-robo")

    assert resp.status_code == 200
    assert f'data-padrao="{usuario_id}"' in resp.text
    assert 'id="aviso-sem-solicitacoes-robo" data-ativo="false"' in resp.text


def test_nao_admin_sem_nenhuma_solicitacao_ve_aviso_dedicado(cliente_nao_admin_logado, limpar_jobs_criados):
    cliente, usuario_id = cliente_nao_admin_logado

    job_de_outro = registrar_processado(
        arquivo_pdf="teste_relrobo_padrao_de_outro_aburesi.pdf",
        processo="0000000-00.2026.8.00.0952",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=None, solicitante_id=USUARIO_TESTE,
    )
    limpar_jobs_criados.append(job_de_outro.id)

    resp = cliente.get("/extratus-aburesi/relatorios-robo")

    assert resp.status_code == 200
    assert 'data-padrao=""' in resp.text
    assert 'id="aviso-sem-solicitacoes-robo" data-ativo="true"' in resp.text
    assert "Você ainda não solicitou nenhum relatório ao Robô" in resp.text
    assert f'value="{usuario_id}"' not in resp.text


def test_admin_nunca_recebe_filtro_padrao(cliente_logado, limpar_jobs_criados):
    job_de_outro = registrar_processado(
        arquivo_pdf="teste_relrobo_admin_sem_padrao_aburesi.pdf",
        processo="0000000-00.2026.8.00.0953",
        relatorio_path=None, destino_pdf=None, confianca="alta",
        usuario_id=None, solicitante_id=USUARIO_TESTE,
    )
    limpar_jobs_criados.append(job_de_outro.id)

    resp = cliente_logado.get("/extratus-aburesi/relatorios-robo")

    assert resp.status_code == 200
    assert 'data-padrao=""' in resp.text
    assert 'id="aviso-sem-solicitacoes-robo" data-ativo="false"' in resp.text


# --- Baixar em lote (.zip) e excluir em lote (Henrique, 2026-09-02) ---

def test_baixar_lote_inclui_sucesso_e_revisao_exclui_erro(cliente_logado, limpar_jobs_criados, tmp_path):
    caminho_sucesso = tmp_path / "teste_lote_sucesso_aburesi.docx"
    caminho_sucesso.write_text("conteudo sucesso")
    caminho_revisao = tmp_path / "teste_lote_revisao_aburesi.docx"
    caminho_revisao.write_text("conteudo revisao")

    job_sucesso = registrar_processado(
        arquivo_pdf="teste_lote_sucesso_aburesi.pdf", processo="0000000-00.2026.8.00.0960",
        relatorio_path=str(caminho_sucesso), destino_pdf=None, confianca="alta", usuario_id=None,
    )
    job_revisao = registrar_processado(
        arquivo_pdf="teste_lote_revisao_aburesi.pdf", processo="0000000-00.2026.8.00.0961",
        relatorio_path=str(caminho_revisao), destino_pdf=None, confianca="media", usuario_id=None,
    )
    job_erro = registrar_erro(
        arquivo_pdf="teste_lote_erro_aburesi.pdf", processo=None, tipo_erro="erro_ia",
        erro_mensagem="falha simulada", usuario_id=None,
    )
    limpar_jobs_criados.extend([job_sucesso.id, job_revisao.id, job_erro.id])

    resp = cliente_logado.post(
        "/extratus-aburesi/relatorios-robo/baixar-lote",
        data={"ids": [job_sucesso.id, job_revisao.id, job_erro.id]},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zip_arquivo:
        nomes = zip_arquivo.namelist()
        assert "teste_lote_sucesso_aburesi.docx" in nomes
        assert "teste_lote_revisao_aburesi.docx" in nomes
        assert len(nomes) == 2


def test_baixar_lote_sem_nenhum_arquivo_redireciona_com_erro(cliente_logado, limpar_jobs_criados):
    job_erro = registrar_erro(
        arquivo_pdf="teste_lote_so_erro_aburesi.pdf", processo=None, tipo_erro="erro_ia",
        erro_mensagem="falha simulada", usuario_id=None,
    )
    limpar_jobs_criados.append(job_erro.id)

    resp = cliente_logado.post(
        "/extratus-aburesi/relatorios-robo/baixar-lote",
        data={"ids": [job_erro.id]},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "erro=" in resp.headers["location"]


def test_excluir_lote_admin_apaga_varios_de_uma_vez(cliente_logado):
    job1 = registrar_processado(
        arquivo_pdf="teste_lote_excluir_1_aburesi.pdf", processo="0000000-00.2026.8.00.0970",
        relatorio_path=None, destino_pdf=None, confianca="alta", usuario_id=None,
    )
    job2 = registrar_processado(
        arquivo_pdf="teste_lote_excluir_2_aburesi.pdf", processo="0000000-00.2026.8.00.0971",
        relatorio_path=None, destino_pdf=None, confianca="alta", usuario_id=None,
    )

    resp = cliente_logado.post(
        "/extratus-aburesi/relatorios-robo/excluir-lote",
        data={"ids": [job1.id, job2.id]},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]

    with obter_sessao() as sessao:
        assert sessao.get(Job, job1.id) is None
        assert sessao.get(Job, job2.id) is None


def test_excluir_lote_recusa_nao_admin(cliente_nao_admin_logado, limpar_jobs_criados):
    cliente, _usuario_id = cliente_nao_admin_logado

    job = registrar_processado(
        arquivo_pdf="teste_lote_excluir_nao_admin_aburesi.pdf", processo="0000000-00.2026.8.00.0972",
        relatorio_path=None, destino_pdf=None, confianca="alta", usuario_id=None,
    )
    limpar_jobs_criados.append(job.id)

    resp = cliente.post("/extratus-aburesi/relatorios-robo/excluir-lote", data={"ids": [job.id]})

    assert resp.status_code == 403

    with obter_sessao() as sessao:
        assert sessao.get(Job, job.id) is not None
