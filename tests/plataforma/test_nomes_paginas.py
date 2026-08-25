from app.plataforma.nomes_paginas import nome_pagina


def test_nome_pagina_raiz():
    assert nome_pagina("/") == "Início"


def test_nome_pagina_prefixo_exato():
    assert nome_pagina("/admin/custos") == "Custos"


def test_nome_pagina_sub_rota_usa_prefixo_mais_longo():
    assert nome_pagina("/admin/custos/extratus-relatorios") == "Custos"
    assert nome_pagina("/admin/ferramentas/extratus-aburesi") == "Ferramentas"


def test_nome_pagina_nao_confunde_extratus_com_extratus_aburesi():
    assert nome_pagina("/extratus-aburesi/fila") == "Fila do Robô — Extratus - Aburesi"
    assert nome_pagina("/extratus/fila") == "Fila do Robô — Extratus - Relatórios"


def test_nome_pagina_raiz_de_modulo_e_o_fluxo_manual():
    assert nome_pagina("/extratus") == "Gerar Relatório URGENTE — Extratus - Relatórios"


def test_nome_pagina_desconhecida_devolve_none():
    assert nome_pagina("/rota/que/nao/existe") is None
