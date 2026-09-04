import uuid
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from app.ferramentas.crivus.config.taxonomia import NAO_IDENTIFICADO, TIPOS_ACOMPANHAMENTO, TIPOS_AGENDAMENTO
from app.ferramentas.crivus.core.ia_cliente import analisar_publicacao
from app.ferramentas.crivus.db.analises import (
    adicionar_anexo,
    concluir_analise,
    criar_agendamento_manual,
    criar_analise_a_partir_da_ia,
    descartar_alteracoes,
    excluir_agendamento_manual,
    listar_itens,
    marcar_ciente_alerta_critico,
    marcar_item_desnecessario,
    marcar_item_pronto,
    obter_analise,
    salvar_edicao_item,
)
from app.plataforma.db.models import CARGO_COORDENADOR, Usuario
from app.plataforma.web.auth import exigir_acesso_ferramenta
from app.plataforma.web.templates_util import criar_templates


router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("leitor-publicacoes"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])

PASTA_ANEXOS = Path(__file__).resolve().parents[2] / "dados" / "anexos"

# Henrique, 2026-09-03: 3 arquivos por colaborador comum — coordenador
# (e admin da plataforma) fica sem teto fixo, pra não travar um caso
# esporádico que precise de mais documentos de apoio.
MAXIMO_ANEXOS_COLABORADOR = 3

# 5MB por arquivo (recomendação registrada em conversa, 2026-09-03 —
# grande o bastante pra uma sentença digitalizada ou foto de celular,
# pequeno o bastante pra barrar um PDF de processo inteiro anexado por
# engano). Ainda sujeito a confirmação final de Henrique.
TAMANHO_MAXIMO_ANEXO_MB = 5
TAMANHO_MAXIMO_ANEXO = TAMANHO_MAXIMO_ANEXO_MB * 1024 * 1024

# Mesmo espírito da blindagem de upload do Extratus (extensão + tamanho +
# assinatura de bytes) — aqui estendida pra além de PDF, já que os
# documentos de apoio podem ser docx/png/jpeg (Henrique, 2026-09-03).
ASSINATURAS_VALIDAS = {
    ".pdf": (b"%PDF",),
    ".docx": (b"PK\x03\x04",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}
TIPOS_MIME_POR_EXTENSAO = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _limite_anexos(usuario):
    if usuario.eh_admin or usuario.cargo == CARGO_COORDENADOR:
        return None
    return MAXIMO_ANEXOS_COLABORADOR


def _erro_home(mensagem):
    return RedirectResponse(url=f"/crivus/leitor-individual?erro={quote(mensagem)}", status_code=303)


def _exigir_dono(analise_id, usuario):
    analise = obter_analise(analise_id)
    if not analise or analise.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Análise não encontrada.")
    return analise


@router.get("/leitor-individual")
def pagina_inicial(
    request: Request,
    erro: str | None = None,
    sucesso: str | None = None,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "usuario": usuario,
            "maximo_anexos": _limite_anexos(usuario),
            "tamanho_maximo_mb": TAMANHO_MAXIMO_ANEXO_MB,
            "erro": erro,
            "sucesso": sucesso,
        },
    )


