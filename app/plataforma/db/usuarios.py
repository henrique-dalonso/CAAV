from typing import Optional

from sqlmodel import delete, select

from datetime import datetime

from app.plataforma.auth import gerar_hash_senha
from app.plataforma.db.models import (
    AcessoFerramenta,
    CARGO_COLABORADOR,
    CARGO_COORDENADOR,
    CARGOS_VALIDOS,
    CORES_PERFIL_VALIDAS,
    Ferramenta,
    TEMAS_VALIDOS,
    Usuario,
    UsuarioFerramenta,
)
from app.plataforma.db.session import obter_sessao


def _conceder_todas_ferramentas(sessao, usuario_id):
    ja_liberadas = set(
        sessao.exec(
            select(UsuarioFerramenta.ferramenta_id).where(
                UsuarioFerramenta.usuario_id == usuario_id
            )
        ).all()
    )

    for ferramenta_id in sessao.exec(select(Ferramenta.id)).all():
        if ferramenta_id not in ja_liberadas:
            sessao.add(
                UsuarioFerramenta(usuario_id=usuario_id, ferramenta_id=ferramenta_id)
            )


def _marcar_admin_ferramenta(sessao, usuario_id, ferramenta_ids_admin):
    if not ferramenta_ids_admin:
        return

    vinculos = sessao.exec(
        select(UsuarioFerramenta).where(
            UsuarioFerramenta.usuario_id == usuario_id,
            UsuarioFerramenta.ferramenta_id.in_(ferramenta_ids_admin),
        )
    ).all()

    for vinculo in vinculos:
        vinculo.admin_ferramenta = True
        sessao.add(vinculo)


def _marcar_fila_motor(sessao, usuario_id, ferramenta_ids_fila):
    if not ferramenta_ids_fila:
        return

    vinculos = sessao.exec(
        select(UsuarioFerramenta).where(
            UsuarioFerramenta.usuario_id == usuario_id,
            UsuarioFerramenta.ferramenta_id.in_(ferramenta_ids_fila),
        )
    ).all()

    for vinculo in vinculos:
        vinculo.fila_motor = True
        sessao.add(vinculo)


def buscar_usuario_por_nome_usuario(nome_usuario: str) -> Optional[Usuario]:
    with obter_sessao() as sessao:
        consulta = select(Usuario).where(
            Usuario.nome_usuario == nome_usuario,
            Usuario.ativo == True,  # noqa: E712
        )
        return sessao.exec(consulta).first()


def buscar_usuario_por_id(usuario_id: int) -> Optional[Usuario]:
    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)

        if usuario and not usuario.ativo:
            return None

        return usuario


def usuario_tem_acesso(usuario: Usuario, slug_ferramenta: str) -> bool:
    if usuario.eh_admin:
        return True

    with obter_sessao() as sessao:
        consulta = (
            select(UsuarioFerramenta)
            .join(Ferramenta, Ferramenta.id == UsuarioFerramenta.ferramenta_id)
            .where(
                UsuarioFerramenta.usuario_id == usuario.id,
                Ferramenta.slug == slug_ferramenta,
            )
        )
        return sessao.exec(consulta).first() is not None


def usuario_eh_admin_da_ferramenta(usuario: Usuario, slug_ferramenta: str) -> bool:
    """Acesso às abas administrativas DENTRO de uma ferramenta específica
    (ex: Custos e Motor no Extratus) — não confundir com exigir_admin, que
    é a área de Administração da plataforma inteira. Admin da plataforma
    sempre tem isso também; coordenador só se foi liberado explicitamente
    ferramenta por ferramenta."""
    if usuario.eh_admin:
        return True

    with obter_sessao() as sessao:
        consulta = (
            select(UsuarioFerramenta)
            .join(Ferramenta, Ferramenta.id == UsuarioFerramenta.ferramenta_id)
            .where(
                UsuarioFerramenta.usuario_id == usuario.id,
                Ferramenta.slug == slug_ferramenta,
                UsuarioFerramenta.admin_ferramenta == True,  # noqa: E712
            )
        )
        return sessao.exec(consulta).first() is not None


