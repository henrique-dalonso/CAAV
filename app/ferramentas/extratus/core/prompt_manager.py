import shutil
from datetime import datetime
from pathlib import Path

from app.plataforma.paths import PROJECT_ROOT


PROMPT_PATH = PROJECT_ROOT / "app" / "ferramentas" / "extratus" / "config" / "instrucoes_relatorio.txt"

# Guarda uma cópia com carimbo de data/hora do prompt anterior toda vez que
# alguém sobe um novo pela tela do Robô — se o novo vier errado, dá pra
# recuperar o de antes sem precisar mexer no código.
HISTORICO_PROMPTS_DIR = PROMPT_PATH.parent / "historico_prompts"


def carregar_instrucoes_relatorio():
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {PROMPT_PATH}"
        )

    with open(
        PROMPT_PATH,
        "r",
        encoding="utf-8"
    ) as arquivo:
        return arquivo.read()


def extensao_esperada_prompt():
    return PROMPT_PATH.suffix.lower()


def obter_metadados_prompt():
    """Info pra tela de Configurações (admin) saber, sem abrir o arquivo:
    quando o prompt atual foi salvo e quantas versões anteriores existem
    em HISTORICO_PROMPTS_DIR (cada substituição guarda uma cópia com
    carimbo antes de sobrescrever, ver substituir_instrucoes_relatorio).
    """
    atualizado_em = (
        datetime.fromtimestamp(PROMPT_PATH.stat().st_mtime)
        if PROMPT_PATH.exists()
        else None
    )

    total_versoes_anteriores = (
        len(list(HISTORICO_PROMPTS_DIR.glob(f"{PROMPT_PATH.stem}_*{PROMPT_PATH.suffix}")))
        if HISTORICO_PROMPTS_DIR.exists()
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


def listar_versoes_prompt():
    """Versões anteriores do prompt guardadas em HISTORICO_PROMPTS_DIR,
    mais recente primeiro — cada uma com o nome de arquivo (usado só
    internamente, pra ativar_versao_prompt saber qual reativar) e quando
    foi salva. A versão ATIVA (PROMPT_PATH) não entra nessa lista — ver
    obter_metadados_prompt pra saber quando ela foi salva."""
    if not HISTORICO_PROMPTS_DIR.exists():
        return []

    arquivos = sorted(
        HISTORICO_PROMPTS_DIR.glob(f"{PROMPT_PATH.stem}_*{PROMPT_PATH.suffix}"),
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


def ativar_versao_prompt(nome_arquivo):
    """Torna uma versão antiga (guardada em HISTORICO_PROMPTS_DIR) a
    versão ATIVA — reaproveita substituir_instrucoes_relatorio, então a
    versão que estava ativa até agora vira uma versão guardada no lugar
    dela, nunca se perde nada (dá pra "ir e voltar" à vontade).

    `Path(nome_arquivo).name` descarta qualquer parte de caminho (/, ..)
    que venha no valor — só o nome puro é usado pra montar o caminho
    real, então não dá pra escapar de HISTORICO_PROMPTS_DIR passando
    algo tipo "../../config.json" nesse campo."""
    candidato = HISTORICO_PROMPTS_DIR / Path(nome_arquivo).name

    if not candidato.is_file():
        raise ValueError("Essa versão do prompt não existe mais.")

    conteudo = candidato.read_text(encoding="utf-8")
    substituir_instrucoes_relatorio(conteudo.encode("utf-8"))


def substituir_instrucoes_relatorio(conteudo: bytes):
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

    if PROMPT_PATH.exists():
        HISTORICO_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        # %f (microssegundos) evita 2 substituições no mesmo segundo
        # colidirem no mesmo nome de arquivo — sem isso, a segunda
        # sobrescrevia o backup da primeira silenciosamente (achado real,
        # 2026-08-25, escrevendo o teste de obter_metadados_prompt).
        carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        backup = HISTORICO_PROMPTS_DIR / f"{PROMPT_PATH.stem}_{carimbo}{PROMPT_PATH.suffix}"
        shutil.copy2(PROMPT_PATH, backup)

    PROMPT_PATH.write_text(texto, encoding="utf-8")