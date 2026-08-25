import time

from fastapi.templating import Jinja2Templates

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
    templates.env.filters["emblema_ferramenta"] = emblema_ferramenta
    templates.env.globals["v"] = VERSAO_ESTATICOS

    return templates
