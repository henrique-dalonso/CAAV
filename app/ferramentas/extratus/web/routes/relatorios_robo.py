import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.ferramentas.extratus.db.checagem_fila import resolver_solicitantes
from app.ferramentas.extratus.db.jobs import excluir_job, listar_jobs_robo, marcar_notificacao_resolvida_robo, obter_job
from app.ferramentas.extratus.web.rotulos import (
    ABA_RELATORIOS_ROBO,
    FERRAMENTA_SLUG,
    contagem_nav_conferencias_fila,
    contagem_nav_conferencias_manual,
    contagem_nav_relatorios,
    contagem_nav_relatorios_robo,
    rotulo_erro,
    rotulo_status,
)
from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import listar_todos_usuarios, marcar_aba_vista
from app.plataforma.web.auth import exigir_acesso_ferramenta, exigir_admin
from app.plataforma.web.templates_util import criar_templates


# "Relatórios do Robô" — repositório universal do que o ROBÔ já
# processou (pronto, em revisão ou com erro), separado da tela
# "Relatórios URGENTES" (só manuais) desde 2026-08-08. Henrique,
# 2026-08-11: acesso de VER esse acervo é do mesmo nível que "Relatórios
# URGENTES" (qualquer um
# com a ferramenta liberada, é acervo do escritório) — não precisa mais
# de acesso à Fila do Robô pra isso; Fila do Robô continua restrita,
# essa é só a permissão de alimentar/operar o Robô, não de ver o que
# ele já produziu.
router = APIRouter(dependencies=[Depends(exigir_acesso_ferramenta("extratus"))])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
PLATAFORMA_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[4] / "plataforma" / "web" / "templates"
)
templates = criar_templates([TEMPLATES_DIR, PLATAFORMA_TEMPLATES_DIR])
templates.env.filters["rotulo_status"] = rotulo_status
templates.env.filters["rotulo_erro"] = rotulo_erro
templates.env.globals["contagem_nav_conferencias_manual"] = contagem_nav_conferencias_manual
templates.env.globals["contagem_nav_conferencias_fila"] = contagem_nav_conferencias_fila
templates.env.globals["contagem_nav_relatorios"] = contagem_nav_relatorios
templates.env.globals["contagem_nav_relatorios_robo"] = contagem_nav_relatorios_robo


@router.get("/relatorios-robo")
def pagina_relatorios_robo(
    request: Request,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus")),
    processo: str | None = None,
    erro: str | None = None,
    sucesso: str | None = None,
):
    jobs = listar_jobs_robo()

    # Henrique, diretoria, 2026-08-27: a diretoria perguntou "o
    # coordenador fulano colocou os processos que pedi no robô?" e não
    # dava pra responder — "Robô automático" sozinho não diz QUEM pediu.
    # `job.solicitante_id` já vem carregado desde o upload pra relatório
    # NOVO (ver ChecagemFila.solicitante_id/checagem_fila.
    # registrar_pendente). Relatório de ANTES dessa coluna existir não
    # tem como ter isso preenchido — `resolver_solicitantes` cai pra
    # dedução por nome+horário nesses casos (Henrique, mesmo dia: "os
    # relatórios que já estavam prontos agora estão como não
    # identificado... manter aquela solução de antes como fallback").
    # Mesmo formato `nomes_por_id` de relatorios_manuais.py, pra
    # reaproveitar o mesmo bloco visual (.relatorio-solicitante) já
    # existente.
    nomes_por_id = {u.id: u.nome for u in listar_todos_usuarios()}
    solicitante_por_job_id = resolver_solicitantes(jobs)
    ids_solicitantes_reais = {sid for sid in solicitante_por_job_id.values() if sid}

    # Só os solicitantes que de fato aparecem na lista atual — dropdown
    # do filtro "Solicitado por", ordenado por nome (não a base de
    # usuários inteira, a maioria nunca mandou nada pro Robô). Henrique,
    # 2026-09-02: o PRÓPRIO usuário NÃO entra aqui à força só pra ter uma
    # opção — se ele nunca pediu nada, não faz sentido oferecer "ver só
    # os meus" como opção selecionável (ficaria sempre vazio); ver
    # `sem_solicitacoes_proprias` abaixo, que cobre esse caso à parte.
    solicitantes_disponiveis = sorted(
        (
            {"id": usuario_id, "nome": nomes_por_id.get(usuario_id, f"Usuário #{usuario_id}")}
            for usuario_id in ids_solicitantes_reais
        ),
        key=lambda item: item["nome"].lower(),
    )

    # Henrique, 2026-09-02: não-admin já abre a tela filtrado em "só os
    # meus" (ver filtro-solicitante no template + relatorios_robo.js) —
    # `solicitante_padrao` é só o valor inicial, a pessoa pode trocar
    # livremente pra "Todos" depois. Quando ela NUNCA pediu nada ainda,
    # não tem um valor real pra usar como padrão (ela nem aparece em
    # `solicitantes_disponiveis`) — nesse caso a tela mostra uma mensagem
    # dedicada no lugar da lista (ver template) em vez de aplicar um
    # filtro que corresponderia a uma opção inexistente no dropdown.
    solicitante_padrao = None
    sem_solicitacoes_proprias = False
    if not usuario.eh_admin:
        if usuario.id in ids_solicitantes_reais:
            solicitante_padrao = usuario.id
        else:
            sem_solicitacoes_proprias = True

    # Renderiza PRIMEIRO, marca como visto DEPOIS — mesmo motivo de
    # gerar_relatorio.py (senão o badge dessa própria visita nunca apareceria).
    resposta = templates.TemplateResponse(
        request,
        "relatorios_robo.html",
        {
            "usuario": usuario,
            "jobs": jobs,
            "nomes_por_id": nomes_por_id,
            "solicitante_por_job_id": solicitante_por_job_id,
            "solicitantes_disponiveis": solicitantes_disponiveis,
            "solicitante_padrao": solicitante_padrao,
            "sem_solicitacoes_proprias": sem_solicitacoes_proprias,
            # Deep-link vindo do botão "Ir ao relatório" (Conferências
            # manuais, web/routes/gerar_relatorio.py, quando o duplicado é do
            # Robô) — pré-preenche a busca, troca pra aba certa
            # (Sucesso/Revisão/Erro) e dá scroll/destaque, ver
            # relatorios_robo.js.
            "processo_busca": processo,
            "erro": erro,
            "sucesso": sucesso,
        },
    )
    marcar_aba_vista(usuario.id, FERRAMENTA_SLUG, ABA_RELATORIOS_ROBO)

    return resposta


