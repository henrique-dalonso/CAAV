from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import delete

from app.ferramentas.extratus_aburesi.db.checagem_fila import (
    APROVADO,
    DUPLICADO_EM_ANDAMENTO,
    DUPLICADO_RELATORIO,
    NAO_ENCONTRADO,
    PENDENTE,
    aprovar_manualmente,
    atualizar_apos_checagem,
    contar_inconsistencias_novas,
    descartar,
    estado_por_nome,
    existe_conflito_de_processo,
    listar_aprovados_por_nome,
    listar_inconsistencias,
    mapear_solicitantes_por_arquivo,
    obter_registro,
    sincronizar_registros,
)
from app.ferramentas.extratus_aburesi.db.lotes import criar_lote, marcar_lote_concluido
from app.ferramentas.extratus_aburesi.db.models import ChecagemFila, ItemLoteRobo, LoteRobo, UploadFilaRobo
from app.plataforma.db.session import obter_sessao


PREFIXO_TESTE = "teste_checagem_aburesi_"
BATCH_ID_TESTE = "teste_batch_checagem_aburesi_9303"

USUARIO_A_TESTE = -9103
USUARIO_B_TESTE = -9104


@pytest.fixture
def limpar_uploads_teste():
    ids_criados = []

    yield ids_criados

    if ids_criados:
        with obter_sessao() as sessao:
            sessao.exec(delete(UploadFilaRobo).where(UploadFilaRobo.id.in_(ids_criados)))
            sessao.commit()


def _registrar_upload_com_horario(nome_arquivo, usuario_id, enviado_em):
    with obter_sessao() as sessao:
        upload = UploadFilaRobo(nome_arquivo=nome_arquivo, usuario_id=usuario_id, enviado_em=enviado_em)
        sessao.add(upload)
        sessao.commit()
        sessao.refresh(upload)
        return upload


@pytest.fixture
def limpar_checagem_teste():
    yield
    with obter_sessao() as sessao:
        sessao.exec(delete(ChecagemFila).where(ChecagemFila.nome_arquivo.like(f"{PREFIXO_TESTE}%")))
        sessao.commit()
        sessao.exec(delete(ItemLoteRobo).where(ItemLoteRobo.arquivo_pdf.like(f"{PREFIXO_TESTE}%")))
        sessao.exec(delete(LoteRobo).where(LoteRobo.batch_id == BATCH_ID_TESTE))
        sessao.commit()


def _sincronizar_so_de_teste(nomes_teste):
    """Ver comentário equivalente em test_checagem_fila.py (Extratus -
    Relatórios) — mesma preocupação de não apagar checagem de arquivo
    real de outro módulo/usuário ao rodar o teste."""
    nomes_reais_preservados = {
        nome for nome in estado_por_nome() if not nome.startswith(PREFIXO_TESTE)
    }
    return sincronizar_registros(nomes_teste | nomes_reais_preservados)


def test_mapear_solicitantes_por_arquivo_lista_vazia_devolve_dict_vazio():
    assert mapear_solicitantes_por_arquivo([]) == {}


def test_mapear_solicitantes_por_arquivo_casa_por_nome_e_horario(limpar_uploads_teste):
    agora = datetime.now()
    nome = f"{PREFIXO_TESTE}solicitante_simples.pdf"

    upload = _registrar_upload_com_horario(nome, USUARIO_A_TESTE, agora - timedelta(minutes=10))
    limpar_uploads_teste.append(upload.id)

    item = SimpleNamespace(id=1, arquivo_pdf=nome, criado_em=agora)

    resultado = mapear_solicitantes_por_arquivo([item])

    assert resultado == {1: USUARIO_A_TESTE}


