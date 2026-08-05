from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from app.ferramentas.extratus.core.config_manager import carregar_config
from app.ferramentas.extratus.core.pdf_manager import listar_pdfs
from app.ferramentas.extratus.db.lotes import listar_arquivos_ja_reivindicados
from app.plataforma.db.models import Usuario
from app.plataforma.web.auth import exigir_acesso_fila_motor
from app.plataforma.web.templates_util import criar_templates


router = APIRouter(dependencies=[Depends(exigir_acesso_fila_motor("extratus"))])

TAMANHO_MAXIMO_UPLOAD = 350 * 1024 * 1024  # 350 MB — a fila do motor aceita PDF bem maior que o manual

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])


def _redirecionar(erro=None, sucesso=None):
    partes = []

    if erro:
        partes.append(f"erro={quote(erro)}")

    if sucesso:
        partes.append(f"sucesso={quote(sucesso)}")

    query = f"?{'&'.join(partes)}" if partes else ""

    return RedirectResponse(url=f"/extratus/fila{query}", status_code=303)


@router.get("/fila")
def pagina_fila(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_fila_motor("extratus")),
    erro: str | None = None,
    sucesso: str | None = None,
):
    config = carregar_config()
    pdfs_na_pasta = [pdf.name for pdf in listar_pdfs(config.get("motor_pasta_entrada", "motor_entrada_pdfs"))]
    em_processamento = listar_arquivos_ja_reivindicados()

    # Separados fisicamente em duas colunas na tela (não só uma etiqueta):
    # quem ainda espera o motor notar o arquivo vs. quem já foi
    # reivindicado por um lote enviado à Anthropic.
    apenas_pendentes = [nome for nome in pdfs_na_pasta if nome not in em_processamento]
    apenas_processando = [nome for nome in pdfs_na_pasta if nome in em_processamento]

    return templates.TemplateResponse(
        request,
        "fila.html",
        {
            "usuario": usuario,
            "apenas_pendentes": apenas_pendentes,
            "total_pendentes": len(apenas_pendentes),
            "apenas_processando": apenas_processando,
            "total_processando": len(apenas_processando),
            "erro": erro,
            "sucesso": sucesso,
        },
    )


@router.post("/fila/upload")
async def enviar_pdfs(arquivos: list[UploadFile] = File(...)):
    config = carregar_config()
    pasta_entrada = Path(config.get("motor_pasta_entrada", "motor_entrada_pdfs"))
    pasta_entrada.mkdir(parents=True, exist_ok=True)

    enviados = 0
    rejeitados = []

    for arquivo in arquivos:
        nome_seguro = Path(arquivo.filename).name

        if not nome_seguro.lower().endswith(".pdf"):
            rejeitados.append(f'"{nome_seguro}" não é .pdf')
            continue

        conteudo = await arquivo.read()

        if len(conteudo) > TAMANHO_MAXIMO_UPLOAD:
            rejeitados.append(f'"{nome_seguro}" passou de {TAMANHO_MAXIMO_UPLOAD // (1024 * 1024)} MB')
            continue

        if not conteudo.startswith(b"%PDF"):
            rejeitados.append(f'"{nome_seguro}" não parece PDF válido')
            continue

        caminho_destino = pasta_entrada / nome_seguro

        # Nunca sobrescreve silenciosamente um arquivo já presente na fila
        # (pendente ou em processamento) — antes disso, um upload com nome
        # repetido apagava o arquivo anterior sem aviso nenhum.
        if caminho_destino.exists():
            rejeitados.append(f'"{nome_seguro}" já existe na fila do motor (não foi enviado de novo)')
            continue

        caminho_destino.write_bytes(conteudo)
        enviados += 1

    if rejeitados:
        return _redirecionar(
            erro=f"{enviados} enviado(s). Recusado(s): " + "; ".join(rejeitados)
        )

    return _redirecionar(sucesso=f"{enviados} PDF(s) enviado(s) pra fila do motor.")


@router.post("/fila/remover-varios")
def remover_varios_da_fila(nomes: list[str] = Form(...)):
    config = carregar_config()
    pasta_entrada = Path(config.get("motor_pasta_entrada", "motor_entrada_pdfs"))
    em_processamento = listar_arquivos_ja_reivindicados()

    removidos = 0
    ignorados = 0

    for nome in nomes:
        nome_seguro = Path(nome).name

        # Já reivindicado por um lote do motor (aguardando ou sendo
        # processado) — não dá pra "desenviar" o lote, então remover o
        # arquivo local aqui só criaria um erro confuso quando o
        # resultado chegasse. Ignora, silenciosamente contado à parte.
        if nome_seguro in em_processamento:
            ignorados += 1
            continue

        caminho = pasta_entrada / nome_seguro

        if caminho.exists():
            caminho.unlink()
            removidos += 1

    mensagem = f"{removidos} PDF(s) removido(s) da fila."

    if ignorados:
        mensagem += f" {ignorados} já estava(m) em processamento pelo motor e não foi(ram) removido(s)."

    return _redirecionar(sucesso=mensagem)
