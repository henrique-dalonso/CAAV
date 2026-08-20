from datetime import datetime, timedelta

from app.ferramentas.extratus.db import triagem_manual as db_triagem

# IDs negativos de propósito — não colidem com usuário real, mesmo padrão
# de tests/ferramentas/extratus/test_checagem_fila.py e test_jobs.py.
USUARIO_A = -9302
USUARIO_B = -9303


def _criar(nome, usuario_id=USUARIO_A):
    return db_triagem.criar_registro(nome, f"/tmp/{nome}", usuario_id)


def test_criar_e_obter_registro():
    registro = _criar("teste_triagem_criar.pdf")

    assert registro.status == "pendente"
    assert db_triagem.obter_registro(registro.id).nome_arquivo == "teste_triagem_criar.pdf"

    db_triagem.descartar(registro.id)


def test_atualizar_apos_triagem_grava_tudo():
    registro = _criar("teste_triagem_atualizar.pdf")

    atualizado = db_triagem.atualizar_apos_triagem(
        registro.id, db_triagem.NAO_ENCONTRADO, None, "revisao", "não achou nada",
    )

    assert atualizado.status == db_triagem.NAO_ENCONTRADO
    assert atualizado.confianca_motivo == "não achou nada"

    db_triagem.descartar(registro.id)


def test_concluir_grava_job_id():
    registro = _criar("teste_triagem_concluir.pdf")

    atualizado = db_triagem.concluir(registro.id, 12345)

    assert atualizado.status == db_triagem.CONCLUIDO
    assert atualizado.job_id == 12345

    db_triagem.descartar(registro.id)


def test_marcar_erro_grava_mensagem():
    registro = _criar("teste_triagem_erro.pdf")

    atualizado = db_triagem.marcar_erro(registro.id, "falha ao gerar")

    assert atualizado.status == db_triagem.ERRO
    assert atualizado.erro_mensagem == "falha ao gerar"

    db_triagem.descartar(registro.id)


def test_aprovar_manualmente_forca_revisao_e_status_processando():
    registro = _criar("teste_triagem_aprovar.pdf")
    db_triagem.atualizar_apos_triagem(registro.id, db_triagem.DUPLICADO_EM_ANDAMENTO, "789", "alta", "motivo original")

    atualizado = db_triagem.aprovar_manualmente(registro.id)

    assert atualizado.status == db_triagem.PROCESSANDO
    assert atualizado.processo_detectado == "789"  # mantido, não veio processo manual
    assert atualizado.confianca_nivel == "revisao"  # nunca herda "alta" automático

    db_triagem.descartar(registro.id)


def test_aprovar_manualmente_com_processo_informado_sobrescreve():
    registro = _criar("teste_triagem_aprovar_processo.pdf")
    db_triagem.atualizar_apos_triagem(registro.id, db_triagem.NAO_ENCONTRADO, None, "revisao", "não achou nada")

    atualizado = db_triagem.aprovar_manualmente(registro.id, processo_manual="1111111-11.2026.8.00.1111")

    assert atualizado.processo_detectado == "1111111-11.2026.8.00.1111"
    assert atualizado.status == db_triagem.PROCESSANDO

    db_triagem.descartar(registro.id)


def test_aprovar_manualmente_registro_inexistente_nao_quebra():
    assert db_triagem.aprovar_manualmente(999999999) is None


def test_aprovar_manualmente_segunda_chamada_nao_reprocessa():
    """Trava contra clique duplo em "Aprovar" (Henrique, 2026-08-13): a
    2ª chamada pro mesmo registro, depois que a 1ª já mudou o status pra
    "processando", não deve mais achar a linha pra atualizar — sem isso,
    o mesmo arquivo seria gerado 2x."""
    registro = _criar("teste_triagem_aprovar_duplo_clique.pdf")
    db_triagem.atualizar_apos_triagem(registro.id, db_triagem.NAO_ENCONTRADO, None, "revisao", "não achou nada")

    primeira = db_triagem.aprovar_manualmente(registro.id, processo_manual="9990001-01.2026.8.00.0001")
    segunda = db_triagem.aprovar_manualmente(registro.id, processo_manual="9990001-01.2026.8.00.0001")

    assert primeira is not None
    assert primeira.status == db_triagem.PROCESSANDO
    assert segunda is None

    do_banco = db_triagem.obter_registro(registro.id)
    assert do_banco.status == db_triagem.PROCESSANDO  # não foi sobrescrito nem voltou atrás

    db_triagem.descartar(registro.id)


