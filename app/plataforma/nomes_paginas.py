"""Registro central de nomes amigáveis por URL — alimenta o botão
"Voltar pra X" no cabeçalho (base.html, ver pagina_voltar em
templates_util.py). Henrique, 2026-08-25: quer um botão dinâmico,
site inteiro, apontando pra última tela visitada com o NOME dela, não
só uma seta genérica.

Mesmo espírito de outros registros manuais já usados no projeto
(URL_CUSTOS_POR_FERRAMENTA, REGISTRO_NOTIFICACOES) — uma URL sem
entrada aqui simplesmente não aparece com nome (o botão mostra só
"Voltar", genérico, mas continua funcionando) — não quebra nada,
só fica menos claro. Comparação por PREFIXO mais longo que bate
primeiro, então sub-rotas (ex: /admin/custos/extratus-relatorios)
não precisam de entrada própria."""


def _rotulos_modulo(prefixo, nome_ferramenta):
    # Mesmos nomes das abas de navegação (_macros_extratus.html) —
    # "URGENTE" é o fluxo manual, "Robô" é o padrão automático. Henrique,
    # 2026-09-02: URLs sanitizadas — "Gerar Relatório URGENTE" saiu da
    # raiz do módulo (não existe mais rota nenhuma nela) pra
    # "/fila-urgentes", e "Fila do Robô" ganhou o sufixo "-robo" — sem
    # entrada de fallback pra raiz aqui de propósito, já que nenhuma tela
    # mora mais lá.
    return {
        f"{prefixo}/fila-urgentes": f"Gerar Relatório URGENTE — {nome_ferramenta}",
        f"{prefixo}/relatorios-urgentes": f"Relatórios URGENTES — {nome_ferramenta}",
        f"{prefixo}/fila-robo": f"Fila do Robô — {nome_ferramenta}",
        f"{prefixo}/relatorios-robo": f"Relatórios do Robô — {nome_ferramenta}",
    }


NOMES_POR_PREFIXO = {
    "/": "Início",
    "/perfil": "Perfil",
    "/admin/custos": "Custos",
    "/admin/ferramentas": "Ferramentas",
    "/admin/usuarios/novo": "Criar usuário",
    "/admin/usuarios": "Usuários",
    "/crivus": "Crivus",
    **_rotulos_modulo("/extratus", "Extratus - Relatórios"),
    **_rotulos_modulo("/extratus-aburesi", "Extratus - Aburesi"),
}


def nome_pagina(caminho):
    candidatos = [
        (prefixo, nome)
        for prefixo, nome in NOMES_POR_PREFIXO.items()
        if caminho == prefixo or (prefixo != "/" and caminho.startswith(prefixo + "/"))
    ]

    if not candidatos:
        return None

    _, nome = max(candidatos, key=lambda item: len(item[0]))
    return nome
