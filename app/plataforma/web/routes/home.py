from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.ferramentas.nucleo_relatorios.telas import REGISTRO_TELAS
from app.plataforma.db.models import Usuario
from app.plataforma.db.usuarios import listar_ferramentas_do_usuario, listar_ferramentas_mais_usadas
from app.plataforma.web.auth import exigir_login
from app.plataforma.web.templates_util import criar_templates


router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = criar_templates(TEMPLATES_DIR)


def agrupar_ferramentas_extratus(ferramentas):
    """Henrique, 2026-09-09: a grade "Ferramentas" do Hub ficava poluída
    com um card cheio pra cada variante do Extratus (Relatórios/Aburesi/
    Emendas, Cálculo a caminho) — pra quem tem acesso a 2+ delas, agrupa
    num card só, mantendo a posição alfabética de onde a primeira delas
    cairia. Com 0 ou 1 (a maioria dos usuários, que só usa uma variante),
    devolve a lista tal como veio, sem nenhum agrupamento.

    Família = quem está em REGISTRO_TELAS (o motor compartilhado,
    nucleo_relatorios/telas.py) — nunca uma lista solta de slugs
    duplicada aqui, pra uma futura tela nova (Cálculo) entrar sozinha
    assim que for cadastrada lá. Usa `slug_plataforma` (não
    `ferramenta_slug`): são conceitos diferentes, ver docstring de
    TelaConfig — Extratus-Relatórios por exemplo é "extratus-relatorios"
    de um lado e só "extratus" do outro (permissão/URL histórica).

    Só mexe na grade do Hub — a bandeja de apps do cabeçalho continua
    lendo `listar_ferramentas_do_usuario` direto, sem passar por aqui."""
    slugs_familia = {tela.slug_plataforma for tela in REGISTRO_TELAS.values()}
    da_familia = [f for f in ferramentas if f.slug in slugs_familia]

    if len(da_familia) <= 1:
        return ferramentas

    grupo = {
        "agrupado": True,
        "nome": "Extratus",
        "descricao": f"{len(da_familia)} módulos disponíveis",
        "itens": da_familia,
    }

    resultado = []
    grupo_inserido = False
    for ferramenta in ferramentas:
        if ferramenta.slug in slugs_familia:
            if not grupo_inserido:
                resultado.append(grupo)
                grupo_inserido = True
            continue
        resultado.append(ferramenta)

    return resultado


def obter_saudacao():
    hora = datetime.now().hour

    if hora < 12:
        return "Bom dia"

    if hora < 18:
        return "Boa tarde"

    return "Boa noite"


@router.get("/")
def pagina_inicial(request: Request, usuario: Usuario = Depends(exigir_login)):
    ferramentas = agrupar_ferramentas_extratus(listar_ferramentas_do_usuario(usuario))
    mais_usadas = listar_ferramentas_mais_usadas(usuario)
    primeiro_nome = usuario.nome.split(" ")[0]

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "usuario": usuario,
            "primeiro_nome": primeiro_nome,
            "saudacao": obter_saudacao(),
            "ferramentas": ferramentas,
            "mais_usadas": mais_usadas,
        },
    )
