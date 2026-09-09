import shutil
from datetime import datetime
from pathlib import Path

from app.plataforma.paths import PROJECT_ROOT


# Caminho do tipo "bancario" (Extratus-Relatórios), o único que existe
# hoje — continua como constante de módulo (em vez de só um campo dentro
# de `tipo`) pra manter 100% de compatibilidade com quem já chama estas
# funções sem passar `tipo` nenhum (uso direto/teste). Toda função abaixo
# aceita um `tipo` opcional (ver nucleo_relatorios/tipos.py) que, quando
# informado, usa `tipo.prompt_path` no lugar desta constante — é assim que
# um tipo novo (EMENDA, CONDENAÇÃO) no futuro terá seu próprio prompt/
# histórico, sem precisar de um módulo prompt_manager por tipo.
PROMPT_PATH = PROJECT_ROOT / "app" / "ferramentas" / "nucleo_relatorios" / "config" / "instrucoes_relatorio.txt"

# Guarda uma cópia com carimbo de data/hora do prompt anterior toda vez que
# alguém sobe um novo pela tela do Robô — se o novo vier errado, dá pra
# recuperar o de antes sem precisar mexer no código.
HISTORICO_PROMPTS_DIR = PROMPT_PATH.parent / "historico_prompts"


def _caminho_prompt(tipo=None):
    return tipo.prompt_path if tipo is not None else PROMPT_PATH


def _historico_dir(tipo=None):
    return _caminho_prompt(tipo).parent / "historico_prompts"


def carregar_instrucoes_relatorio(tipo=None):
    caminho = _caminho_prompt(tipo)

    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}"
        )

    with open(
        caminho,
        "r",
        encoding="utf-8"
    ) as arquivo:
        return arquivo.read()


def extensao_esperada_prompt(tipo=None):
    return _caminho_prompt(tipo).suffix.lower()


def obter_metadados_prompt(tipo=None):
    """Info pra tela de Configurações (admin) saber, sem abrir o arquivo:
    quando o prompt atual foi salvo e quantas versões anteriores existem
    no histórico (cada substituição guarda uma cópia com carimbo antes de
    sobrescrever, ver substituir_instrucoes_relatorio).
    """
    caminho = _caminho_prompt(tipo)
    historico_dir = _historico_dir(tipo)

    atualizado_em = (
        datetime.fromtimestamp(caminho.stat().st_mtime)
        if caminho.exists()
        else None
    )

    total_versoes_anteriores = (
        len(list(historico_dir.glob(f"{caminho.stem}_*{caminho.suffix}")))
        if historico_dir.exists()
        else 0
    )

    return {
        "atualizado_em": atualizado_em,
        "total_versoes_anteriores": total_versoes_anteriores,
    }


# Quantas versões anteriores mostrar na tela de Configurações — a pasta
# de histórico não tem limpeza automática (cresce 1 arquivo por
# substituição, pra sempre), então a lista mostrada é só as mais
# recentes; os arquivos mais antigos continuam no disco, só não
# aparecem na tela.
LIMITE_VERSOES_EXIBIDAS = 10


def listar_versoes_prompt(tipo=None):
    """Versões anteriores do prompt guardadas no histórico, mais recente
    primeiro — cada uma com o nome de arquivo (usado só internamente, pra
    ativar_versao_prompt saber qual reativar) e quando foi salva. A versão
    ATIVA não entra nessa lista — ver obter_metadados_prompt pra saber
    quando ela foi salva."""
    caminho = _caminho_prompt(tipo)
    historico_dir = _historico_dir(tipo)

    if not historico_dir.exists():
        return []

    arquivos = sorted(
        historico_dir.glob(f"{caminho.stem}_*{caminho.suffix}"),
        key=lambda caminho: caminho.stat().st_mtime,
        reverse=True,
    )

    return [
        {
            "nome_arquivo": arquivo.name,
            "salvo_em": datetime.fromtimestamp(arquivo.stat().st_mtime),
        }
        for arquivo in arquivos[:LIMITE_VERSOES_EXIBIDAS]
    ]


def ativar_versao_prompt(nome_arquivo, tipo=None):
    """Torna uma versão antiga (guardada no histórico) a versão ATIVA —
    reaproveita substituir_instrucoes_relatorio, então a versão que estava
    ativa até agora vira uma versão guardada no lugar dela, nunca se perde
    nada (dá pra "ir e voltar" à vontade).

    `Path(nome_arquivo).name` descarta qualquer parte de caminho (/, ..)
    que venha no valor — só o nome puro é usado pra montar o caminho
    real, então não dá pra escapar da pasta de histórico passando algo
    tipo "../../config.json" nesse campo."""
    candidato = _historico_dir(tipo) / Path(nome_arquivo).name

    if not candidato.is_file():
        raise ValueError("Essa versão do prompt não existe mais.")

    conteudo = candidato.read_text(encoding="utf-8")
    substituir_instrucoes_relatorio(conteudo.encode("utf-8"), tipo=tipo)


def substituir_instrucoes_relatorio(conteudo: bytes, tipo=None):
    """Sobrescreve o prompt de instruções com um novo conteúdo (upload pela
    tela do Robô). Valida que o conteúdo é texto de verdade (UTF-8) antes
    de gravar, e guarda uma cópia com carimbo de data/hora do prompt
    anterior em `historico_prompts/`, pra não perder o que havia antes se
    o arquivo novo estiver errado.
    """
    try:
        texto = conteudo.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("O arquivo não parece ser um texto válido (UTF-8).")

    caminho = _caminho_prompt(tipo)
    historico_dir = _historico_dir(tipo)

    if caminho.exists():
        historico_dir.mkdir(parents=True, exist_ok=True)
        # %f (microssegundos) evita 2 substituições no mesmo segundo
        # colidirem no mesmo nome de arquivo — sem isso, a segunda
        # sobrescrevia o backup da primeira silenciosamente (achado real,
        # 2026-08-25, escrevendo o teste de obter_metadados_prompt).
        carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        backup = historico_dir / f"{caminho.stem}_{carimbo}{caminho.suffix}"
        shutil.copy2(caminho, backup)

    caminho.write_text(texto, encoding="utf-8")