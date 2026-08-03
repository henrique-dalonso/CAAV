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


def emblema_ferramenta(nome):
    """Letra(s) mostradas no círculo/emblema de cada ferramenta (cartão da
    home, bandeja de apps do cabeçalho). Nomes compostos tipo "Extratus -
    Aburesi" viram 2 letras (1ª de cada lado do hífen: "EA") pra não ficar
    tudo com a mesma letra ("E") quando várias ferramentas compartilham o
    mesmo prefixo de marca. Nomes sem hífen continuam com 1 letra só,
    igual sempre foi.
    """
    nome = (nome or "").strip()

    if " - " in nome:
        antes, depois = nome.split(" - ", 1)
        antes = antes.strip()
        depois = depois.strip()

        if antes and depois:
            return (antes[0] + depois[0]).upper()

    return nome[:1].upper()