@router.get("/relatorios-robo/{job_id}/pdf")
def ver_pdf_relatorio_robo_route(job_id: int):
    """Ver docstring equivalente em relatorios_manuais.py — mesma lógica."""
    job = obter_job(job_id)

    if not job or not job.destino_pdf:
        raise HTTPException(status_code=404, detail="PDF de origem não encontrado.")

    caminho = Path(job.destino_pdf)

    if not caminho.exists():
        raise HTTPException(status_code=404, detail="PDF de origem não encontrado.")

    return FileResponse(caminho, media_type="application/pdf")


def _redirecionar(erro=None, sucesso=None):
    partes = []

    if erro:
        partes.append(f"erro={quote(erro)}")

    if sucesso:
        partes.append(f"sucesso={quote(sucesso)}")

    query = f"?{'&'.join(partes)}" if partes else ""

    return RedirectResponse(url=f"/extratus/relatorios-robo{query}", status_code=303)


@router.post("/relatorios-robo/{job_id}/excluir")
def excluir_relatorio_robo_route(job_id: int, usuario: Usuario = Depends(exigir_admin)):
    """Mesma regra do equivalente manual (relatorios_manuais.py): só
    admin da plataforma exclui de verdade."""
    if not excluir_job(job_id):
        return _redirecionar(erro="Esse relatório não existe mais.")

    return _redirecionar(sucesso="Relatório excluído permanentemente.")


@router.post("/relatorios-robo/baixar-lote")
def baixar_lote_relatorios_robo(ids: list[int] = Form(...)):
    """Baixa vários relatórios do Robô de uma vez, num .zip só — Henrique,
    2026-09-02: "Baixar todos" (respeitando os filtros já aplicados na
    tela) e "Baixar selecionados" (modo de seleção) caem os dois aqui,
    mesmo endpoint — só muda quais ids o JS manda (ver relatorios_robo.js).
    Job "erro" nunca tem `relatorio_path` (nunca gerou arquivo de
    verdade) — pulado tanto por essa checagem quanto pelo status em si,
    de propósito redundante: Henrique pediu explicitamente "revisão sim,
    erro não", então o status vira uma segunda trava explícita, não só
    uma consequência indireta de "sem arquivo"."""
    buffer = BytesIO()
    nomes_usados = set()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_arquivo:
        for job_id in ids:
            job = obter_job(job_id)

            if not job or job.status == "erro" or not job.relatorio_path:
                continue

            caminho = Path(job.relatorio_path)

            if not caminho.exists():
                continue

            nome_no_zip = caminho.name
            if nome_no_zip in nomes_usados:
                nome_no_zip = f"{caminho.stem}_{job.id}{caminho.suffix}"
            nomes_usados.add(nome_no_zip)

            zip_arquivo.write(caminho, arcname=nome_no_zip)

    if not nomes_usados:
        return _redirecionar(erro="Nenhum dos relatórios selecionados tem arquivo pra baixar.")

    nome_zip = f"relatorios_robo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nome_zip}"'},
    )


@router.post("/relatorios-robo/excluir-lote")
def excluir_lote_relatorios_robo(ids: list[int] = Form(...), usuario: Usuario = Depends(exigir_admin)):
    """Exclui vários relatórios do Robô de uma vez — mesma regra do
    excluir individual (só admin da plataforma), reaproveitando
    excluir_job por trás, um a um."""
    excluidos = 0

    for job_id in ids:
        if excluir_job(job_id):
            excluidos += 1

    if excluidos == 0:
        return _redirecionar(erro="Nenhum dos relatórios selecionados existe mais.")

    mensagem = (
        "1 relatório excluído permanentemente."
        if excluidos == 1
        else f"{excluidos} relatórios excluídos permanentemente."
    )
    return _redirecionar(sucesso=mensagem)


@router.post("/relatorios-robo/{job_id}/marcar-notificacao-resolvida")
def marcar_notificacao_resolvida_robo_route(
    job_id: int,
    usuario: Usuario = Depends(exigir_acesso_ferramenta("extratus")),
):
    """X do "sucesso" do Robô na aba "Ferramentas" do sino — diferente
    do equivalente manual (relatorios_manuais.py), não tem dono: qualquer
    um com acesso à ferramenta pode dispensar (Henrique, diretoria,
    2026-08-19). "Revisão" e "erro" do Robô não têm esse botão de
    propósito, mesma exigência de "não pode sumir sozinho" que erro já
    tinha."""
    if not marcar_notificacao_resolvida_robo(job_id):
        raise HTTPException(status_code=404, detail="Esse relatório não existe mais.")

    return {"ok": True}
