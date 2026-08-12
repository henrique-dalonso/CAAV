import re
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app.ferramentas.extratus_aburesi.core.config_manager import carregar_config
from app.ferramentas.extratus_aburesi.core.pipeline_manual import processar_upload_manual, retomar_apos_conferencia
from app.ferramentas.extratus_aburesi.db.conferencias import registrar_decisao
from app.ferramentas.extratus_aburesi.db.triagem_manual import (
    DUPLICADO_RELATORIO,
    MENSAGENS_INCONSISTENCIA,
    STATUS_EXIGE_PROCESSO_MANUAL,
    STATUS_INCONSISTENCIA,
    criar_registro,
    descartar,
    listar_estado_do_usuario,
    listar_inconsistencias_do_usuario,
    obter_registro,
)
from app.ferramentas.extratus_aburesi.web.rotulos import contagem_nav_pendentes, contagem_nav_relatorios
from app.plataforma.db.models import Usuario
from app.plataforma.web.auth import exigir_acesso_ferramenta
from app.plataforma.web.templates_util import criar_templates


# Mesmo padrão CNJ que a Fila do Motor já valida (web/routes/fila.py) —
# ver core/processo_detector.py pro reconhecimento automático.
PADRAO_CNJ = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")

# Henrique, 2026-08-11: "se não pode virar baderna, nego sair torrando
# solicitação" — teto rígido, reforçado no servidor (nunca só no cliente).
MAXIMO_ARQUIVOS_POR_ENVIO = 5

router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("extratus-aburesi"))])

TAMANHO_MAXIMO_UPLOAD = 100 * 1024 * 1024  # 100 MB

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])
templates.env.globals["contagem_nav_pendentes"] = contagem_nav_pendentes
templates.env.globals["contagem_nav_relatorios"] = contagem_nav_relatorios


def _estado_atual(usuario_id):
    estado = listar_estado_do_usuario(usuario_id)

    pendentes = [
        {
            "id": r.id,
            "nome": r.nome_arquivo,
            "status": r.status,
            "aguardando_conferencia": r.status in STATUS_INCONSISTENCIA,
        }
        for r in estado["pendentes"]
    ]
    processando = [
        {
            "id": r.id,
            "nome": r.nome_arquivo,
            "status": r.status,
            "erro_mensagem": r.erro_mensagem,
            "job_id": r.job_id,
            "processo_detectado": r.processo_detectado,
        }
        for r in estado["processando"]
    ]

    return pendentes, processando


def _redirecionar(erro=None, sucesso=None):
    partes = []

    if erro:
        partes.append(f"erro={quote(erro)}")

    if sucesso:
        partes.append(f"sucesso={quote(sucesso)}")

    query = f"?{'&'.join(partes)}" if partes else ""

    return RedirectResponse(url=f"/extratus-aburesi/{query}", status_code=303)


def _link_relatorio_existente(registro):
    """Ver docstring equivalente em app/ferramentas/extratus/web/routes/
    inbox.py (Extratus - Relatórios) — mesma lógica."""
    if registro.origem_duplicado == "motor":
        return "/extratus-aburesi/relatorios-finalizados"
    return "/extratus-aburesi/relatorios"


def _conferencias_pendentes(usuario_id):
    return [
        {
            "id": registro.id,
            "nome": registro.nome_arquivo,
            "tipo": registro.status,
            "mensagem": MENSAGENS_INCONSISTENCIA.get(registro.status, "pendência na triagem"),
            "processo_detectado": registro.processo_detectado,
            "link_relatorio": _link_relatorio_existente(registro) if registro.status == DUPLICADO_RELATORIO else None,
        }
        for registro in listar_inconsistencias_do_usuario(usuario_id)
    ]


@router.get("/")
def pagina_inicial(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus-aburesi")),
    erro: str | None = None,
    sucesso: str | None = None,
):
    pendentes, processando = _estado_atual(usuario.id)

    return templates.TemplateResponse(
        request,
        "inbox.html",
        {
            "usuario": usuario,
            "pendentes": pendentes,
            "total_pendentes": len(pendentes),
            "processando": processando,
            "conferencias": _conferencias_pendentes(usuario.id),
            "maximo_arquivos": MAXIMO_ARQUIVOS_POR_ENVIO,
            "erro": erro,
            "sucesso": sucesso,
            "aba_ativa": "gerar",
        },
    )


