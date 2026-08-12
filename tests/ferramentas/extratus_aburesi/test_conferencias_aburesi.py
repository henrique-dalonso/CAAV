import pytest
from sqlmodel import delete

from app.ferramentas.extratus_aburesi.db.checagem_fila import DUPLICADO_RELATORIO
from app.ferramentas.extratus_aburesi.db.conferencias import registrar_decisao
from app.ferramentas.extratus_aburesi.db.models import RegistroConferencia
from app.plataforma.db.models import Usuario
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario


PREFIXO_TESTE = "teste_conferencia_aburesi_"
NOME_USUARIO_TESTE = "teste_conferencia_aburesi_usuario"


@pytest.fixture
def usuario_teste():
    with obter_sessao() as sessao:
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()

    usuario = criar_usuario(
        nome="Teste Conferência Aburesi",
        nome_usuario=NOME_USUARIO_TESTE,
        email="teste_conferencia_aburesi@example.com",
        senha="senhaTeste123",
        eh_admin=False,
    )

    yield usuario

    with obter_sessao() as sessao:
        sessao.exec(delete(RegistroConferencia).where(RegistroConferencia.nome_arquivo.like(f"{PREFIXO_TESTE}%")))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_USUARIO_TESTE))
        sessao.commit()


def test_registrar_decisao_grava_tudo(usuario_teste):
    nome = f"{PREFIXO_TESTE}arquivo.pdf"

    registro = registrar_decisao(
        nome,
        DUPLICADO_RELATORIO,
        "aprovado",
        usuario_teste.id,
        processo_informado="1234567-11.2026.8.00.1234",
    )

    assert registro.id is not None
    assert registro.nome_arquivo == nome
    assert registro.tipo_inconsistencia == DUPLICADO_RELATORIO
    assert registro.decisao == "aprovado"
    assert registro.usuario_id == usuario_teste.id
    assert registro.processo_informado == "1234567-11.2026.8.00.1234"

    with obter_sessao() as sessao:
        do_banco = sessao.get(RegistroConferencia, registro.id)
        assert do_banco is not None
        assert do_banco.decisao == "aprovado"


def test_registrar_decisao_sem_processo_informado(usuario_teste):
    nome = f"{PREFIXO_TESTE}sem_processo.pdf"

    registro = registrar_decisao(nome, DUPLICADO_RELATORIO, "descartado", usuario_teste.id)

    assert registro.processo_informado is None
    assert registro.decisao == "descartado"
