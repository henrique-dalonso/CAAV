from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import delete, select

from app.ferramentas.extratus_aburesi.db.checagem_fila import (
    APROVADO,
    DUPLICADO_RELATORIO,
    NAO_ENCONTRADO,
    PENDENTE,
    descartar,
    obter_registro,
)
from app.ferramentas.extratus_aburesi.db.models import ChecagemFila, RegistroConferencia
from app.ferramentas.extratus_aburesi.web.routes import fila
from app.plataforma.db.models import Ferramenta, Usuario, UsuarioFerramenta
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import criar_usuario
from app.plataforma.web.main import app


NOME_USUARIO_TESTE = "teste_fila_upload_aburesi"
SENHA = "senhaTeste123"
PREFIXO_TESTE = "teste_fila_conferencia_aburesi_"


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
    return {"robo_pasta_entrada": str(pasta)}


@pytest.fixture
def limpar_conferencia_teste():
    yield
    with obter_sessao() as sessao:
        sessao.exec(delete(RegistroConferencia).where(RegistroConferencia.nome_arquivo.like(f"{PREFIXO_TESTE}%")))
        sessao.exec(delete(ChecagemFila).where(ChecagemFila.nome_arquivo.like(f"{PREFIXO_TESTE}%")))
        sessao.commit()


def _criar_checagem(nome, status, processo=None):
    with obter_sessao() as sessao:
        registro = ChecagemFila(nome_arquivo=nome, status=status, processo_detectado=processo)
        sessao.add(registro)
        sessao.commit()
        sessao.refresh(registro)
        return registro


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


def test_remover_varios_limpa_conferencia_aberta_na_hora(cliente_logado, limpar_conferencia_teste, tmp_path):
    nome = f"{PREFIXO_TESTE}remover_com_conferencia.pdf"
    (tmp_path / nome).write_bytes(b"%PDF-1.4 conteudo")
    registro = _criar_checagem(nome, NAO_ENCONTRADO)

    with patch.object(fila, "carregar_config", return_value=_config_para(tmp_path)):
        resp = cliente_logado.post(
            "/extratus-aburesi/fila/remover-varios",
            data={"nomes": [nome]},
            follow_redirects=False,
        )

    assert "sucesso=" in resp.headers["location"]
    assert not (tmp_path / nome).exists()
    assert obter_registro(registro.id) is None

    with obter_sessao() as sessao:
        decisao = sessao.exec(
            select(RegistroConferencia).where(RegistroConferencia.nome_arquivo == nome)
        ).first()
        assert decisao is not None
        assert decisao.decisao == "descartado"
        assert decisao.tipo_inconsistencia == NAO_ENCONTRADO


def test_remover_varios_sem_conferencia_nao_cria_registro(cliente_logado, limpar_conferencia_teste, tmp_path):
    nome = f"{PREFIXO_TESTE}remover_sem_conferencia.pdf"
    (tmp_path / nome).write_bytes(b"%PDF-1.4 conteudo")
    registro = _criar_checagem(nome, PENDENTE)

    with patch.object(fila, "carregar_config", return_value=_config_para(tmp_path)):
        resp = cliente_logado.post(
            "/extratus-aburesi/fila/remover-varios",
            data={"nomes": [nome]},
            follow_redirects=False,
        )

    assert "sucesso=" in resp.headers["location"]
    assert not (tmp_path / nome).exists()
    assert obter_registro(registro.id) is None

    with obter_sessao() as sessao:
        decisao = sessao.exec(
            select(RegistroConferencia).where(RegistroConferencia.nome_arquivo == nome)
        ).first()
        assert decisao is None


