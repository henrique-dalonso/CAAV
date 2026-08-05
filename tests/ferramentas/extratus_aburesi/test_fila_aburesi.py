from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete

from app.ferramentas.extratus_aburesi.web.routes import fila
from app.plataforma.db.models import Usuario
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_TESTE = "teste_fila_upload_aburesi"
SENHA = "senhaTeste123"


@pytest.fixture
def cliente_logado():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    criar_usuario(
        nome="Teste Fila Upload Aburesi",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_fila_upload_aburesi@example.com",
        senha=SENHA,
        eh_admin=True,
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_USUARIO_TESTE, "senha": SENHA})

    yield cliente

    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


def _config_para(pasta):
    return {"motor_pasta_entrada": str(pasta)}


def test_upload_com_nome_repetido_nao_sobrescreve(cliente_logado, tmp_path):
    with patch.object(fila, "carregar_config", return_value=_config_para(tmp_path)):
        resp1 = cliente_logado.post(
            "/extratus-aburesi/fila/upload",
            files={"arquivos": ("processo.pdf", b"%PDF-1.4 conteudo original", "application/pdf")},
            follow_redirects=False,
        )
        assert resp1.status_code == 303
        assert "sucesso=" in resp1.headers["location"]

        resp2 = cliente_logado.post(
            "/extratus-aburesi/fila/upload",
            files={"arquivos": ("processo.pdf", b"%PDF-1.4 conteudo NOVO, nao deveria entrar", "application/pdf")},
            follow_redirects=False,
        )
        assert resp2.status_code == 303
        assert "erro=" in resp2.headers["location"]
        assert "existe" in resp2.headers["location"]

    conteudo_final = (tmp_path / "processo.pdf").read_bytes()
    assert conteudo_final == b"%PDF-1.4 conteudo original"


def test_upload_normal_ainda_funciona(cliente_logado, tmp_path):
    with patch.object(fila, "carregar_config", return_value=_config_para(tmp_path)):
        resp = cliente_logado.post(
            "/extratus-aburesi/fila/upload",
            files={"arquivos": ("novo.pdf", b"%PDF-1.4 arquivo novo", "application/pdf")},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "sucesso=" in resp.headers["location"]

    assert (tmp_path / "novo.pdf").read_bytes() == b"%PDF-1.4 arquivo novo"