def test_mapear_solicitantes_por_arquivo_nome_reutilizado_pega_o_envio_certo(limpar_uploads_teste):
    """Ver docstring equivalente em test_checagem_fila.py (Extratus -
    Relatórios)."""
    agora = datetime.now()
    nome = f"{PREFIXO_TESTE}pdf_reutilizado.pdf"

    upload_antigo = _registrar_upload_com_horario(nome, USUARIO_A_TESTE, agora - timedelta(days=2))
    upload_recente = _registrar_upload_com_horario(nome, USUARIO_B_TESTE, agora - timedelta(minutes=5))
    limpar_uploads_teste.extend([upload_antigo.id, upload_recente.id])

    item_antigo = SimpleNamespace(id=1, arquivo_pdf=nome, criado_em=agora - timedelta(days=2) + timedelta(minutes=10))
    item_recente = SimpleNamespace(id=2, arquivo_pdf=nome, criado_em=agora)

    resultado = mapear_solicitantes_por_arquivo([item_antigo, item_recente])

    assert resultado[1] == USUARIO_A_TESTE
    assert resultado[2] == USUARIO_B_TESTE


def test_mapear_solicitantes_por_arquivo_sem_upload_correspondente_fica_de_fora(limpar_uploads_teste):
    item = SimpleNamespace(id=99, arquivo_pdf=f"{PREFIXO_TESTE}nunca_foi_enviado_pela_tela.pdf", criado_em=datetime.now())

    resultado = mapear_solicitantes_por_arquivo([item])

    assert resultado == {}


def test_sincronizar_registros_cria_pendente_pra_nome_novo(limpar_checagem_teste):
    nome = f"{PREFIXO_TESTE}novo.pdf"

    pendentes = _sincronizar_so_de_teste({nome})
    nomes_pendentes = {p.nome_arquivo for p in pendentes}

    assert nome in nomes_pendentes
    assert next(p for p in pendentes if p.nome_arquivo == nome).status == PENDENTE


def test_existe_conflito_de_processo_true_quando_ja_aprovado_em_outro_arquivo(limpar_checagem_teste):
    processo = "4444444-44.2026.8.00.4444"
    nome_a = f"{PREFIXO_TESTE}a.pdf"
    nome_b = f"{PREFIXO_TESTE}b.pdf"

    registro_a = next(p for p in _sincronizar_so_de_teste({nome_a}) if p.nome_arquivo == nome_a)
    atualizar_apos_checagem(registro_a.id, APROVADO, processo, "alta", "ok")

    assert existe_conflito_de_processo(processo, exceto_nome_arquivo=nome_b) is True
    assert existe_conflito_de_processo(processo, exceto_nome_arquivo=nome_a) is False


def test_existe_conflito_de_processo_ignora_lote_ja_concluido(limpar_checagem_teste):
    processo = "5555555-55.2026.8.00.5555"
    lote = criar_lote(BATCH_ID_TESTE, [{
        "custom_id": "custom-concluido",
        "arquivo_pdf": f"{PREFIXO_TESTE}concluido.pdf",
        "processo_detectado": processo,
        "confianca_nivel": "alta",
        "confianca_motivo": "teste",
    }])
    marcar_lote_concluido(lote.id)

    assert existe_conflito_de_processo(processo, exceto_nome_arquivo="outro.pdf") is False


def test_listar_aprovados_por_nome_so_traz_aprovados(limpar_checagem_teste):
    nome_aprovado = f"{PREFIXO_TESTE}aprovado.pdf"
    nome_pendente = f"{PREFIXO_TESTE}pendente.pdf"

    registro_aprovado = next(
        p for p in _sincronizar_so_de_teste({nome_aprovado}) if p.nome_arquivo == nome_aprovado
    )
    atualizar_apos_checagem(registro_aprovado.id, APROVADO, "123", "alta", "ok")
    _sincronizar_so_de_teste({nome_aprovado, nome_pendente})

    aprovados = listar_aprovados_por_nome()

    assert nome_aprovado in aprovados
    assert nome_pendente not in aprovados
    assert aprovados[nome_aprovado].processo_detectado == "123"


