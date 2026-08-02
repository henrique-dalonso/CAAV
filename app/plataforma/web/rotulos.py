"""Rótulos amigáveis pra hierarquia de usuário — usados no cabeçalho
(card de perfil) e na tela de Perfil, em qualquer lugar que precise
mostrar "Administrador" / "Coordenador" / "Colaborador" pro usuário.
"""

from app.plataforma.db.models import CARGO_COORDENADOR

CARGO_LABELS = {
    CARGO_COORDENADOR: "Coordenador",
}


def rotulo_perfil(usuario):
    if usuario.eh_admin:
        return "Administrador"

    return CARGO_LABELS.get(usuario.cargo, "Colaborador")
