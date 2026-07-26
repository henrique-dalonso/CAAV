from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates

from app.ferramentas.extratus.core.config_manager import carregar_config
from app.ferramentas.extratus.core.pdf_manager import listar_pdfs
from app.ferramentas.extratus.core.pipeline import processar_pdf
from app.plataforma.db.models import Usuario
from app.plataforma.web.auth import exigir_acesso_ferramenta


router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("extratus"))])

TAMANHO_MAXIMO_UPLOAD = 100 * 1024 * 1024  # 100 MB

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
# Duas pastas de busca: a própria (inbox.html) e a da plataforma (base.html,
# de onde essa tela herda o cabeçalho/layout compartilhado).
templates = Jinja2Templates(directory=[TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])


def listar_relatorios_prontos(pasta_saida):
    pasta_saida = Path(pasta_saida)

    if not pasta_saida.exists():
        return []

    return sorted(
        (arquivo.name for arquivo in pasta_saida.glob("*.docx")),
        reverse=True
    )


def _redirecionar_com_erro(mensagem):
    return RedirectResponse(url=f"/extratus/?erro={quote(mensagem)}", status_code=303)


@router.get("/")
def pagina_inicial(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus")),
    erro: str | None = None,
):
    config = carregar_config()

    pendentes = listar_pdfs(config.get("pasta_entrada", "entrada_pdfs"))
    relatorios = listar_relatorios_prontos(config.get("pasta_saida", "relatorios_prontos"))

    return templates.TemplateResponse(
        request,
        "inbox.html",
        {
            "usuario": usuario,
            "pendentes": [pdf.name for pdf in pendentes],
            "total_pendentes": len(pendentes),
            "relatorios": relatorios,
            "ia_provider": config.get("ia_provider", "simulado"),
            "erro": erro,
        },
    )


@router.post("/upload")
async def enviar_pdf(arquivo: UploadFile = File(...)):
    nome_seguro = Path(arquivo.filename).name

    if not nome_seguro.lower().endswith(".pdf"):
        return _redirecionar_com_erro("Só é permitido enviar arquivos .pdf.")

    conteudo = await arquivo.read()

    if len(conteudo) > TAMANHO_MAXIMO_UPLOAD:
        return _redirecionar_com_erro(
            f"\"{nome_seguro}\" tem mais de {TAMANHO_MAXIMO_UPLOAD // (1024 * 1024)} MB "
            "— esse é o limite atual de upload."
        )

    if not conteudo.startswith(b"%PDF"):
        return _redirecionar_com_erro(
            f"\"{nome_seguro}\" não parece ser um PDF válido."
        )

    config = carregar_config()

    pasta_entrada = Path(config.get("pasta_entrada", "entrada_pdfs"))
    pasta_entrada.mkdir(parents=True, exist_ok=True)

    destino = pasta_entrada / nome_seguro
    destino.write_bytes(conteudo)

    return RedirectResponse(url="/extratus/", status_code=303)


@router.post("/processar-tudo")
def processar_tudo():
    config = carregar_config()

    pasta_entrada = config.get("pasta_entrada", "entrada_pdfs")
    pasta_saida = config.get("pasta_saida", "relatorios_prontos")
    pasta_processados = config.get("pasta_processados", "processados")
    pasta_erros = config.get("pasta_erros", "erros")
    pasta_revisao = config.get("pasta_revisao", "revisao")
    ia_provider = config.get("ia_provider", "simulado")

    for pdf in listar_pdfs(pasta_entrada):
        processar_pdf(
            pdf, pasta_saida, pasta_processados, pasta_erros, pasta_revisao, ia_provider
        )

    return RedirectResponse(url="/extratus/", status_code=303)


@router.get("/download/{nome_arquivo}")
def baixar_relatorio(nome_arquivo: str):
    config = carregar_config()

    pasta_saida = Path(config.get("pasta_saida", "relatorios_prontos"))
    nome_seguro = Path(nome_arquivo).name

    return FileResponse(
        pasta_saida / nome_seguro,
        filename=nome_seguro
    )
