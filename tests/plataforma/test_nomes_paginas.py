from app.plataforma.nomes_paginas import nome_pagina


def test_nome_pagina_raiz():
    assert nome_pagina("/") == "Início"


def test_nome_pagina_prefixo_exato():
    assert nome_pagina("/admin/custos") == "Custos"


def test_nome_pagina_sub_rota_usa_prefixo_mais_longo():
    assert nome_pagina("/admin/custos/extratus-relatorios") == "Custos"
    assert nome_pagina("/admin/ferramentas/extratus-aburesi") == "Ferramentas"


def test_nome_pagina_nao_confunde_extratus_com_extratus_aburesi():
    assert nome_pagina("/extratus-aburesi/fila-robo") == "Fila do Robô — Extratus - Aburesi"
    assert nome_pagina("/extratus/fila-robo") == "Fila do Robô — Extratus - Relatórios"


def test_nome_pagina_fluxo_manual_renomeado():
    # Henrique, 2026-09-02: "Gerar Relatório URGENTE" saiu da raiz do
    # módulo ("/extratus") pra "/extratus/fila-urgentes" na sanitização
    # de URLs — não existe mais rota nenhuma na raiz, então ela mesma
    # não tem mais nome (ver teste abaixo).
    assert nome_pagina("/extratus/fila-urgentes") == "Gerar Relatório URGENTE — Extratus - Relatórios"


def test_nome_pagina_raiz_de_modulo_nao_tem_mais_nome():
    assert nome_pagina("/extratus") is None


def test_nome_pagina_desconhecida_devolve_none():
    assert nome_pagina("/rota/que/nao/existe") is None