def test_atualizar_apos_triagem_processando_com_processo_ja_ativo_vira_duplicado():
    """Trava real de banco (índice único parcial, db/session.py) contra
    2 arquivos DIFERENTES virando "processando" pro MESMO número de
    processo — cenário que a checagem de duplicidade (checagem_fila) não
    cobre pra 2 uploads manuais concorrentes entre si (Henrique,
    2026-08-13)."""
    processo = "9990002-02.2026.8.00.0002"
    primeiro = _criar("teste_triagem_processo_ativo_1.pdf")
    segundo = _criar("teste_triagem_processo_ativo_2.pdf")

    db_triagem.atualizar_apos_triagem(primeiro.id, db_triagem.PROCESSANDO, processo, "alta", "ok")
    resultado = db_triagem.atualizar_apos_triagem(segundo.id, db_triagem.PROCESSANDO, processo, "alta", "ok")

    assert resultado.status == db_triagem.DUPLICADO_EM_ANDAMENTO

    do_banco_primeiro = db_triagem.obter_registro(primeiro.id)
    assert do_banco_primeiro.status == db_triagem.PROCESSANDO  # o primeiro não foi mexido

    db_triagem.descartar(primeiro.id)
    db_triagem.descartar(segundo.id)


def test_aprovar_manualmente_com_processo_ja_ativo_em_outro_arquivo_vira_duplicado():
    processo = "9990003-03.2026.8.00.0003"
    ja_processando = _criar("teste_triagem_processo_ativo_aprovar_1.pdf")
    aguardando_conferencia = _criar("teste_triagem_processo_ativo_aprovar_2.pdf")

    db_triagem.atualizar_apos_triagem(ja_processando.id, db_triagem.PROCESSANDO, processo, "alta", "ok")
    db_triagem.atualizar_apos_triagem(
        aguardando_conferencia.id, db_triagem.NAO_ENCONTRADO, None, "revisao", "não achou nada",
    )

    resultado = db_triagem.aprovar_manualmente(aguardando_conferencia.id, processo_manual=processo)

    assert resultado is None

    do_banco = db_triagem.obter_registro(aguardando_conferencia.id)
    assert do_banco.status == db_triagem.DUPLICADO_EM_ANDAMENTO
    assert do_banco.processo_detectado == processo

    db_triagem.descartar(ja_processando.id)
    db_triagem.descartar(aguardando_conferencia.id)


def test_descartar_apaga_a_linha():
    registro = _criar("teste_triagem_descartar.pdf")

    db_triagem.descartar(registro.id)

    assert db_triagem.obter_registro(registro.id) is None


def test_descartar_registro_inexistente_nao_quebra():
    db_triagem.descartar(999999999)  # não deve levantar exceção


def test_listar_estado_do_usuario_separa_pendentes_e_processando_e_escopa_por_usuario():
    pendente_a = _criar("teste_triagem_estado_pendente_a.pdf", USUARIO_A)
    processando_a = _criar("teste_triagem_estado_processando_a.pdf", USUARIO_A)
    db_triagem.atualizar_apos_triagem(processando_a.id, db_triagem.PROCESSANDO, "123", "alta", "ok")
    pendente_b = _criar("teste_triagem_estado_pendente_b.pdf", USUARIO_B)

    estado_a = db_triagem.listar_estado_do_usuario(USUARIO_A)
    nomes_pendentes_a = {r.nome_arquivo for r in estado_a["pendentes"]}
    nomes_processando_a = {r.nome_arquivo for r in estado_a["processando"]}

    assert pendente_a.nome_arquivo in nomes_pendentes_a
    assert processando_a.nome_arquivo in nomes_processando_a
    assert pendente_b.nome_arquivo not in nomes_pendentes_a
    assert pendente_b.nome_arquivo not in nomes_processando_a

    db_triagem.descartar(pendente_a.id)
    db_triagem.descartar(processando_a.id)
    db_triagem.descartar(pendente_b.id)


