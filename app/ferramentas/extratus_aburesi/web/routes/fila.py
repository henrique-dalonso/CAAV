import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app.ferramentas.extratus_aburesi.core.config_manager import carregar_config
from app.ferramentas.extratus_aburesi.core.pdf_manager import listar_pdfs
from app.ferramentas.extratus_aburesi.db.checagem_fila import (
    APROVADO,
    MENSAGENS_INCONSISTENCIA,
    NAO_ENCONTRADO,
    PENDENTE,
    STATUS_INCONSISTENCIA,
    aprovar_manualmente,
    descartar as descartar_checagem,
    estado_por_nome,
    listar_inconsistencias,
    obter_registro,
    obter_registro_por_nome,
)
from app.ferramentas.extratus_aburesi.db.conferencias import registrar_decisao
from app.ferramentas.extratus_aburesi.db.lotes import listar_arquivos_ja_reivindicados
from app.ferramentas.extratus_aburesi.web.rotulos import contagem_nav_pendentes, contagem_nav_relatorios
from app.plataforma.db.models import Usuario
from app.plataforma.web.auth import exigir_acesso_fila_motor
from app.plataforma.web.templates_util import criar_templates


# Mesmo padrão de número de processo (CNJ) que o resto do sistema já
# reconhece (ver core/processo_detector.py) — usado aqui só pra validar
# o número digitado à mão no painel de Conferências antes de liberar um
# arquivo marcado como "processo não encontrado".
PADRAO_CNJ = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")


router = APIRouter(dependencies=[Depends(exigir_acesso_fila_motor("extratus-aburesi"))])

TAMANHO_MAXIMO_UPLOAD = 350 * 1024 * 1024  # 350 MB — a fila do motor aceita PDF bem maior que o manual

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])
# Contagem da aba "Gerar relatórios"/"Relatórios" — ver mesmo comentário
# em inbox.py. Cuidado: essa página TAMBÉM tem seu próprio
# "total_pendentes" no contexto (a fila do MOTOR, sem relação nenhuma
# com isso) — por isso as funções globais têm nome bem diferente
# (contagem_nav_*), pra nunca colidir com esse outro.
templates.env.globals["contagem_nav_pendentes"] = contagem_nav_pendentes
templates.env.globals["contagem_nav_relatorios"] = contagem_nav_relatorios


def _redirecionar(erro=None, sucesso=None):
    partes = []

    if erro:
        partes.append(f"erro={quote(erro)}")

    if sucesso:
        partes.append(f"sucesso={quote(sucesso)}")

    query = f"?{'&'.join(partes)}" if partes else ""

    return RedirectResponse(url=f"/extratus-aburesi/fila{query}", status_code=303)


def _estado_atual_fila():
    """Quem está pendente vs. já reivindicado pelo motor agora mesmo —
    usado tanto pra renderizar a página quanto pelo endpoint de polling
    (/fila/estado), sempre a mesma fonte de verdade.

    Pendentes vem como [{"nome": ..., "status": ..., "aguardando_conferencia": ...}],
    não só o nome — status é o da checagem (checagem_lote.py): "pendente"
    (bolinha laranja, ainda checando de verdade) ou "aprovado" (bolinha
    amarela, elegível pro motor). "aguardando_conferencia" é True quando
    o status é uma das 3 inconsistências (bolinha VERMELHA, distinta da
    laranja de propósito — Henrique, 2026-08-07: "se fica só em
    checagem, não fica explícito que aquele em específico está
    esperando" uma decisão humana no painel de Conferências, ao
    contrário de "em checagem", que resolve sozinho). Um arquivo sem
    linha na checagem ainda (acabou de chegar, o próximo ciclo — poucos
    segundos — ainda não rodou pra ele) conta como "pendente" por
    padrão, nunca some da lista por causa disso."""
    config = carregar_config()
    pdfs_na_pasta = [pdf.name for pdf in listar_pdfs(config.get("motor_pasta_entrada", "motor_entrada_pdfs"))]
    em_processamento = listar_arquivos_ja_reivindicados()
    status_checagem = estado_por_nome()

    # Separados fisicamente em duas colunas na tela (não só uma etiqueta):
    # quem ainda espera o motor notar o arquivo vs. quem já foi
    # reivindicado por um lote enviado à Anthropic.
    apenas_pendentes = [
        {
            "nome": nome,
            "status": status_checagem.get(nome, PENDENTE),
            "aguardando_conferencia": status_checagem.get(nome, PENDENTE) in STATUS_INCONSISTENCIA,
        }
        for nome in pdfs_na_pasta
        if nome not in em_processamento
    ]
    apenas_processando = [nome for nome in pdfs_na_pasta if nome in em_processamento]

    # Vermelho (aguardando conferência) sobe pro topo — é o que precisa de
    # uma decisão humana agora; amarelo (aprovado, só esperando o Motor
    # pegar) desce pro fim, já que não precisa de ação nenhuma; laranja
    # (ainda checando) fica no meio (Henrique, 2026-08-07: "fica melhor a
    # visualização"). sort() é estável — dentro do mesmo grupo, mantém a
    # ordem original (a mesma de pdfs_na_pasta).
    def _prioridade_pendente(item):
        if item["aguardando_conferencia"]:
            return 0
        if item["status"] == APROVADO:
            return 2
        return 1

    apenas_pendentes.sort(key=_prioridade_pendente)

    return apenas_pendentes, apenas_processando


