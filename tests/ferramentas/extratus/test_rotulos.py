from app.ferramentas.extratus.web.rotulos import rotulo_erro, rotulo_status


def test_rotulo_status_mapeia_conhecidos():
    assert rotulo_status("sucesso") == "Sucesso"
    assert rotulo_status("revisao") == "Revisão"
    assert rotulo_status("erro") == "Erro"


def test_rotulo_status_desconhecido_devolve_o_proprio_valor():
    # Se aparecer um status novo que ainda não tem tradução, mostra o
    # valor cru em vez de quebrar ou esconder a informação.
    assert rotulo_status("nunca_visto") == "nunca_visto"


def test_rotulo_erro_mapeia_conhecidos():
    assert rotulo_erro("erro_pdf") == "Falha ao ler o PDF"
    assert rotulo_erro("erro_ia") == "Falha ao gerar o relatório"
    assert rotulo_erro("erro_docx") == "Falha ao salvar o relatório"
    assert rotulo_erro("erro_movimentacao") == "Falha ao mover o arquivo"


def test_rotulo_erro_desconhecido_devolve_mensagem_generica():
    assert rotulo_erro("tipo_nunca_visto") == "Falha no processamento"