@router.post("/leitor-individual/analisar")
async def analisar(
    npjur: str = Form(...),
    processo: str = Form(...),
    teor_publicacao: str = Form(...),
    arquivos: list[UploadFile] = File(default=[]),
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    if not teor_publicacao or not teor_publicacao.strip():
        return _erro_home("Cole o teor da publicação antes de enviar.")

    if not npjur.strip() or not processo.strip():
        return _erro_home("Informe o número do NPJUR e o número CNJ do processo.")

    arquivos_validos = [arquivo for arquivo in arquivos if arquivo.filename]

    limite = _limite_anexos(usuario)
    if limite is not None and len(arquivos_validos) > limite:
        return _erro_home(f"Máximo de {limite} anexos por análise.")

    anexos_para_ia = []
    anexos_para_salvar = []

    for arquivo in arquivos_validos:
        nome_seguro = Path(arquivo.filename).name
        extensao = Path(nome_seguro).suffix.lower()

        if extensao not in ASSINATURAS_VALIDAS:
            return _erro_home(f'"{nome_seguro}" não é um tipo de arquivo aceito (PDF, DOCX, PNG ou JPEG).')

        conteudo = await arquivo.read()

        if len(conteudo) > TAMANHO_MAXIMO_ANEXO:
            return _erro_home(f'"{nome_seguro}" tem mais de {TAMANHO_MAXIMO_ANEXO_MB}MB.')

        if not any(conteudo.startswith(assinatura) for assinatura in ASSINATURAS_VALIDAS[extensao]):
            return _erro_home(f'"{nome_seguro}" não parece ser um arquivo válido — conteúdo não bate com a extensão.')

        PASTA_ANEXOS.mkdir(parents=True, exist_ok=True)
        nome_no_disco = f"{uuid.uuid4().hex[:8]}_{nome_seguro}"
        caminho_destino = PASTA_ANEXOS / nome_no_disco
        caminho_destino.write_bytes(conteudo)

        tipo_mime = TIPOS_MIME_POR_EXTENSAO[extensao]
        anexos_para_ia.append({"caminho": caminho_destino, "tipo_mime": tipo_mime})
        anexos_para_salvar.append((nome_seguro, caminho_destino, tipo_mime, len(conteudo)))

    try:
        dados, uso = analisar_publicacao(teor_publicacao, anexos=anexos_para_ia)
    except Exception as exc:
        return _erro_home(f"Falha ao analisar a publicação: {exc}")

    analise = criar_analise_a_partir_da_ia(
        usuario.id, teor_publicacao, dados, uso, origem="individual",
        npjur=npjur.strip(), processo=processo.strip(),
    )

    for nome_seguro, caminho_destino, tipo_mime, tamanho in anexos_para_salvar:
        adicionar_anexo(analise.id, usuario.id, nome_seguro, caminho_destino, tipo_mime, tamanho)

    return RedirectResponse(url=f"/crivus/leitor-individual/{analise.id}", status_code=303)


@router.get("/leitor-individual/{analise_id}")
def pagina_detalhe(
    analise_id: int,
    request: Request,
    erro: str | None = None,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    analise = _exigir_dono(analise_id, usuario)
    acompanhamentos, agendamentos = listar_itens(analise_id)

    todos_os_itens = list(acompanhamentos) + list(agendamentos)
    todos_prontos = all(item.status != "sugerido" for item in todos_os_itens) if todos_os_itens else True

    # Henrique, 2026-09-06: "seção completa" fica verde quando TODOS os
    # itens DELA já foram revisados — mas só se ela tiver algum item; uma
    # seção vazia ("Nenhum agendamento necessário") não tem o que revisar,
    # não é "completa" de verdade.
    todos_acompanhamentos_prontos = bool(acompanhamentos) and all(item.status != "sugerido" for item in acompanhamentos)
    todos_agendamentos_prontos = bool(agendamentos) and all(item.status != "sugerido" for item in agendamentos)

    aviso_concluir = None
    if not todos_prontos:
        aviso_concluir = "Revise todos os itens antes de concluir."
    elif analise.tem_alerta_critico and not analise.ciente_alerta_critico:
        aviso_concluir = "Confirme a ciência do alerta crítico antes de concluir."

    return templates.TemplateResponse(
        request,
        "detalhe.html",
        {
            "usuario": usuario,
            "analise": analise,
            "acompanhamentos": acompanhamentos,
            "agendamentos": agendamentos,
            # Henrique, 2026-09-06: NAO_IDENTIFICADO NÃO entra na lista geral
            # de opções — "é de uso exclusivo da IA", uma pessoa nunca deve
            # poder escolhê-lo manualmente. Só aparece no <select> quando o
            # item ATUAL já veio assim da IA (ver detalhe.html), pra pessoa
            # enxergar o valor a corrigir, nunca como opção de lista nova.
            "tipos_acompanhamento": TIPOS_ACOMPANHAMENTO,
            "tipos_agendamento": TIPOS_AGENDAMENTO,
            "nao_identificado": NAO_IDENTIFICADO,
            "todos_prontos": todos_prontos,
            "todos_acompanhamentos_prontos": todos_acompanhamentos_prontos,
            "todos_agendamentos_prontos": todos_agendamentos_prontos,
            "pode_concluir": todos_prontos and (not analise.tem_alerta_critico or analise.ciente_alerta_critico),
            "aviso_concluir": aviso_concluir,
            "erro": erro,
        },
    )


@router.post("/leitor-individual/{analise_id}/acompanhamento/{item_id}/salvar")
async def salvar_acompanhamento(
    analise_id: int,
    item_id: int,
    # Form("") aqui e nas 3 rotas irmãs (não Form(...)) — achado real,
    # 2026-09-06: um <select required> vazio não deveria conseguir
    # submeter, mas se algo escapar disso (o campo some por completo do
    # form data quando o valor é string vazia, gerando 422 puro do
    # FastAPI em vez do banner de erro normal). Com default "" a
    # validação de "tipo vazio" vira responsabilidade da camada de
    # negócio (marcar_item_pronto/salvar_edicao_item), que já mostra a
    # mensagem certa pra pessoa em vez de uma tela de erro genérica.
    tipo: str = Form(""),
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    try:
        marcar_item_pronto(analise_id, "acompanhamento", item_id, novo_tipo=tipo)
    except ValueError as exc:
        return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}?erro={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}", status_code=303)


@router.post("/leitor-individual/{analise_id}/acompanhamento/{item_id}/salvar-edicao")
async def salvar_edicao_acompanhamento(
    analise_id: int,
    item_id: int,
    tipo: str = Form(""),
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    try:
        salvar_edicao_item(analise_id, "acompanhamento", item_id, tipo)
    except ValueError as exc:
        return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}?erro={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}", status_code=303)


@router.post("/leitor-individual/{analise_id}/acompanhamento/{item_id}/desnecessario")
async def marcar_acompanhamento_desnecessario(
    analise_id: int,
    item_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    marcar_item_desnecessario(analise_id, "acompanhamento", item_id, desnecessario=True)
    return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}", status_code=303)


@router.post("/leitor-individual/{analise_id}/acompanhamento/{item_id}/reverter")
async def reverter_acompanhamento(
    analise_id: int,
    item_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    marcar_item_desnecessario(analise_id, "acompanhamento", item_id, desnecessario=False)
    return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}", status_code=303)


@router.post("/leitor-individual/{analise_id}/agendamento/{item_id}/salvar")
async def salvar_agendamento(
    analise_id: int,
    item_id: int,
    tipo: str = Form(""),
    data_inicio: date = Form(...),
    data_fim: date = Form(...),
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    try:
        marcar_item_pronto(
            analise_id, "agendamento", item_id,
            novo_tipo=tipo, nova_data_inicio=data_inicio, nova_data_fim=data_fim,
        )
    except ValueError as exc:
        return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}?erro={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}", status_code=303)


@router.post("/leitor-individual/{analise_id}/agendamento/{item_id}/salvar-edicao")
async def salvar_edicao_agendamento(
    analise_id: int,
    item_id: int,
    tipo: str = Form(""),
    data_inicio: date = Form(...),
    data_fim: date = Form(...),
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    try:
        salvar_edicao_item(analise_id, "agendamento", item_id, tipo, nova_data_inicio=data_inicio, nova_data_fim=data_fim)
    except ValueError as exc:
        return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}?erro={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}", status_code=303)


@router.post("/leitor-individual/{analise_id}/agendamento/novo")
async def adicionar_agendamento(
    analise_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    try:
        criar_agendamento_manual(analise_id)
    except ValueError as exc:
        return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}?erro={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}", status_code=303)


@router.post("/leitor-individual/{analise_id}/agendamento/{item_id}/excluir")
async def excluir_agendamento(
    analise_id: int,
    item_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    try:
        excluir_agendamento_manual(analise_id, item_id)
    except ValueError as exc:
        return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}?erro={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}", status_code=303)


@router.post("/leitor-individual/{analise_id}/agendamento/{item_id}/desnecessario")
async def marcar_agendamento_desnecessario(
    analise_id: int,
    item_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    marcar_item_desnecessario(analise_id, "agendamento", item_id, desnecessario=True)
    return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}", status_code=303)


@router.post("/leitor-individual/{analise_id}/agendamento/{item_id}/reverter")
async def reverter_agendamento(
    analise_id: int,
    item_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    marcar_item_desnecessario(analise_id, "agendamento", item_id, desnecessario=False)
    return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}", status_code=303)


@router.post("/leitor-individual/{analise_id}/ciente-alerta")
async def ciente_alerta(
    analise_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    marcar_ciente_alerta_critico(analise_id)
    return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}", status_code=303)


@router.post("/leitor-individual/{analise_id}/descartar")
async def descartar(
    analise_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    try:
        descartar_alteracoes(analise_id)
    except ValueError as exc:
        return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}?erro={quote(str(exc))}", status_code=303)
    return RedirectResponse(url="/crivus/leitor-individual", status_code=303)


@router.post("/leitor-individual/{analise_id}/concluir")
async def concluir(
    analise_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("leitor-publicacoes")),
):
    _exigir_dono(analise_id, usuario)
    try:
        concluir_analise(analise_id)
    except ValueError as exc:
        return RedirectResponse(url=f"/crivus/leitor-individual/{analise_id}?erro={quote(str(exc))}", status_code=303)
    return RedirectResponse(url=f"/crivus/leitor-individual?sucesso={quote('Caso concluído.')}", status_code=303)
