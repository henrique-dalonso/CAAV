import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app.ferramentas.crivus.core.lote_manager import PlanilhaInvalida, ler_linhas_planilha
from app.ferramentas.crivus.db.lotes_crivus import criar_lote, listar_lotes, obter_lote
from app.plataforma.db.models import Usuario
from app.plataforma.web.auth import exigir_acesso_ferramenta
from app.plataforma.web.templates_util import criar_templates


router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("leitor-publicacoes"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])

PASTA_ENTRADA_LOTES = Path(__file__).resolve().parents[2] / "dados" / "lotes_entrada"

# Planilha real de amostra tem 10.274 linhas de texto livre — 25MB é
# generoso o bastante pra isso sem abrir espaço pra um upload absurdo por
# engano.
TAMANHO_MAXIMO_PLANILHA_MB = 25
TAMANHO_MAXIMO_PLANILHA = TAMANHO_MAXIMO_PLANILHA_MB * 1024 * 1024

# Mesma assinatura de bytes do .docx (leitor_individual.py) — .xlsx
# também é um zip por baixo.
ASSINATURA_XLSX = b"PK\x03\x04"


def _erro_lista(mensagem):
    return RedirectResponse(url=f"/crivus/lote?erro={quote(mensagem)}", status_code=303)


@router.get("/lote")
def pagina_lote(
    request: Request,
    erro: str | None = None,
    sucesso: str | None = None,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    return templates.TemplateResponse(
        request,
        "lote.html",
        {
            "usuario": usuario,
            "lotes": listar_lotes(),
            "erro": erro,
            "sucesso": sucesso,
        },
    )


# Henrique, 2026-09-14: rota SEM async — parse + inserção de 10 mil+
# linhas é trabalho de verdade (não é um `await` esperando rede), rodar
# isso direto numa coroutine travaria o event loop pro resto do site
# inteiro enquanto durasse. Uma rota `def` comum, o FastAPI já joga numa
# thread do pool sozinho (mesmo raciocínio já usado no motor
# compartilhado pro upload de PDFs em lote).
@router.post("/lote/upload")
def enviar_planilha(
    arquivo: UploadFile = File(...),
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    nome_seguro = Path(arquivo.filename or "").name

    if not nome_seguro.lower().endswith(".xlsx"):
        return _erro_lista(f'"{nome_seguro}" não é uma planilha .xlsx.')

    conteudo = arquivo.file.read()

    if len(conteudo) > TAMANHO_MAXIMO_PLANILHA:
        return _erro_lista(f'"{nome_seguro}" tem mais de {TAMANHO_MAXIMO_PLANILHA_MB}MB.')

    if not conteudo.startswith(ASSINATURA_XLSX):
        return _erro_lista(f'"{nome_seguro}" não parece ser uma planilha .xlsx válida.')

    PASTA_ENTRADA_LOTES.mkdir(parents=True, exist_ok=True)
    caminho_destino = PASTA_ENTRADA_LOTES / f"{uuid.uuid4().hex[:8]}_{nome_seguro}"
    caminho_destino.write_bytes(conteudo)

    try:
        linhas = ler_linhas_planilha(caminho_destino)
    except PlanilhaInvalida as erro:
        return _erro_lista(str(erro))

    if not linhas:
        return _erro_lista("A planilha não tem nenhuma linha com teor de publicação preenchido.")

    lote = criar_lote(usuario.id, nome_seguro, linhas)

    return RedirectResponse(
        url=f"/crivus/lote?sucesso={quote(f'Planilha enviada — {lote.total_linhas} publicações na fila.')}",
        status_code=303,
    )


@router.get("/lote/{lote_id}/planilha")
def baixar_planilha_resultado(lote_id: int):
    lote = obter_lote(lote_id)

    if not lote:
        return _erro_lista("Lote não encontrado.")

    if lote.status != "concluido" or not lote.caminho_planilha_saida:
        return _erro_lista("Esse lote ainda não terminou de processar.")

    caminho = Path(lote.caminho_planilha_saida)
    if not caminho.exists():
        return _erro_lista("Planilha de resultado não encontrada no servidor.")

    return FileResponse(
        caminho,
        filename=f"resultado_{lote.nome_arquivo}",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