def test_aprovar_conferencia_duplicado_libera_direto(cliente_logado, limpar_conferencia_teste):
    registro = _criar_checagem(f"{PREFIXO_TESTE}duplicado.pdf", DUPLICADO_RELATORIO, processo="123")

    resp = cliente_logado.post(f"/extratus-aburesi/fila/conferencia/{registro.id}/aprovar", follow_redirects=False)

    assert resp.status_code == 303
    assert "sucesso=" in resp.headers["location"]

    atualizado = obter_registro(registro.id)
    assert atualizado.status == APROVADO
    assert atualizado.processo_detectado == "123"

    with obter_sessao() as sessao:
        decisao = sessao.exec(
            select(RegistroConferencia).where(RegistroConferencia.nome_arquivo == registro.nome_arquivo)
        ).first()
        assert decisao is not None
        assert decisao.decisao == "aprovado"
        assert decisao.tipo_inconsistencia == DUPLICADO_RELATORIO


def test_aprovar_conferencia_sem_processo_quando_nao_encontrado_falha(cliente_logado, limpar_conferencia_teste):
    registro = _criar_checagem(f"{PREFIXO_TESTE}sem_processo.pdf", NAO_ENCONTRADO)

    resp = cliente_logado.post(f"/extratus-aburesi/fila/conferencia/{registro.id}/aprovar", follow_redirects=False)

    assert "erro=" in resp.headers["location"]
    assert obter_registro(registro.id).status == NAO_ENCONTRADO


def test_aprovar_conferencia_com_processo_invalido_falha(cliente_logado, limpar_conferencia_teste):
    registro = _criar_checagem(f"{PREFIXO_TESTE}processo_invalido.pdf", NAO_ENCONTRADO)

    resp = cliente_logado.post(
        f"/extratus-aburesi/fila/conferencia/{registro.id}/aprovar",
        data={"processo": "numero-qualquer"},
        follow_redirects=False,
    )

    assert "erro=" in resp.headers["location"]
    assert obter_registro(registro.id).status == NAO_ENCONTRADO


def test_aprovar_conferencia_com_processo_valido_libera(cliente_logado, limpar_conferencia_teste):
    registro = _criar_checagem(f"{PREFIXO_TESTE}com_processo.pdf", NAO_ENCONTRADO)

    resp = cliente_logado.post(
        f"/extratus-aburesi/fila/conferencia/{registro.id}/aprovar",
        data={"processo": "1234567-11.2026.8.00.1234"},
        follow_redirects=False,
    )

    assert "sucesso=" in resp.headers["location"]
    atualizado = obter_registro(registro.id)
    assert atualizado.status == APROVADO
    assert atualizado.processo_detectado == "1234567-11.2026.8.00.1234"


def test_descartar_conferencia_apaga_arquivo_e_registra(cliente_logado, limpar_conferencia_teste, tmp_path):
    nome = f"{PREFIXO_TESTE}descartar.pdf"
    (tmp_path / nome).write_bytes(b"%PDF-1.4 conteudo")
    registro = _criar_checagem(nome, DUPLICADO_RELATORIO, processo="999")

    with patch.object(fila, "carregar_config", return_value=_config_para(tmp_path)):
        resp = cliente_logado.post(f"/extratus-aburesi/fila/conferencia/{registro.id}/descartar", follow_redirects=False)

    assert "sucesso=" in resp.headers["location"]
    assert not (tmp_path / nome).exists()
    assert obter_registro(registro.id) is None

    with obter_sessao() as sessao:
        decisao = sessao.exec(
            select(RegistroConferencia).where(RegistroConferencia.nome_arquivo == nome)
        ).first()
        assert decisao is not None
        assert decisao.decisao == "descartado"


