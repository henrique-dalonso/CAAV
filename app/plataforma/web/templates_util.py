import time

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app.plataforma.db.usuarios import (
    ferramenta_pela_url,
    listar_ferramentas_do_usuario,
    usuario_tem_acesso_a_alguma_fila_robo,
    usuario_tem_acesso_manual,
)
from app.plataforma.web.rotulos import emblema_ferramenta, rotulo_perfil


# Carimbo fixado uma vez quando o processo do servidor sobe (não muda
# durante a execução) — usado como "?v=..." em CSS/JS pra forçar o
# navegador a buscar a versão nova depois de um reinício do servidor, em
# vez de continuar servindo do cache uma folha de estilo antiga. O
# servidor hoje roda sem --reload (ver iniciar_servidor.bat, na raiz), então
# trocar um arquivo CSS só tem efeito depois de reiniciar o processo —
# isso aqui resolve a MERA parte de cache do navegador, não substitui
# reiniciar o servidor quando o código muda.
VERSAO_ESTATICOS = str(int(time.time()))


def cor_ferramenta_atual(request):
    """Ferramenta "dona" da página atual (pelo caminho da URL), se
    alguma — base.html usa isso pra injetar a cor de identidade daquela
    ferramenta como variável CSS, em vez de cada ferramenta precisar de
    um bloco :root próprio fixado no seu extratus.css."""
    return ferramenta_pela_url(request.url.path)


# Botão "Voltar", 3ª geração (2026-09-13) — as 2 anteriores foram
# descartadas na prática (ver [[extratus-botao-voltar-universal]] na
# memória): nome dinâmico da tela ("ficou horrível") e position:fixed
# ancorado perto da logo ("parecia tapa-buraco"). Henrique também não
# gostou de uma 3ª tentativa dentro do cabeçalho (.marca-sistema, ao
# lado da logo) — pediu pra encaixar junto ao TÍTULO de cada tela em
# vez disso (onde esse tipo de botão normalmente fica, e onde o olho já
# vai quando a página troca).
#
# Por isso NÃO fica em base.html (que não sabe o que cada página tem
# dentro do próprio <h1>) — é uma função global do Jinja, chamada como
# `{{ botao_voltar() }}` logo depois de cada `<h1>` (ver
# app/plataforma/web/static/base.css .cabecalho-ferramenta h1, que já
# vira flex pra acomodar o botão + o texto na mesma linha). Fica de fora
# de propósito em home.html (Hub) e login.html — nenhum dos dois usa
# .cabecalho-ferramenta/<h1> desse jeito, então nunca chamam essa
# função, sem precisar de nenhuma checagem explícita de rota.
#
# Continua usando history.back() do navegador (não uma "última página"
# calculada no servidor) — única forma de refletir corretamente
# navegação via JavaScript dentro de uma ferramenta (troca de aba sem
# recarregar a página).
_BOTAO_VOLTAR_HTML = Markup(
    '<button type="button" class="botao-voltar-titulo" onclick="history.back()" data-dica="Voltar">'
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<polyline points="15 18 9 12 15 6"></polyline>'
    "</svg>"
    "</button>"
)


def botao_voltar():
    return _BOTAO_VOLTAR_HTML


def criar_templates(directory):
    """Cria um Jinja2Templates com os globals que toda tela logada precisa
    — a lista de ferramentas do usuário pro seletor de apps, o rótulo de
    hierarquia (Administrador/Coordenador/Colaborador) pro card de perfil,
    a checagem de acesso-manual (abas Gerar Relatório URGENTE/Relatórios
    URGENTES), e o emblema (1-2 letras) de cada ferramenta. Usar isso em
    vez de instanciar Jinja2Templates direto garante que qualquer tela
    nova já sai com isso funcionando, sem precisar lembrar de passar
    nada em cada rota.
    """
    templates = Jinja2Templates(directory=directory)
    templates.env.globals["ferramentas_do_usuario"] = listar_ferramentas_do_usuario
    templates.env.globals["rotulo_perfil"] = rotulo_perfil
    templates.env.globals["usuario_tem_acesso_manual"] = usuario_tem_acesso_manual
    templates.env.globals["usuario_tem_acesso_a_alguma_fila_robo"] = usuario_tem_acesso_a_alguma_fila_robo
    templates.env.globals["cor_ferramenta_atual"] = cor_ferramenta_atual
    templates.env.globals["botao_voltar"] = botao_voltar
    templates.env.filters["emblema_ferramenta"] = emblema_ferramenta
    templates.env.globals["v"] = VERSAO_ESTATICOS

    return templates