def test_listar_inconsistencias_so_traz_os_3_tipos(limpar_checagem_teste):
    nome_duplicado = f"{PREFIXO_TESTE}duplicado.pdf"
    nome_aprovado = f"{PREFIXO_TESTE}aprovado_ok.pdf"

    registro_duplicado = next(
        p for p in _sincronizar_so_de_teste({nome_duplicado}) if p.nome_arquivo == nome_duplicado
    )
    atualizar_apos_checagem(registro_duplicado.id, DUPLICADO_RELATORIO, "123", "alta", "ok")

    registro_aprovado = next(
        p for p in _sincronizar_so_de_teste({nome_duplicado, nome_aprovado}) if p.nome_arquivo == nome_aprovado
    )
    atualizar_apos_checagem(registro_aprovado.id, APROVADO, "456", "alta", "ok")

    nomes = {r.nome_arquivo for r in listar_inconsistencias()}

    assert nome_duplicado in nomes
    assert nome_aprovado not in nomes


def test_aprovar_manualmente_libera_e_forca_revisao(limpar_checagem_teste):
    nome = f"{PREFIXO_TESTE}conferencia_aprovar.pdf"
    registro = next(p for p in _sincronizar_so_de_teste({nome}) if p.nome_arquivo == nome)
    atualizar_apos_checagem(registro.id, DUPLICADO_EM_ANDAMENTO, "789", "alta", "motivo original")

    atualizado = aprovar_manualmente(registro.id)

    assert atualizado.status == APROVADO
    assert atualizado.processo_detectado == "789"
    assert atualizado.confianca_nivel == "revisao"

    do_banco = obter_registro(registro.id)
    assert do_banco.status == APROVADO


def test_aprovar_manualmente_com_processo_informado_sobrescreve(limpar_checagem_teste):
    nome = f"{PREFIXO_TESTE}conferencia_processo_manual.pdf"
    registro = next(p for p in _sincronizar_so_de_teste({nome}) if p.nome_arquivo == nome)
    atualizar_apos_checagem(registro.id, NAO_ENCONTRADO, None, "revisao", "não achou nada")

    atualizado = aprovar_manualmente(registro.id, processo_manual="1111111-11.2026.8.00.1111")

    assert atualizado.processo_detectado == "1111111-11.2026.8.00.1111"
    assert atualizado.status == APROVADO


def test_aprovar_manualmente_registro_inexistente_nao_quebra(limpar_checagem_teste):
    assert aprovar_manualmente(999999999) is None


def test_descartar_apaga_a_linha(limpar_checagem_teste):
    nome = f"{PREFIXO_TESTE}conferencia_descartar.pdf"
    registro = next(p for p in _sincronizar_so_de_teste({nome}) if p.nome_arquivo == nome)
    atualizar_apos_checagem(registro.id, NAO_ENCONTRADO, None, "revisao", "não achou nada")

    descartar(registro.id)

    assert obter_registro(registro.id) is None


def test_descartar_registro_inexistente_nao_quebra(limpar_checagem_teste):
    descartar(999999999)


def test_checagem_aburesi_isolada_da_checagem_extratus(limpar_checagem_teste):
    """Confirma que a tabela é realmente separada (__tablename__
    checagemfila_aburesi) — um nome marcado aqui não deveria aparecer na
    checagem do outro módulo."""
    from app.ferramentas.extratus.db.checagem_fila import estado_por_nome as estado_extratus

    nome = f"{PREFIXO_TESTE}isolamento.pdf"
    _sincronizar_so_de_teste({nome})

    assert nome in estado_por_nome()
    assert nome not in estado_extratus()


def test_contar_inconsistencias_novas_conta_a_partir_do_timestamp(limpar_checagem_teste):
    desde = datetime.now() - timedelta(seconds=1)
    antes = contar_inconsistencias_novas(desde)

    nome = f"{PREFIXO_TESTE}badge_novo.pdf"
    registro = next(p for p in _sincronizar_so_de_teste({nome}) if p.nome_arquivo == nome)
    atualizar_apos_checagem(registro.id, NAO_ENCONTRADO, None, "revisao", "não achou nada")

    depois = contar_inconsistencias_novas(desde)

    assert depois == antes + 1
