from fastapi.templating import Jinja2Templates

from app.plataforma.db.usuarios import listar_ferramentas_do_usuario


def criar_templates(directory):
    """Cria um Jinja2Templates com os globals que toda tela logada precisa
    — hoje, a lista de ferramentas do usuário pro seletor de apps no
    cabeçalho (base.html). Usar isso em vez de instanciar Jinja2Templates
    direto garante que qualquer tela nova já sai com o seletor funcionando,
    sem precisar lembrar de passar "ferramentas" em cada rota.
    """
    templates = Jinja2Templates(directory=directory)
    templates.env.globals["ferramentas_do_usuario"] = listar_ferramentas_do_usuario

    return templates
