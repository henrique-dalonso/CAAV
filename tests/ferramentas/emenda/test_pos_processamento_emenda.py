from app.ferramentas.nucleo_relatorios.core.pos_processamento_emenda import processar_emenda


_DADOS_BASE = {
    "cnj": "0001234-56.2025.8.26.0100",
    "cliente": "Cliente Teste",
    "carteira": "MAPFRE",
    "autor": "Banco Teste",
    "reu": "Fulano de Tal",
    "comarca_vara": "3a Vara Civel",
    "decisao_resumo": "Resumo da decisao.",
    "prazo_dias": 4,
    "prazo_dias_uteis": False,
    "veiculo_em_nome_terceiro": True,
    "providencia_solicitada": "documento X",
    "email_carteira_descricao": "Descricao do e-mail.",
    "data_intimacao_confirmada": "03/11/2026",
}


def test_processa_emenda_com_data_completa_calcula_prazo_e_campos_extra():
    dados_finais, campos_extra = processar_emenda(_DADOS_BASE)

    assert dados_finais["prazo_data_final_calculada"] == "09/11/2026"
    assert dados_finais["prazo_ja_vencido"] is False
    assert dados_finais["prazo_aviso_calculo"] == ""

    assert campos_extra == {
        "emenda_data_intimacao": "03/11/2026",
        "emenda_prazo_dias": 4,
        "emenda_dias_uteis": False,
        "emenda_prazo_calculado": "09/11/2026",
        "emenda_prazo_ja_expirado": False,
        "emenda_veiculo_terceiro": True,
    }


def test_sem_data_de_intimacao_nao_quebra_e_sinaliza_aviso():
    """Regra do prompt: "não localizado nos autos" nunca pode derrubar o
    processamento inteiro — só sinaliza que o cálculo automático não
    rodou."""
    dados_sem_data = dict(_DADOS_BASE)
    dados_sem_data.pop("data_intimacao_confirmada")

    dados_finais, campos_extra = processar_emenda(dados_sem_data)

    assert dados_finais["prazo_aviso_calculo"] != ""
    assert dados_finais["prazo_data_final_calculada"] == ""
    assert dados_finais["prazo_ja_vencido"] is False

    assert campos_extra["emenda_data_intimacao"] is None
    assert campos_extra["emenda_prazo_calculado"] is None
    assert campos_extra["emenda_prazo_ja_expirado"] is None
    # veiculo_em_nome_terceiro continua sendo repassado mesmo sem prazo.
    assert campos_extra["emenda_veiculo_terceiro"] is True


def test_sem_prazo_dias_tambem_pula_o_calculo():
    dados_sem_prazo = dict(_DADOS_BASE)
    dados_sem_prazo["prazo_dias"] = None

    dados_finais, campos_extra = processar_emenda(dados_sem_prazo)

    assert dados_finais["prazo_aviso_calculo"] != ""
    assert campos_extra["emenda_prazo_dias"] is None


def test_divergencia_com_data_fatal_informada_e_repassada_pro_template():
    dados = dict(_DADOS_BASE)
    dados["data_fatal_email_interno"] = "10/11/2026"

    dados_finais, _ = processar_emenda(dados)

    assert dados_finais["prazo_diverge_do_informado"] is True
    assert dados_finais["prazo_data_informada_formatada"] == "10/11/2026"


def test_campos_opcionais_de_lista_ausentes_viram_lista_vazia():
    """Campo que docxtpl/Jinja precisa iterar (checklist_verificacao,
    documentos_ja_nos_autos) nunca pode ficar ausente do dict — vira
    `Undefined` e quebra o render do .docx inteiro. Ver
    _normalizar_campos_opcionais em pos_processamento_emenda.py."""
    dados_finais, _ = processar_emenda(_DADOS_BASE)

    assert dados_finais["checklist_verificacao"] == []
    assert dados_finais["documentos_ja_nos_autos"] == []
    assert dados_finais["processos_relacionados_flag"] is False


def test_campos_de_texto_opcionais_ausentes_viram_string_vazia():
    dados_finais, _ = processar_emenda(_DADOS_BASE)

    assert dados_finais["npjur"] == ""
    assert dados_finais["uf"] == ""
    assert dados_finais["identificador_carteira"] == ""


def test_nao_modifica_o_dict_original_recebido():
    """`processar_emenda` sempre trabalha numa cópia — quem chama
    (core/pipeline.py) não pode ver o dict original da IA mutado por
    baixo dos panos."""
    original = dict(_DADOS_BASE)
    processar_emenda(_DADOS_BASE)

    assert _DADOS_BASE == original