def listar_ferramentas_admin_ids(usuario_id: int):
    with obter_sessao() as sessao:
        consulta = select(UsuarioFerramenta.ferramenta_id).where(
            UsuarioFerramenta.usuario_id == usuario_id,
            UsuarioFerramenta.admin_ferramenta == True,  # noqa: E712
        )
        return set(sessao.exec(consulta).all())


def usuario_tem_acesso_fila_motor(usuario: Usuario, slug_ferramenta: str) -> bool:
    """Acesso à aba de Fila do motor (upload em lote pra pasta universal
    do motor) — independente de admin_ferramenta: um coordenador admin da
    ferramenta sempre tem, mas um colaborador também pode ter só isso,
    sem ganhar acesso a ligar/desligar o motor nem às configs dele."""
    if usuario.eh_admin:
        return True

    with obter_sessao() as sessao:
        consulta = (
            select(UsuarioFerramenta)
            .join(Ferramenta, Ferramenta.id == UsuarioFerramenta.ferramenta_id)
            .where(
                UsuarioFerramenta.usuario_id == usuario.id,
                Ferramenta.slug == slug_ferramenta,
                (UsuarioFerramenta.fila_motor == True)  # noqa: E712
                | (UsuarioFerramenta.admin_ferramenta == True),  # noqa: E712
            )
        )
        return sessao.exec(consulta).first() is not None


def listar_ferramentas_fila_ids(usuario_id: int):
    with obter_sessao() as sessao:
        consulta = select(UsuarioFerramenta.ferramenta_id).where(
            UsuarioFerramenta.usuario_id == usuario_id,
            UsuarioFerramenta.fila_motor == True,  # noqa: E712
        )
        return set(sessao.exec(consulta).all())


def listar_ferramentas_do_usuario(usuario: Usuario):
    """Devolve as ferramentas do usuário em ordem alfabética por nome —
    mesma fonte usada pela home e pela bandeja de apps do cabeçalho, então
    as duas sempre mostram a mesma ordem (a bandeja ainda pode reordenar
    favoritos pra frente disso, por cima, via JS)."""
    with obter_sessao() as sessao:
        if usuario.eh_admin:
            return sessao.exec(select(Ferramenta).order_by(Ferramenta.nome)).all()

        consulta = (
            select(Ferramenta)
            .join(UsuarioFerramenta, UsuarioFerramenta.ferramenta_id == Ferramenta.id)
            .where(UsuarioFerramenta.usuario_id == usuario.id)
            .order_by(Ferramenta.nome)
        )
        return sessao.exec(consulta).all()


def registrar_acesso_ferramenta(usuario_id, ferramenta_id):
    """Soma 1 no contador de uso dessa ferramenta pra esse usuário —
    chamado uma vez por visita à página principal de qualquer ferramenta
    (ver middleware em app/plataforma/web/main.py). Alimenta o bloco "Mais
    utilizadas" da home."""
    with obter_sessao() as sessao:
        acesso = sessao.get(AcessoFerramenta, (usuario_id, ferramenta_id))

        if acesso:
            acesso.contagem += 1
            acesso.ultimo_acesso = datetime.now()
        else:
            acesso = AcessoFerramenta(usuario_id=usuario_id, ferramenta_id=ferramenta_id, contagem=1)

        sessao.add(acesso)
        sessao.commit()


def listar_ferramentas_mais_usadas(usuario: Usuario, limite=6):
    """As ferramentas que esse usuário mais abriu, mais usada primeiro —
    só entre as que ele ainda tem acesso (se o acesso foi revogado depois
    de usar, some daqui também). Devolve lista vazia pra quem ainda não
    usou nada (conta nova, ou só favoritos sem uso real)."""
    permitidas = {f.id for f in listar_ferramentas_do_usuario(usuario)}

    if not permitidas:
        return []

    with obter_sessao() as sessao:
        consulta = (
            select(Ferramenta)
            .join(AcessoFerramenta, AcessoFerramenta.ferramenta_id == Ferramenta.id)
            .where(
                AcessoFerramenta.usuario_id == usuario.id,
                Ferramenta.id.in_(permitidas),
            )
            .order_by(AcessoFerramenta.contagem.desc(), AcessoFerramenta.ultimo_acesso.desc())
            .limit(limite)
        )
        return sessao.exec(consulta).all()