def test_listar_estado_do_usuario_mantem_inconsistencia_em_pendentes():
    """Henrique, 2026-08-12: uma inconsistência NÃO some de Pendentes —
    continua lá (bolinha vermelha na tela), igual à Fila do Robô, até
    ser resolvida em Conferências."""
    duplicado = _criar("teste_triagem_estado_duplicado.pdf", USUARIO_A)
    db_triagem.atualizar_apos_triagem(duplicado.id, db_triagem.DUPLICADO_RELATORIO, "123", "alta", "ok")

    estado = db_triagem.listar_estado_do_usuario(USUARIO_A)
    nomes_pendentes = {r.nome_arquivo for r in estado["pendentes"]}
    nomes_processando = {r.nome_arquivo for r in estado["processando"]}

    assert duplicado.nome_arquivo in nomes_pendentes
    assert duplicado.nome_arquivo not in nomes_processando

    db_triagem.descartar(duplicado.id)


def test_listar_inconsistencias_do_usuario_escopa_por_usuario():
    duplicado_a = _criar("teste_triagem_inconsistencia_a.pdf", USUARIO_A)
    db_triagem.atualizar_apos_triagem(duplicado_a.id, db_triagem.DUPLICADO_RELATORIO, "123", "alta", "ok")
    duplicado_b = _criar("teste_triagem_inconsistencia_b.pdf", USUARIO_B)
    db_triagem.atualizar_apos_triagem(duplicado_b.id, db_triagem.NAO_ENCONTRADO, None, "revisao", "nada")

    inconsistencias_a = db_triagem.listar_inconsistencias_do_usuario(USUARIO_A)
    nomes_a = {r.nome_arquivo for r in inconsistencias_a}

    assert duplicado_a.nome_arquivo in nomes_a
    assert duplicado_b.nome_arquivo not in nomes_a

    db_triagem.descartar(duplicado_a.id)
    db_triagem.descartar(duplicado_b.id)


def test_contar_inconsistencias_novas_do_usuario_conta_so_desde_o_timestamp():
    desde = datetime.now() - timedelta(seconds=1)

    duplicado = _criar("teste_triagem_badge_novo.pdf", USUARIO_A)
    db_triagem.atualizar_apos_triagem(duplicado.id, db_triagem.DUPLICADO_RELATORIO, "123", "alta", "ok")

    assert db_triagem.contar_inconsistencias_novas_do_usuario(USUARIO_A, desde) == 1

    depois_de_ver = datetime.now()
    assert db_triagem.contar_inconsistencias_novas_do_usuario(USUARIO_A, depois_de_ver) == 0

    db_triagem.descartar(duplicado.id)


def test_listar_erros_do_usuario_traz_so_erro_do_proprio_usuario():
    erro_a = _criar("teste_triagem_minhas_erro_a.pdf", USUARIO_A)
    db_triagem.marcar_erro(erro_a.id, "Falha ao gerar o relatório.")
    erro_b = _criar("teste_triagem_minhas_erro_b.pdf", USUARIO_B)
    db_triagem.marcar_erro(erro_b.id, "Falha ao gerar o relatório.")
    pendente_a = _criar("teste_triagem_minhas_pendente_a.pdf", USUARIO_A)

    nomes_a = {r.nome_arquivo for r in db_triagem.listar_erros_do_usuario(USUARIO_A)}

    assert erro_a.nome_arquivo in nomes_a
    assert erro_b.nome_arquivo not in nomes_a
    assert pendente_a.nome_arquivo not in nomes_a

    db_triagem.descartar(erro_a.id)
    db_triagem.descartar(erro_b.id)
    db_triagem.descartar(pendente_a.id)


def test_contar_inconsistencias_novas_do_usuario_nao_conta_pendente_nem_outro_usuario():
    desde = datetime.now() - timedelta(seconds=1)

    pendente = _criar("teste_triagem_badge_pendente.pdf", USUARIO_A)
    duplicado_b = _criar("teste_triagem_badge_outro.pdf", USUARIO_B)
    db_triagem.atualizar_apos_triagem(duplicado_b.id, db_triagem.NAO_ENCONTRADO, None, "revisao", "nada")

    assert db_triagem.contar_inconsistencias_novas_do_usuario(USUARIO_A, desde) == 0

    db_triagem.descartar(pendente.id)
    db_triagem.descartar(duplicado_b.id)
