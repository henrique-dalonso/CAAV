import json
from pathlib import Path

from app.plataforma.paths import PROJECT_ROOT


EXTRATUS_ROOT = PROJECT_ROOT / "app" / "ferramentas" / "extratus"

CONFIG_PATH = EXTRATUS_ROOT / "config" / "config.json"


CONFIG_PADRAO = {
    "pasta_entrada": "app/ferramentas/extratus/dados/entrada_pdfs",
    "pasta_saida": "app/ferramentas/extratus/dados/relatorios_prontos",
    "pasta_processados": "app/ferramentas/extratus/dados/processados",
    "pasta_revisao": "app/ferramentas/extratus/dados/revisao",
    "pasta_erros": "app/ferramentas/extratus/dados/erros",

    "limite_padrao": 0,

    "ia_provider": "claude",

    # Robô automático — essa bandeira liga/desliga o vigiar-pasta-sozinho
    # de verdade (robo_watcher.py, rodando em segundo plano desde o
    # startup do app) na tela de Configurações do Robô.
    "robo_ativo": False,

    # Pasta PRÓPRIA do robô — separada de pasta_entrada (que é a fila
    # manual/individual). Universal: todo mundo com acesso à aba Fila
    # do robô manda PDF pra cá, sem filtro por quem enviou.
    "robo_pasta_entrada": "app/ferramentas/extratus/dados/robo_entrada_pdfs",

    # Premissa de "economia estimada" na tela de Custos (admin) — não é
    # medido, é uma estimativa configurável de quanto tempo/dinheiro um
    # caso levaria pra ser feito manualmente, pra comparar com o custo
    # real de IA. Henrique, diretoria, 2026-08-26: valores de partida
    # sugeridos por mim, editáveis a qualquer momento na própria tela —
    # nunca apresentados como fato, só como premissa configurável. Fica
    # por ferramenta de propósito (Relatórios e Aburesi são produtos
    # diferentes, ver [[extratus-duas-frentes]] — um relatório completo
    # e um resumo rápido não deveriam levar o mesmo tempo na mão).
    "horas_estimadas_por_caso": 3.0,
    "valor_hora_profissional": 200.0,
}

PASTAS_CONFIGURAVEIS = [
    "pasta_entrada",
    "pasta_saida",
    "pasta_processados",
    "pasta_revisao",
    "pasta_erros",
    "robo_pasta_entrada",
]

# Henrique, diretoria, 2026-08-19: "Motor" virou "Robô" em tudo — migração
# automática pra quem já tinha um config.json salvo com os nomes antigos
# (literalmente "motor_..." — string já gravada em arquivo real, não dá
# pra "renomear" isso retroativamente), uma vez só (ver carregar_config
# abaixo). NÃO renomear as chaves à ESQUERDA aqui — são o nome antigo de
# verdade, do jeito que já está escrito no disco.
_CHAVES_CONFIG_ANTIGAS = {
    "motor_ativo": "robo_ativo",
    "motor_pasta_entrada": "robo_pasta_entrada",
}


# Henrique, 2026-08-11: "modo simulado" foi removido — só existe o
# provedor real "claude" hoje. Continua sendo uma tupla (em vez de uma
# constante única) porque um segundo provedor de IA REAL pode entrar
# aqui no futuro, "se for preciso".
PROVEDORES_IA_VALIDOS = ("claude",)


def _migrar_chaves_config_antigas(config_bruto):
    """Renomeia in-place as chaves antigas ("motor_...") pras novas
    ("robo_...") num dict de config recém-lido do disco — só move o
    valor se a chave nova ainda não tiver sido gravada por ninguém
    (setdefault), e sempre remove a antiga, pra não sobrar lixo duplicado
    no config.json na próxima gravação."""
    for chave_antiga, chave_nova in _CHAVES_CONFIG_ANTIGAS.items():
        if chave_antiga in config_bruto:
            config_bruto.setdefault(chave_nova, config_bruto.pop(chave_antiga))

    return config_bruto


def salvar_config(config):
    CONFIG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        CONFIG_PATH,
        "w",
        encoding="utf-8"
    ) as arquivo:
        json.dump(
            config,
            arquivo,
            ensure_ascii=False,
            indent=4
        )


def resolver_pastas(config):
    """Devolve uma cópia do config com as pastas como caminho absoluto,
    baseado na raiz do projeto — não em qual pasta o programa foi chamado.

    O arquivo config.json em si continua guardando só os nomes simples
    (ex: "entrada_pdfs"), pra ficar fácil de editar à mão.
    """
    resolvido = dict(config)

    for chave in PASTAS_CONFIGURAVEIS:
        valor = resolvido.get(chave)

        if valor:
            caminho = Path(valor)

            if not caminho.is_absolute():
                caminho = PROJECT_ROOT / caminho

            resolvido[chave] = str(caminho)

    return resolvido


