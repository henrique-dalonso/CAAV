import pytest
from sqlmodel import delete

from app.ferramentas.extratus.db.checagem_fila import (
    APROVADO,
    DUPLICADO_EM_ANDAMENTO,
    DUPLICADO_RELATORIO,
    NAO_ENCONTRADO,
    PENDENTE,
    aprovar_manualmente,
    atualizar_apos_checagem,
    descartar,
    estado_por_nome,
    existe_conflito_de_processo,
    listar_aprovados_por_nome,
    listar_inconsistencias,
    obter_registro,
    sincronizar_registros,
)
from app.ferramentas.extratus.db.lotes import criar_lote, marcar_lote_concluido
from app.ferramentas.extratus.db.models import ChecagemFila, ItemLoteMotor, LoteMotor
from app.plataforma.db.session import obter_sessao


PREFIXO_TESTE = "teste_checagem_"
BATCH_ID_TESTE = "teste_batch_checagem_9202"


@pytest.fixture
def limpar_checagem_teste():
    yield
    with obter_sessao() as sessao:
        sessao.exec(delete(ChecagemFila).where(ChecagemFila.nome_arquivo.like(f"{PREFIXO_TESTE}%")))
        sessao.commit()
        sessao.exec(delete(ItemLoteMotor).where(ItemLoteMotor.arquivo_pdf.like(f"{PREFIXO_TESTE}%")))
        sessao.exec(delete(LoteMotor).where(LoteMotor.batch_id == BATCH_ID_TESTE))
        sessao.commit()


def _sincronizar_so_de_teste(nomes_teste):
    """sincronizar_registros() apaga qualquer linha cujo nome não esteja
    no conjunto passado — chamar direto com só os nomes de teste, num
    banco de verdade (compartilhado com dados reais do Henrique), apagaria
    a checagem de qualquer arquivo real que esteja de fato na fila nesse
    momento. Esse wrapper busca o que já existe primeiro e preserva tudo
    que não é de teste, garantindo que só nomes com PREFIXO_TESTE somem."""
    nomes_reais_preservados = {
        nome for nome in estado_por_nome() if not nome.startswith(PREFIXO_TESTE)
    }
    return sincronizar_registros(nomes_teste | nomes_reais_preservados)


def test_sincronizar_registros_cria_pendente_pra_nome_novo(limpar_checagem_teste):
    nome = f"{PREFIXO_TESTE}novo.pdf"

    pendentes = _sincronizar_so_de_teste({nome})
    nomes_pendentes = {p.nome_arquivo for p in pendentes}

    assert nome in nomes_pendentes
    assert next(p for p in pendentes if p.nome_arquivo == nome).status == PENDENTE


def test_sincronizar_registros_remove_quem_saiu_da_pasta(limpar_checagem_teste):
    nome = f"{PREFIXO_TESTE}vai_sumir.pdf"
    _sincronizar_so_de_teste({nome})

    _sincronizar_so_de_teste(set())  # esse nome de teste não está mais "na pasta"

    assert estado_por_nome().get(nome) is None


def test_sincronizar_registros_nao_repete_quem_ja_foi_checado(limpar_checagem_teste):
    nome = f"{PREFIXO_TESTE}ja_checado.pdf"
    primeira_passada = _sincronizar_so_de_teste({nome})
    registro = next(p for p in primeira_passada if p.nome_arquivo == nome)
    atualizar_apos_checagem(registro.id, APROVADO, "123", "alta", "ok")

    segunda_passada = _sincronizar_so_de_teste({nome})

    assert nome not in {p.nome_arquivo for p in segunda_passada}  # já não está mais "pendente"
    assert estado_por_nome()[nome] == APROVADO


def test_atualizar_apos_checagem_grava_tudo(limpar_checagem_teste):
    nome = f"{PREFIXO_TESTE}atualiza.pdf"
    registro = next(p for p in _sincronizar_so_de_teste({nome}) if p.nome_arquivo == nome)

    atualizar_apos_checagem(registro.id, NAO_ENCONTRADO, None, "revisao", "não achou nada")

    with obter_sessao() as sessao:
        atualizado = sessao.get(ChecagemFila, registro.id)
        assert atualizado.status == NAO_ENCONTRADO
        assert atualizado.processo_detectado is None
        assert atualizado.confianca_motivo == "não achou nada"


def test_existe_conflito_de_processo_false_quando_nao_ha_nada(limpar_checagem_teste):
    assert existe_conflito_de_processo("9999999-99.2026.8.00.9999", exceto_nome_arquivo="qualquer.pdf") is False


def test_existe_conflito_de_processo_true_quando_ja_aprovado_em_outro_arquivo(limpar_checagem_teste):
    processo = "1111111-11.2026.8.00.1111"
    nome_a = f"{PREFIXO_TESTE}a.pdf"
    nome_b = f"{PREFIXO_TESTE}b.pdf"

    registro_a = next(p for p in _sincronizar_so_de_teste({nome_a}) if p.nome_arquivo == nome_a)
    atualizar_apos_checagem(registro_a.id, APROVADO, processo, "alta", "ok")

    assert existe_conflito_de_processo(processo, exceto_nome_arquivo=nome_b) is True
    # não conflita consigo mesmo
    assert existe_conflito_de_processo(processo, exceto_nome_arquivo=nome_a) is False


def test_existe_conflito_de_processo_true_quando_em_lote_ativo(limpar_checagem_teste):
    processo = "2222222-22.2026.8.00.2222"
    criar_lote(BATCH_ID_TESTE, [{
        "custom_id": "custom-conflito",
        "arquivo_pdf": f"{PREFIXO_TESTE}em_lote.pdf",
        "processo_detectado": processo,
        "confianca_nivel": "alta",
        "confianca_motivo": "teste",
    }])

    assert existe_conflito_de_processo(processo, exceto_nome_arquivo="outro.pdf") is True


def test_existe_conflito_de_processo_ignora_lote_ja_concluido(limpar_checagem_teste):
    """Um lote concluído significa que o relatório já foi gerado (ou
    tentado) — isso é assunto de DUPLICADO_RELATORIO (via Job), não
    DUPLICADO_EM_ANDAMENTO. Não deve contar aqui, senão o mesmo caso
    apareceria classificado errado."""
    processo = "3333333-33.2026.8.00.3333"
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
    assert atualizado.processo_detectado == "789"  # mantido, não veio processo manual
    assert atualizado.confianca_nivel == "revisao"  # nunca herda "alta" — sempre pede revisão humana depois

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
    descartar(999999999)  # não deve levantar exceção