def listar_todos_usuarios():
    with obter_sessao() as sessao:
        return sessao.exec(select(Usuario).order_by(Usuario.nome)).all()


def listar_ferramentas_liberadas_ids(usuario_id: int):
    with obter_sessao() as sessao:
        consulta = select(UsuarioFerramenta.ferramenta_id).where(
            UsuarioFerramenta.usuario_id == usuario_id
        )
        return set(sessao.exec(consulta).all())


def criar_usuario(
    nome,
    nome_usuario,
    email,
    senha,
    eh_admin,
    cargo=CARGO_COLABORADOR,
    ferramenta_ids=None,
    ferramentas_admin_ids=None,
    ferramentas_fila_ids=None,
):
    if cargo not in CARGOS_VALIDOS:
        raise ValueError(f"Cargo inválido: {cargo!r}")

    ferramentas_admin_ids = set(ferramentas_admin_ids or [])
    ferramentas_fila_ids = set(ferramentas_fila_ids or [])

    with obter_sessao() as sessao:
        ja_existe = sessao.exec(
            select(Usuario).where(
                (Usuario.nome_usuario == nome_usuario) | (Usuario.email == email)
            )
        ).first()

        if ja_existe:
            raise ValueError("Já existe um usuário com esse nome de usuário ou e-mail.")

        usuario = Usuario(
            nome=nome,
            nome_usuario=nome_usuario,
            email=email,
            senha_hash=gerar_hash_senha(senha),
            eh_admin=eh_admin,
            cargo=cargo,
        )
        sessao.add(usuario)
        sessao.commit()
        sessao.refresh(usuario)

        # Admin da plataforma tem acesso a tudo de forma inerente, nunca
        # via UsuarioFerramenta — por isso ignoramos ferramenta_ids/admin/
        # fila aqui quando eh_admin=True, mesmo que algo tenha vindo
        # marcado no formulário (ex: o bloco de cargo/ferramentas é só
        # ESCONDIDO por CSS quando "Administrador? Sim" é escolhido, não
        # desabilitado — então checkboxes marcados antes de trocar pra
        # "Sim" ainda seriam enviados no POST se a gente não bloqueasse
        # aqui). Isso evita vínculos dormentes que ressurgem como acesso
        # indevido caso essa pessoa seja rebaixada de admin depois.
        if not eh_admin:
            for ferramenta_id in (ferramenta_ids or []):
                sessao.add(
                    UsuarioFerramenta(
                        usuario_id=usuario.id,
                        ferramenta_id=ferramenta_id,
                        admin_ferramenta=ferramenta_id in ferramentas_admin_ids,
                        fila_motor=ferramenta_id in ferramentas_fila_ids,
                    )
                )

            # Coordenador tem todas as ferramentas liberadas por padrão. Se
            # quem criou já escolheu ferramentas específicas no seletor (a
            # tela pré-marca tudo pro admin desmarcar o que não quiser), essa
            # escolha foi respeitada no laço acima — só completa com "tudo"
            # aqui quando não veio nada (ex: chamada fora da tela de admin,
            # como o script de bootstrap).
            if cargo == CARGO_COORDENADOR and not ferramenta_ids:
                _conceder_todas_ferramentas(sessao, usuario.id)
                _marcar_admin_ferramenta(sessao, usuario.id, ferramentas_admin_ids)
                _marcar_fila_motor(sessao, usuario.id, ferramentas_fila_ids)

        sessao.commit()
        # Esse commit expira os atributos já carregados em "usuario" — sem
        # um refresh de novo, ler usuario.id (ou qualquer campo) depois que
        # a função retorna quebra com DetachedInstanceError, já que a
        # sessão já fechou.
        sessao.refresh(usuario)

        return usuario