def carregar_config():
    if not CONFIG_PATH.exists():
        config = CONFIG_PADRAO.copy()
        salvar_config(config)
        return resolver_pastas(config)

    try:
        with open(
            CONFIG_PATH,
            "r",
            encoding="utf-8"
        ) as arquivo:
            config_usuario = json.load(arquivo)

    except (
        json.JSONDecodeError,
        OSError
    ):
        config = CONFIG_PADRAO.copy()
        salvar_config(config)
        return resolver_pastas(config)

    if not isinstance(config_usuario, dict):
        config = CONFIG_PADRAO.copy()
        salvar_config(config)
        return resolver_pastas(config)

    # Comparação precisa ser contra uma CÓPIA de antes da migração —
    # _migrar_chaves_config_antigas muda config_usuario in-place, então
    # comparar depois seria comparar o dict já migrado com ele mesmo,
    # nunca detectando que teve mudança nenhuma (achado real: o
    # config.json nunca limpava as chaves antigas sozinho por causa
    # disso, mesmo com o valor certo já em uso na memória).
    config_usuario_original = dict(config_usuario)
    config_usuario = _migrar_chaves_config_antigas(config_usuario)

    config = CONFIG_PADRAO.copy()
    config.update(config_usuario)

    if config != config_usuario_original:
        salvar_config(config)

    return resolver_pastas(config)


def definir_robo_ativo(ativo: bool):
    """Liga/desliga a bandeira do robô automático — lê e grava o
    config.json em bruto (caminhos relativos), nunca a versão resolvida
    em caminho absoluto que carregar_config() devolve, senão corrompe o
    arquivo pra quem edita à mão depois.
    """
    config_bruto = {}

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as arquivo:
                lido = json.load(arquivo)

            if isinstance(lido, dict):
                config_bruto = _migrar_chaves_config_antigas(lido)
        except (json.JSONDecodeError, OSError):
            config_bruto = {}

    config = CONFIG_PADRAO.copy()
    config.update(config_bruto)
    config["robo_ativo"] = bool(ativo)

    salvar_config(config)

    return config["robo_ativo"]


def _carregar_config_bruta():
    if not CONFIG_PATH.exists():
        return {}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as arquivo:
            lido = json.load(arquivo)

        if isinstance(lido, dict):
            return _migrar_chaves_config_antigas(lido)
    except (json.JSONDecodeError, OSError):
        pass

    return {}


def carregar_config_bruto():
    """Igual carregar_config(), mas SEM resolver as pastas pra caminho
    absoluto — usado pra preencher formulário de edição, pra não gravar
    de volta um caminho amarrado a essa máquina quando o admin salva sem
    mudar o valor exibido."""
    config = CONFIG_PADRAO.copy()
    config.update(_carregar_config_bruta())
    return config


def atualizar_config_robo(pasta_entrada=None, ia_provider=None):
    """Edita as configurações do robô (pasta própria + provedor de IA) —
    mesmo padrão de leitura/gravação em bruto do definir_robo_ativo, pra
    não sobrescrever o config.json com caminhos já resolvidos em absoluto.
    """
    if ia_provider is not None and ia_provider not in PROVEDORES_IA_VALIDOS:
        raise ValueError(f"Provedor de IA inválido: {ia_provider!r}")

    config = CONFIG_PADRAO.copy()
    config.update(_carregar_config_bruta())

    if pasta_entrada is not None:
        pasta_entrada = pasta_entrada.strip()

        if not pasta_entrada:
            raise ValueError("Pasta de entrada do Robô não pode ficar vazia.")

        config["robo_pasta_entrada"] = pasta_entrada

    if ia_provider is not None:
        config["ia_provider"] = ia_provider

    salvar_config(config)

    return config


def atualizar_parametros_economia(horas_estimadas_por_caso, valor_hora_profissional):
    """Edita a premissa de "economia estimada" da tela de Custos (admin) —
    mesmo padrão de leitura/gravação em bruto das funções acima. Os dois
    valores precisam ser positivos (uma premissa zero/negativa não faz
    sentido pra estimar economia nenhuma)."""
    if horas_estimadas_por_caso <= 0:
        raise ValueError("Horas estimadas por caso precisa ser maior que zero.")

    if valor_hora_profissional <= 0:
        raise ValueError("Valor da hora do profissional precisa ser maior que zero.")

    config = CONFIG_PADRAO.copy()
    config.update(_carregar_config_bruta())

    config["horas_estimadas_por_caso"] = float(horas_estimadas_por_caso)
    config["valor_hora_profissional"] = float(valor_hora_profissional)

    salvar_config(config)

    return config
