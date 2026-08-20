import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.ferramentas.extratus_aburesi.db.jobs import registrar_processado
from app.ferramentas.extratus_aburesi.db.models import Job
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