def test_descartar_todas_conferencias_remove_tudo(cliente_logado, limpar_conferencia_teste, tmp_path):
    # Ver comentário equivalente em tests/ferramentas/extratus/test_fila.py
    # (Extratus - Relatórios) — patcheia listar_inconsistencias de
    # propósito, senão a rota descartaria qualquer inconsistência real
    # pendente no banco compartilhado, não só as criadas aqui.
    nome1 = f"{PREFIXO_TESTE}lote1.pdf"
    nome2 = f"{PREFIXO_TESTE}lote2.pdf"
    (tmp_path / nome1).write_bytes(b"%PDF-1.4 conteudo 1")
    (tmp_path / nome2).write_bytes(b"%PDF-1.4 conteudo 2")
    registro1 = _criar_checagem(nome1, DUPLICADO_RELATORIO, processo="111")
    registro2 = _criar_checagem(nome2, NAO_ENCONTRADO)

    with patch.object(fila, "carregar_config", return_value=_config_para(tmp_path)), \
            patch.object(fila, "listar_inconsistencias", return_value=[registro1, registro2]):
        resp = cliente_logado.post("/extratus-aburesi/fila/conferencia/descartar-todas", follow_redirects=False)

    assert "sucesso=" in resp.headers["location"]
    assert not (tmp_path / nome1).exists()
    assert not (tmp_path / nome2).exists()
    assert obter_registro(registro1.id) is None
    assert obter_registro(registro2.id) is None

    with obter_sessao() as sessao:
        decisoes = sessao.exec(
            select(RegistroConferencia).where(RegistroConferencia.nome_arquivo.in_([nome1, nome2]))
        ).all()
        assert len(decisoes) == 2
        assert all(d.decisao == "descartado" for d in decisoes)


def test_descartar_todas_conferencias_sem_nada_da_aviso(cliente_logado):
    with patch.object(fila, "listar_inconsistencias", return_value=[]):
        resp = cliente_logado.post("/extratus-aburesi/fila/conferencia/descartar-todas", follow_redirects=False)

    assert "erro=" in resp.headers["location"]


def test_estado_fila_ordena_pendentes_vermelho_laranja_amarelo(cliente_logado, limpar_conferencia_teste, tmp_path):
    nome_vermelho = f"{PREFIXO_TESTE}zzz_vermelho.pdf"
    nome_laranja = f"{PREFIXO_TESTE}aaa_laranja.pdf"
    nome_amarelo = f"{PREFIXO_TESTE}mmm_amarelo.pdf"

    for nome in (nome_vermelho, nome_laranja, nome_amarelo):
        (tmp_path / nome).write_bytes(b"%PDF-1.4 conteudo")

    _criar_checagem(nome_vermelho, NAO_ENCONTRADO)
    _criar_checagem(nome_amarelo, APROVADO, processo="123")
    # nome_laranja fica sem linha de checagem nenhuma — é o que "ainda
    # checando" significa na prática (ver _estado_atual_fila).

    with patch.object(fila, "carregar_config", return_value=_config_para(tmp_path)), \
            patch.object(fila, "listar_arquivos_ja_reivindicados", return_value=set()):
        resp = cliente_logado.get("/extratus-aburesi/fila/estado")

    assert resp.status_code == 200
    nomes_na_ordem = [item["nome"] for item in resp.json()["pendentes"]]
    assert nomes_na_ordem.index(nome_vermelho) < nomes_na_ordem.index(nome_laranja)
    assert nomes_na_ordem.index(nome_laranja) < nomes_na_ordem.index(nome_amarelo)


def test_aprovar_conferencia_registro_inexistente_da_erro(cliente_logado):
    resp = cliente_logado.post("/extratus-aburesi/fila/conferencia/999999999/aprovar", follow_redirects=False)
    assert "erro=" in resp.headers["location"]


def test_descartar_conferencia_registro_inexistente_da_erro(cliente_logado):
    resp = cliente_logado.post("/extratus-aburesi/fila/conferencia/999999999/descartar", follow_redirects=False)
    assert "erro=" in resp.headers["location"]