def definir_ferramentas(usuario_id, ferramenta_ids, ferramentas_admin_ids=None, ferramentas_fila_ids=None):
    ferramentas_admin_ids = set(ferramentas_admin_ids or [])
    ferramentas_fila_ids = set(ferramentas_fila_ids or [])

    with obter_sessao() as sessao:
        atuais = sessao.exec(
            select(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_id)
        ).all()

        for vinculo in atuais:
            sessao.delete(vinculo)

        for ferramenta_id in ferramenta_ids:
            sessao.add(
                UsuarioFerramenta(
                    usuario_id=usuario_id,
                    ferramenta_id=ferramenta_id,
                    admin_ferramenta=ferramenta_id in ferramentas_admin_ids,
                    fila_motor=ferramenta_id in ferramentas_fila_ids,
                )
            )

        sessao.commit()


def alternar_ativo(usuario_id):
    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)
        usuario.ativo = not usuario.ativo
        sessao.add(usuario)
        sessao.commit()
        return usuario.ativo


def alternar_admin(usuario_id):
    """Liga/desliga `eh_admin`. Admin da plataforma tem acesso a tudo de
    forma inerente (nunca via UsuarioFerramenta) — por isso, ao PROMOVER,
    apagamos qualquer vínculo por ferramenta que porventura já existisse
    (não tem mais função nenhuma, e ficar dormente aí é exatamente o que
    causava o bug de "removi o admin e o Motor/Fila continuavam
    liberados", porque o vínculo antigo ressurgia assim que eh_admin virava
    False de novo). Ao REBAIXAR, devolvemos o acesso básico às ferramentas
    (sem admin_ferramenta/fila_motor, que continuam precisando ser
    concedidos à parte) — senão a pessoa ficaria sem usar nada."""
    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)
        usuario.eh_admin = not usuario.eh_admin
        sessao.add(usuario)

        if usuario.eh_admin:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_id))
        else:
            _conceder_todas_ferramentas(sessao, usuario_id)

        sessao.commit()
        return usuario.eh_admin


def excluir_usuario(usuario_id):
    """Exclusão física — apaga os vínculos de ferramenta primeiro (senão
    um id reciclado pelo SQLite pode "herdar" permissões de um usuário
    já apagado, mesmo bug já visto nos testes) e depois o usuário."""
    with obter_sessao() as sessao:
        sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id == usuario_id))

        usuario = sessao.get(Usuario, usuario_id)
        if usuario:
            sessao.delete(usuario)

        sessao.commit()


def atualizar_senha(usuario_id, nova_senha_hash):
    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)
        usuario.senha_hash = nova_senha_hash
        sessao.add(usuario)
        sessao.commit()


def atualizar_tema(usuario_id, tema):
    if tema not in TEMAS_VALIDOS:
        raise ValueError(f"Tema inválido: {tema!r}")

    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)
        usuario.tema = tema
        sessao.add(usuario)
        sessao.commit()


def atualizar_cor_perfil(usuario_id, cor):
    if cor not in CORES_PERFIL_VALIDAS:
        raise ValueError(f"Cor de perfil inválida: {cor!r}")

    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)
        usuario.cor_perfil = cor
        sessao.add(usuario)
        sessao.commit()


def definir_cargo(usuario_id, cargo):
    if cargo not in CARGOS_VALIDOS:
        raise ValueError(f"Cargo inválido: {cargo!r}")

    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)
        usuario.cargo = cargo
        sessao.add(usuario)

        # Promover a coordenador libera todas as ferramentas na hora —
        # rebaixar não tira nada automaticamente (evita surpresa; admin
        # ajusta na mão se precisar restringir).
        if cargo == CARGO_COORDENADOR:
            _conceder_todas_ferramentas(sessao, usuario_id)

        sessao.commit()
        return usuario.cargo