@router.get("/estado")
def estado_processamento(usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus-aburesi"))):
    """Endpoint enxuto pro polling (inbox.js) — mesmo formato que
    /fila/estado usa, escopado ao próprio usuário (Conferências e
    processamento manual são pessoais, diferente da Fila do Motor)."""
    pendentes, processando = _estado_atual(usuario.id)

    return {
        "pendentes": pendentes,
        "processando": processando,
        "conferencias": _conferencias_pendentes(usuario.id),
    }


@router.post("/upload")
async def enviar_pdfs(
    background_tasks: BackgroundTasks,
    arquivos: list[UploadFile] = File(...),
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus-aburesi")),
):
    if len(arquivos) > MAXIMO_ARQUIVOS_POR_ENVIO:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo de {MAXIMO_ARQUIVOS_POR_ENVIO} arquivos por envio.",
        )

    config = carregar_config()
    pasta_entrada = Path(config.get("pasta_entrada", "entrada_pdfs"))
    pasta_entrada.mkdir(parents=True, exist_ok=True)

    enviados = []
    rejeitados = []

    for arquivo in arquivos:
        nome_seguro = Path(arquivo.filename).name

        if not nome_seguro.lower().endswith(".pdf"):
            rejeitados.append(f'"{nome_seguro}" não é .pdf')
            continue

        conteudo = await arquivo.read()

        if len(conteudo) > TAMANHO_MAXIMO_UPLOAD:
            rejeitados.append(
                f'"{nome_seguro}" tem mais de {TAMANHO_MAXIMO_UPLOAD // (1024 * 1024)} MB'
            )
            continue

        if not conteudo.startswith(b"%PDF"):
            rejeitados.append(f'"{nome_seguro}" não parece ser um PDF válido')
            continue

        # Prefixo único por upload — a pasta é compartilhada no disco e
        # vários usuários (ou vários arquivos do mesmo lote) podem mandar
        # nomes iguais ao mesmo tempo; diferente da Fila do Motor (um
        # arquivo por requisição, sequencial), aqui todos sobem juntos.
        nome_no_disco = f"{uuid.uuid4().hex[:8]}_{nome_seguro}"
        caminho_destino = pasta_entrada / nome_no_disco
        caminho_destino.write_bytes(conteudo)

        registro = criar_registro(nome_seguro, caminho_destino, usuario.id)
        background_tasks.add_task(processar_upload_manual, registro.id)
        enviados.append(nome_seguro)

    if rejeitados:
        return _redirecionar(
            erro=f"{len(enviados)} enviado(s). Recusado(s): " + "; ".join(rejeitados)
        )

    return _redirecionar(sucesso=f"{len(enviados)} PDF(s) enviado(s) — a triagem já começou.")


@router.post("/conferencia/{registro_id}/aprovar")
async def aprovar_conferencia(
    registro_id: int,
    background_tasks: BackgroundTasks,
    processo: str | None = Form(None),
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus-aburesi")),
):
    registro = obter_registro(registro_id)

    if not registro or registro.usuario_id != usuario.id or registro.status not in STATUS_INCONSISTENCIA:
        return _redirecionar(erro="Essa pendência de conferência não existe mais.")

    processo_informado = (processo or "").strip() or None

    if registro.status in STATUS_EXIGE_PROCESSO_MANUAL and (not processo_informado or not PADRAO_CNJ.match(processo_informado)):
        return _redirecionar(
            erro="Informe um número de processo válido (formato 0000000-00.0000.0.00.0000) pra liberar esse arquivo."
        )

    tipo_original = registro.status
    nome_arquivo = registro.nome_arquivo

    registrar_decisao(nome_arquivo, tipo_original, "aprovado", usuario.id, processo_informado=processo_informado)
    background_tasks.add_task(retomar_apos_conferencia, registro_id, processo_informado)

    return _redirecionar(sucesso=f'"{nome_arquivo}" liberado — gerando o relatório agora.')


@router.post("/conferencia/{registro_id}/descartar")
def descartar_conferencia(
    registro_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus-aburesi")),
):
    registro = obter_registro(registro_id)

    if not registro or registro.usuario_id != usuario.id or registro.status not in STATUS_INCONSISTENCIA:
        return _redirecionar(erro="Essa pendência de conferência não existe mais.")

    tipo_original = registro.status
    nome_arquivo = registro.nome_arquivo
    caminho = Path(registro.caminho_pdf)

    if caminho.exists():
        caminho.unlink()

    descartar(registro_id)
    registrar_decisao(nome_arquivo, tipo_original, "descartado", usuario.id)

    return _redirecionar(sucesso=f'"{nome_arquivo}" descartado.')


@router.get("/conferencia/{registro_id}/ver")
def ver_pdf_conferencia(
    registro_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus-aburesi")),
):
    registro = obter_registro(registro_id)

    if not registro or registro.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    caminho = Path(registro.caminho_pdf)

    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    return FileResponse(caminho, media_type="application/pdf")


@router.post("/processamento/{registro_id}/descartar")
def dispensar_processamento_finalizado(
    registro_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus-aburesi")),
):
    """Dispensa um card "Concluído"/"Erro" já finalizado — só some da
    tela, o Job/relatório já está seguro em outro lugar (Job/.docx)."""
    registro = obter_registro(registro_id)

    if not registro or registro.usuario_id != usuario.id or registro.status not in ("concluido", "erro"):
        raise HTTPException(status_code=404, detail="Esse item não existe mais.")

    descartar(registro_id)

    return {"ok": True}


@router.get("/download/{nome_arquivo}")
def baixar_relatorio(nome_arquivo: str):
    config = carregar_config()

    pasta_saida = Path(config.get("pasta_saida", "relatorios_prontos"))
    nome_seguro = Path(nome_arquivo).name
    caminho = pasta_saida / nome_seguro

    # Achado testando a página de erro nova (2026-08-12): sem essa
    # checagem, um link de download apontando pra um arquivo que já não
    # existe (removido, movido) derrubava com um `RuntimeError` cru do
    # Starlette (FileResponse só confere o arquivo na hora de mandar a
    # resposta) — igual ao padrão já usado em fila.py, agora vira um 404
    # controlado, com página de erro estilizada em vez de crash.
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    return FileResponse(caminho, filename=nome_seguro)
