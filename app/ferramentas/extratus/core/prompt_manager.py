import shutil
from datetime import datetime

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