def test_pagina_fila_mostra_badge_ambar_ate_resolver(cliente_logado, limpar_conferencia_teste):
    # Ver comentário equivalente em tests/ferramentas/extratus/test_fila.py
    # — mesma lógica.
    registro = _criar_checagem(f"{PREFIXO_TESTE}badge_ambar.pdf", NAO_ENCONTRADO)

    # Texto exato do badge nesse tab específico (não só a classe CSS —
    # ver comentário equivalente em tests/ferramentas/extratus/test_fila.py).
    badge_fila_robo = 'Fila do Robô <span class="contagem-aba contagem-aba-revisao">+1</span>'

    primeira_visita = cliente_logado.get("/extratus-aburesi/fila")
    assert primeira_visita.status_code == 200
    assert badge_fila_robo in primeira_visita.text

    segunda_visita = cliente_logado.get("/extratus-aburesi/fila")
    assert segunda_visita.status_code == 200
    assert badge_fila_robo in segunda_visita.text

    descartar(registro.id)

    depois_de_resolver = cliente_logado.get("/extratus-aburesi/fila")
    assert depois_de_resolver.status_code == 200
    assert badge_fila_robo not in depois_de_resolver.text


# --- Robô virou acesso padrão (Henrique, diretoria, 2026-08-19) ---

NOME_COLABORADOR_PADRAO_TESTE = "teste_fila_colaborador_padrao_aburesi"


def _apagar_colaborador_padrao_teste():
    # Apaga UsuarioFerramenta ANTES do Usuario — sem isso, o vínculo fica
    # órfão e "ressurge" num usuário novo que recicle o mesmo id (SQLite),
    # quebrando testes sem relação nenhuma com este arquivo.
    with obter_sessao() as sessao:
        usuario = sessao.exec(
            select(Usuario).where(Usuario.nome_usuario == NOME_COLABORADOR_PADRAO_TESTE)
        ).first()
        if usuario:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario.id))
        sessao.exec(delete(Usuario).where(Usuario.nome_usuario == NOME_COLABORADOR_PADRAO_TESTE))
        sessao.commit()


@pytest.fixture
def cliente_colaborador_padrao():
    """Colaborador comum, só com acesso básico à ferramenta (sem
    acesso_manual) — prova que a Fila do Robô não exige mais flag
    nenhuma, só acesso à ferramenta em si."""
    _apagar_colaborador_padrao_teste()

    with obter_sessao() as sessao:
        extratus_id = sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == "extratus-aburesi")).first()

    criar_usuario(
        nome="Teste Fila Colaborador Padrão",
        nome_usuario=NOME_COLABORADOR_PADRAO_TESTE,
        email="teste_fila_colaborador_padrao_aburesi@example.com",
        senha=SENHA,
        eh_admin=False,
        ferramenta_ids=[extratus_id],
    )

    cliente = TestClient(app)
    cliente.post("/login", data={"usuario_login": NOME_COLABORADOR_PADRAO_TESTE, "senha": SENHA})

    yield cliente

    _apagar_colaborador_padrao_teste()


def test_colaborador_sem_flag_nenhuma_acessa_fila_do_robo(cliente_colaborador_padrao):
    resposta = cliente_colaborador_padrao.get("/extratus-aburesi/fila")
    assert resposta.status_code == 200


def test_pagina_fila_mostra_bolinha_azul_pulsando_pra_quem_esta_processando(cliente_logado, tmp_path):
    """Ver docstring equivalente em tests/ferramentas/extratus/
    test_fila.py (Extratus - Relatórios) — mesma lógica."""
    nome_pdf = "teste_fila_processando_aburesi.pdf"
    (tmp_path / nome_pdf).write_bytes(b"%PDF-1.4 conteudo")

    with patch.object(fila, "carregar_config", return_value=_config_para(tmp_path)), \
            patch.object(fila, "listar_arquivos_ja_reivindicados", return_value={nome_pdf}):
        resp = cliente_logado.get("/extratus-aburesi/fila")

    assert resp.status_code == 200
    assert "bolinha-azul" in resp.text
    assert "bolinha-verde" not in resp.text