def _conferencias_pendentes():
    """Inconsistências da triagem esperando decisão humana no painel de
    Conferências — só as DESTA ferramenta (cada Fila do Motor mostra
    exclusivamente as suas próprias, nunca mistura com outra ferramenta;
    isso é diferente do sininho de notificações, que é multi-ferramenta
    de propósito). Mesma fonte (`listar_inconsistencias`) usada pelo
    sininho, pra nunca ter duas consultas divergentes."""
    return [
        {
            "id": registro.id,
            "nome": registro.nome_arquivo,
            "tipo": registro.status,
            "mensagem": MENSAGENS_INCONSISTENCIA.get(registro.status, "pendência na triagem"),
            "processo_detectado": registro.processo_detectado,
        }
        for registro in listar_inconsistencias()
    ]


@router.get("/fila")
def pagina_fila(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_fila_motor("extratus-aburesi")),
    erro: str | None = None,
    sucesso: str | None = None,
):
    apenas_pendentes, apenas_processando = _estado_atual_fila()

    return templates.TemplateResponse(
        request,
        "fila.html",
        {
            "usuario": usuario,
            "apenas_pendentes": apenas_pendentes,
            "total_pendentes": len(apenas_pendentes),
            "apenas_processando": apenas_processando,
            "total_processando": len(apenas_processando),
            "conferencias": _conferencias_pendentes(),
            "erro": erro,
            "sucesso": sucesso,
        },
    )


@router.get("/fila/estado")
def estado_fila():
    """Endpoint enxuto pro polling (fila.js) — só os nomes, sem
    renderizar HTML nenhum. Chamado a cada poucos segundos pela tela da
    Fila, pra Pendentes/Processando (e agora Conferências) se
    atualizarem sozinhos sem F5."""
    apenas_pendentes, apenas_processando = _estado_atual_fila()

    return {
        "pendentes": apenas_pendentes,
        "processando": apenas_processando,
        "conferencias": _conferencias_pendentes(),
    }


@router.post("/fila/upload")
async def enviar_pdfs(request: Request, arquivos: list[UploadFile] = File(...)):
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
            rejeitados.append(f'"{nome_seguro}" já existe na fila do Motor (não foi enviado de novo)')
            continue

        caminho_destino.write_bytes(conteudo)
        enviados += 1

    # A Fila do motor envia um arquivo por requisição (fila.js), pra um
    # PDF ruim/duplicado não travar o lote inteiro nem perder o que já
    # deu certo se a conexão cair no meio. Nesse caso o JS só precisa de
    # um retrato objetivo do que aconteceu — devolver a página inteira
    # renderizada de novo (o que o redirect clássico faz) seria
    # trabalho puro descartado, refeito uma vez por arquivo do lote.
    # O fallback de formulário puro (sem JS) continua no redirect normal.
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JSONResponse({"enviados": enviados, "rejeitados": rejeitados})

    if rejeitados:
        return _redirecionar(
            erro=f"{enviados} enviado(s). Recusado(s): " + "; ".join(rejeitados)
        )

    return _redirecionar(sucesso=f"{enviados} PDF(s) enviado(s) pra fila do Motor.")


@router.post("/fila/remover-varios")
def remover_varios_da_fila(
    nomes: list[str] = Form(...),
    usuario: Usuario = Depends(exigir_acesso_fila_motor("extratus-aburesi")),
):
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

        # Ver comentário equivalente em app/ferramentas/extratus/web/
        # routes/fila.py (Extratus - Relatórios) — mesma lógica.
        registro = obter_registro_por_nome(nome_seguro)
        if registro:
            if registro.status in STATUS_INCONSISTENCIA:
                registrar_decisao(nome_seguro, registro.status, "descartado", usuario.id)
            descartar_checagem(registro.id)

    mensagem = f"{removidos} PDF(s) removido(s) da fila."

    if ignorados:
        mensagem += f" {ignorados} já estava(m) em processamento pelo Motor e não foi(ram) removido(s)."

    return _redirecionar(sucesso=mensagem)


