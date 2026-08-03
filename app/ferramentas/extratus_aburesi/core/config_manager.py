import json
from pathlib import Path

from app.plataforma.paths import PROJECT_ROOT


EXTRATUS_ROOT = PROJECT_ROOT / "app" / "ferramentas" / "extratus_aburesi"

CONFIG_PATH = EXTRATUS_ROOT / "config" / "config.json"


CONFIG_PADRAO = {
    "pasta_entrada": "app/ferramentas/extratus_aburesi/dados/entrada_pdfs",
    "pasta_saida": "app/ferramentas/extratus_aburesi/dados/relatorios_prontos",
    "pasta_processados": "app/ferramentas/extratus_aburesi/dados/processados",
    "pasta_revisao": "app/ferramentas/extratus_aburesi/dados/revisao",
    "pasta_erros": "app/ferramentas/extratus_aburesi/dados/erros",

    "limite_padrao": 0,

    "ia_provider": "simulado",

    # Motor automático — ainda só liga/desliga uma bandeira (ver Motor no
    # Extratus). O "vigiar a pasta sozinho de verdade" é o próximo passo,
    # separado dessa tela de controle.
    "motor_ativo": False,

    # Pasta PRÓPRIA do motor — separada de pasta_entrada (que é a fila
    # manual/individual). Universal: todo mundo com acesso à aba Fila
    # do motor manda PDF pra cá, sem filtro por quem enviou.
    "motor_pasta_entrada": "app/ferramentas/extratus_aburesi/dados/motor_entrada_pdfs",
}

PASTAS_CONFIGURAVEIS = [
    "pasta_entrada",
    "pasta_saida",
    "pasta_processados",
    "pasta_revisao",
    "pasta_erros",
    "motor_pasta_entrada",
]

PROVEDORES_IA_VALIDOS = ("simulado", "claude")


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

    config = CONFIG_PADRAO.copy()
    config.update(config_usuario)

    if config != config_usuario:
        salvar_config(config)

    return resolver_pastas(config)


def definir_motor_ativo(ativo: bool):
    """Liga/desliga a bandeira do motor automático — lê e grava o
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
                config_bruto = lido
        except (json.JSONDecodeError, OSError):
            config_bruto = {}

    config = CONFIG_PADRAO.copy()
    config.update(config_bruto)
    config["motor_ativo"] = bool(ativo)

    salvar_config(config)

    return config["motor_ativo"]


def _carregar_config_bruta():
    if not CONFIG_PATH.exists():
        return {}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as arquivo:
            lido = json.load(arquivo)

        if isinstance(lido, dict):
            return lido
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


def atualizar_config_motor(pasta_entrada=None, ia_provider=None):
    """Edita as configurações do motor (pasta própria + provedor de IA) —
    mesmo padrão de leitura/gravação em bruto do definir_motor_ativo, pra
    não sobrescrever o config.json com caminhos já resolvidos em absoluto.
    """
    if ia_provider is not None and ia_provider not in PROVEDORES_IA_VALIDOS:
        raise ValueError(f"Provedor de IA inválido: {ia_provider!r}")

    config = CONFIG_PADRAO.copy()
    config.update(_carregar_config_bruta())

    if pasta_entrada is not None:
        pasta_entrada = pasta_entrada.strip()

        if not pasta_entrada:
            raise ValueError("Pasta de entrada do motor não pode ficar vazia.")

        config["motor_pasta_entrada"] = pasta_entrada

    if ia_provider is not None:
        config["ia_provider"] = ia_provider

    salvar_config(config)

    return config
