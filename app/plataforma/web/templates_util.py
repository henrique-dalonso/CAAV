from fastapi.templating import Jinja2Templates

from app.plataforma.db.usuarios import (
    listar_ferramentas_do_usuario,
    usuario_eh_admin_da_ferramenta,
    usuario_tem_acesso_fila_motor,
)
from app.plataforma.web.rotulos import rotulo_perfil


def criar_templates(directory):
    """Cria um Jinja2Templates com os globals que toda tela logada precisa
    — a lista de ferramentas do usuário pro seletor de apps, o rótulo de
    hierarquia (Administrador/Coordenador/Colaborador) pro card de perfil,
    e as checagens de admin-de-ferramenta e fila-do-motor (pras abas
    Custos/Motor/Fila dentro de cada ferramenta). Usar isso em vez de
    instanciar Jinja2Templates direto garante que qualquer tela nova já
    sai com isso funcionando, sem precisar lembrar de passar nada em cada
    rota.
    """
    templates = Jinja2Templates(directory=directory)
    templates.env.globals["ferramentas_do_usuario"] = listar_ferramentas_do_usuario
    templates.env.globals["rotulo_perfil"] = rotulo_perfil
    templates.env.globals["usuario_eh_admin_da_ferramenta"] = usuario_eh_admin_da_ferramenta
    templates.env.globals["usuario_tem_acesso_fila_motor"] = usuario_tem_acesso_fila_motor

    return templates