@router.post("/fila/conferencia/{registro_id}/aprovar")
def aprovar_conferencia(
    registro_id: int,
    usuario: Usuario = Depends(exigir_acesso_fila_motor("extratus-aburesi")),
    processo: str | None = Form(None),
):
    """"Prosseguir" do painel de Conferências — pula a trava da checagem
    automática e libera o arquivo pro Motor pegar no próximo ciclo. Quem
    decidiu fica registrado pra sempre (RegistroConferencia), mesmo a
    Fila do Motor sendo compartilhada por todo mundo com acesso."""
    registro = obter_registro(registro_id)

    if not registro or registro.status not in STATUS_INCONSISTENCIA:
        return _redirecionar(erro="Essa pendência de conferência não existe mais (o arquivo já saiu da fila).")

    processo_informado = (processo or "").strip() or None

    # "Processo não encontrado" é o único tipo onde ninguém sabe o
    # número ainda — sem digitar um válido, não libera (Henrique,
    # 2026-08-07: "não libera se a pessoa não inserir").
    if registro.status == NAO_ENCONTRADO and (not processo_informado or not PADRAO_CNJ.match(processo_informado)):
        return _redirecionar(erro="Informe um número de processo válido (formato 0000000-00.0000.0.00.0000) pra liberar esse arquivo.")

    tipo_original = registro.status
    nome_arquivo = registro.nome_arquivo

    aprovar_manualmente(registro_id, processo_manual=processo_informado)
    registrar_decisao(nome_arquivo, tipo_original, "aprovado", usuario.id, processo_informado=processo_informado)

    return _redirecionar(sucesso=f'"{nome_arquivo}" liberado pra fila do Motor.')


@router.post("/fila/conferencia/{registro_id}/descartar")
def descartar_conferencia(
    registro_id: int,
    usuario: Usuario = Depends(exigir_acesso_fila_motor("extratus-aburesi")),
):
    """"Descartar" do painel de Conferências — remove o PDF de vez da
    fila (mesmo mecanismo de /fila/remover-varios) e registra quem
    decidiu."""
    registro = obter_registro(registro_id)

    if not registro or registro.status not in STATUS_INCONSISTENCIA:
        return _redirecionar(erro="Essa pendência de conferência não existe mais (o arquivo já saiu da fila).")

    tipo_original = registro.status
    nome_arquivo = registro.nome_arquivo

    config = carregar_config()
    caminho = Path(config.get("motor_pasta_entrada", "motor_entrada_pdfs")) / nome_arquivo

    if caminho.exists():
        caminho.unlink()

    descartar_checagem(registro_id)
    registrar_decisao(nome_arquivo, tipo_original, "descartado", usuario.id)

    return _redirecionar(sucesso=f'"{nome_arquivo}" descartado da fila.')


@router.post("/fila/conferencia/descartar-todas")
def descartar_todas_conferencias(
    usuario: Usuario = Depends(exigir_acesso_fila_motor("extratus-aburesi")),
):
    """Ver docstring equivalente em app/ferramentas/extratus/web/routes/
    fila.py (Extratus - Relatórios) — mesma lógica."""
    config = carregar_config()
    pasta_entrada = Path(config.get("motor_pasta_entrada", "motor_entrada_pdfs"))

    descartados = 0

    for registro in listar_inconsistencias():
        caminho = pasta_entrada / registro.nome_arquivo

        if caminho.exists():
            caminho.unlink()

        descartar_checagem(registro.id)
        registrar_decisao(registro.nome_arquivo, registro.status, "descartado", usuario.id)
        descartados += 1

    if descartados == 0:
        return _redirecionar(erro="Não havia nada aguardando conferência pra descartar.")

    return _redirecionar(sucesso=f"{descartados} arquivo(s) descartado(s) da fila.")


@router.get("/fila/conferencia/{registro_id}/ver")
def ver_pdf_conferencia(
    registro_id: int,
    usuario: Usuario = Depends(exigir_acesso_fila_motor("extratus-aburesi")),
):
    """Ver docstring equivalente em app/ferramentas/extratus/web/routes/
    fila.py (Extratus - Relatórios) — mesma lógica."""
    registro = obter_registro(registro_id)

    if not registro:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    config = carregar_config()
    caminho = Path(config.get("motor_pasta_entrada", "motor_entrada_pdfs")) / registro.nome_arquivo

    if not caminho.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    return FileResponse(caminho, media_type="application/pdf")
