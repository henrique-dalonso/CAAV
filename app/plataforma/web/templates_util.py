import time

from fastapi.templating import Jinja2Templates

from app.plataforma.db.usuarios import (
    listar_ferramentas_do_usuario,
    usuario_eh_admin_da_ferramenta,
    usuario_tem_acesso_fila_motor,
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


def criar_templates(directory):
    """Cria um Jinja2Templates com os globals que toda tela logada precisa
    — a lista de ferramentas do usuário pro seletor de apps, o rótulo de
    hierarquia (Administrador/Coordenador/Colaborador) pro card de perfil,
    as checagens de admin-de-ferramenta e fila-do-motor (pras abas
    Custos/Motor/Fila dentro de cada ferramenta), e o emblema (1-2 letras)
    de cada ferramenta. Usar isso em vez de instanciar Jinja2Templates
    direto garante que qualquer tela nova já sai com isso funcionando, sem
    precisar lembrar de passar nada em cada rota.
    """
    templates = Jinja2Templates(directory=directory)
    templates.env.globals["ferramentas_do_usuario"] = listar_ferramentas_do_usuario
    templates.env.globals["rotulo_perfil"] = rotulo_perfil
    templates.env.globals["usuario_eh_admin_da_ferramenta"] = usuario_eh_admin_da_ferramenta
    templates.env.globals["usuario_tem_acesso_fila_motor"] = usuario_tem_acesso_fila_motor
    templates.env.filters["emblema_ferramenta"] = emblema_ferramenta
    templates.env.globals["v"] = VERSAO_ESTATICOS

    return templates
