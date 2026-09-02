from typing import Optional

from sqlmodel import delete, select, update

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
    UltimoVistoAba,
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


def _marcar_acesso_manual(sessao, usuario_id, ferramenta_ids_manual):
    if not ferramenta_ids_manual:
        return

    vinculos = sessao.exec(
        select(UsuarioFerramenta).where(
            UsuarioFerramenta.usuario_id == usuario_id,
            UsuarioFerramenta.ferramenta_id.in_(ferramenta_ids_manual),
        )
    ).all()

    for vinculo in vinculos:
        vinculo.acesso_manual = True
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


def _agrupar_ferramenta_ids_por_usuario(condicao_extra=None):
    """Mesma ideia das 3 funções de um usuário só acima (liberadas/admin/
    manual), mas pra TODOS de uma vez — 1 consulta no total em vez de 1 por
    usuário. Usada pela tela de Usuários do admin (Rodada 12, achado de
    qualidade de código: 3 consultas × N usuários listados, virou 3 no
    total)."""
    with obter_sessao() as sessao:
        consulta = select(UsuarioFerramenta.usuario_id, UsuarioFerramenta.ferramenta_id)
        if condicao_extra is not None:
            consulta = consulta.where(condicao_extra)
        linhas = sessao.exec(consulta).all()

    resultado: dict[int, set[int]] = {}
    for usuario_id, ferramenta_id in linhas:
        resultado.setdefault(usuario_id, set()).add(ferramenta_id)
    return resultado


def listar_ferramentas_liberadas_ids_por_usuario():
    return _agrupar_ferramenta_ids_por_usuario()


def listar_ferramentas_manual_ids_por_usuario():
    return _agrupar_ferramenta_ids_por_usuario(UsuarioFerramenta.acesso_manual == True)  # noqa: E712


def usuario_tem_acesso_manual(usuario: Usuario, slug_ferramenta: str) -> bool:
    """Acesso ao fluxo Manual/URGENTE (Gerar Relatório URGENTE, Relatórios
    URGENTES) — Henrique, diretoria, 2026-08-19: virou exclusivo de quem
    tem essa flag (na prática, coordenadores), já que o Robô passou a
    ser o modo padrão pra todo mundo. Henrique, 2026-08-24: o OR com
    admin_ferramenta que existia aqui era um resto de código de antes do
    redesenho de acesso (Robô virou padrão, Urgente virou a exceção) —
    admin_ferramenta nunca teve relação de verdade com o modo Urgente,
    era engano. Removido junto da remoção de admin_ferramenta em si."""
    if usuario.eh_admin:
        return True

    with obter_sessao() as sessao:
        consulta = (
            select(UsuarioFerramenta)
            .join(Ferramenta, Ferramenta.id == UsuarioFerramenta.ferramenta_id)
            .where(
                UsuarioFerramenta.usuario_id == usuario.id,
                Ferramenta.slug == slug_ferramenta,
                UsuarioFerramenta.acesso_manual == True,  # noqa: E712
            )
        )
        return sessao.exec(consulta).first() is not None


def usuario_tem_acesso_a_alguma_fila_robo(usuario: Usuario) -> bool:
    """Versão "em qualquer ferramenta" de usuario_tem_acesso — usada só
    pra decidir se a aba "Ferramentas" do sininho de notificações (antiga
    "Conferências Robô", renomeada e ampliada 2026-08-19 — ver
    web/notificacoes.py) aparece pra alguém (Henrique, 2026-08-07: "Ela
    só será exibida para quem tiver acesso a pelo menos uma fila de
    Robô"). Henrique, diretoria, 2026-08-19: Fila do Robô virou acesso
    padrão de quem já usa a ferramenta — não filtra mais por uma flag
    própria, só por ter acesso básico a uma ferramenta que suporta
    Robô. Filtra por
    Ferramenta.suporta_fila_robo em vez de uma lista fixa de slugs —
    assim, uma ferramenta nova que ganhe fila do robô no futuro já
    entra automaticamente aqui, sem precisar lembrar de atualizar isso
    também (ver REGISTRO_NOTIFICACOES em web/notificacoes.py, que é uma
    lista fixa por um motivo diferente: lá precisa do import de cada
    listar_notificacoes(), que não tem como descobrir sozinho)."""
    if usuario.eh_admin:
        return True

    with obter_sessao() as sessao:
        consulta = (
            select(UsuarioFerramenta)
            .join(Ferramenta, Ferramenta.id == UsuarioFerramenta.ferramenta_id)
            .where(
                UsuarioFerramenta.usuario_id == usuario.id,
                Ferramenta.suporta_fila_robo == True,  # noqa: E712
            )
        )
        return sessao.exec(consulta).first() is not None


def listar_ferramentas_manual_ids(usuario_id: int):
    with obter_sessao() as sessao:
        consulta = select(UsuarioFerramenta.ferramenta_id).where(
            UsuarioFerramenta.usuario_id == usuario_id,
            UsuarioFerramenta.acesso_manual == True,  # noqa: E712
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


def ferramenta_pela_url(caminho):
    """Qual ferramenta "dona" desse caminho de URL, se alguma — usado pra
    saber de qual ferramenta puxar a cor de identidade (ver
    cor_ferramenta_atual, templates_util.py) em qualquer sub-página dela
    (não só a raiz, também funciona pra /extratus/fila, /extratus/relatorios
    etc.), já que o middleware de "Mais utilizadas" só faz esse match
    exato pra raiz, não serve pra isso.

    Henrique, 2026-09-02: achado real — comparava contra `Ferramenta.url`,
    mas esse campo virou o link de destino do ÍCONE (seed.py, deploy
    2026-08-21: "/extratus/fila", não mais a raiz "/extratus/"). Isso
    fazia o nome da ferramenta (marca-sistema-ferramenta) só aparecer
    dentro de /extratus/fila mesmo, voltando pra "Alonso & Verdiani" em
    qualquer outra aba do mesmo módulo. Usa `slug` (sempre o prefixo real
    de TODAS as rotas do módulo, ex: "extratus"/"extratus-aburesi") em
    vez de `url` — com barra de fronteira explícita pra "extratus" não
    casar com "/extratus-aburesi/...", que também começa com "extratus"."""
    with obter_sessao() as sessao:
        ferramentas = sessao.exec(select(Ferramenta)).all()

    candidatas = [
        f for f in ferramentas
        if caminho == f"/{f.slug}" or caminho.startswith(f"/{f.slug}/")
    ]

    if not candidatas:
        return None

    # Prefixo mais específico (slug mais longo) vence, se mais de um
    # bater — não acontece com as URLs de hoje, mas evita ambiguidade
    # silenciosa se um dia existir.
    return max(candidatas, key=lambda f: len(f.slug))


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


def obter_ultimo_visto(usuario_id, ferramenta_slug, aba):
    """Quando esse usuário viu essa aba pela última vez, ou None se nunca
    visitou — usado pelos badges "+N" (ver `web/rotulos.py` de cada
    ferramenta) pra saber a partir de quando contar o que é novo. `None`
    (nunca visitou) é tratado por quem chama como "desde sempre" — tudo
    que já existir hoje conta como novo, não é escondido só por nunca ter
    sido visto."""
    with obter_sessao() as sessao:
        registro = sessao.get(UltimoVistoAba, (usuario_id, ferramenta_slug, aba))
        return registro.visto_em if registro else None


def marcar_aba_vista(usuario_id, ferramenta_slug, aba):
    """Marca "vi agora" pra essa aba — chamado no início de cada rota que
    renderiza a página correspondente (antes do template calcular os
    badges), pra a própria página já carregar com o número zerado, não só
    a próxima visita."""
    with obter_sessao() as sessao:
        registro = sessao.get(UltimoVistoAba, (usuario_id, ferramenta_slug, aba))

        if registro:
            registro.visto_em = datetime.now()
        else:
            registro = UltimoVistoAba(usuario_id=usuario_id, ferramenta_slug=ferramenta_slug, aba=aba)

        sessao.add(registro)
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


def listar_todas_ferramentas():
    with obter_sessao() as sessao:
        return sessao.exec(select(Ferramenta)).all()


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
    ferramentas_manual_ids=None,
):
    if cargo not in CARGOS_VALIDOS:
        raise ValueError(f"Cargo inválido: {cargo!r}")

    ferramentas_manual_ids = set(ferramentas_manual_ids or [])

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
        # manual aqui quando eh_admin=True, mesmo que algo tenha vindo
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
                        acesso_manual=ferramenta_id in ferramentas_manual_ids,
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
                _marcar_acesso_manual(sessao, usuario.id, ferramentas_manual_ids)

        sessao.commit()
        # Esse commit expira os atributos já carregados em "usuario" — sem
        # um refresh de novo, ler usuario.id (ou qualquer campo) depois que
        # a função retorna quebra com DetachedInstanceError, já que a
        # sessão já fechou.
        sessao.refresh(usuario)

        return usuario


def definir_ferramentas(usuario_id, ferramenta_ids, ferramentas_manual_ids=None):
    ferramentas_manual_ids = set(ferramentas_manual_ids or [])

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
                    acesso_manual=ferramenta_id in ferramentas_manual_ids,
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
    causava o bug de "removi o admin e o Robô/Fila continuavam
    liberados", porque o vínculo antigo ressurgia assim que eh_admin virava
    False de novo). Ao REBAIXAR, devolvemos o acesso básico às ferramentas
    (sem acesso_manual, que continua precisando ser concedido à parte) —
    senão a pessoa ficaria sem usar nada."""
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


def incrementar_tentativas_falhas(usuario_id):
    """Soma 1 nas tentativas de senha erradas SEGUIDAS e devolve o novo
    total — quem decide se isso já é motivo de bloqueio é o chamador
    (auth.py), que conhece o limite (LIMITE_TENTATIVAS_USUARIO).

    UPDATE atômico (incremento feito pelo próprio banco, não
    ler-e-gravar em Python) — duas tentativas erradas simultâneas na
    mesma conta não podem mais "perder" um incremento uma por cima da
    outra."""
    with obter_sessao() as sessao:
        sessao.exec(
            update(Usuario)
            .where(Usuario.id == usuario_id)
            .values(tentativas_login_falhas=Usuario.tentativas_login_falhas + 1)
        )
        sessao.commit()
        usuario = sessao.get(Usuario, usuario_id)
        return usuario.tentativas_login_falhas


def resetar_tentativas_falhas(usuario_id):
    """Chamado em todo login bem-sucedido — qualquer acerto no meio zera
    a sequência de erros (Henrique, 2026-08-11: "consecutivas, zera ao
    acertar")."""
    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)
        usuario.tentativas_login_falhas = 0
        sessao.add(usuario)
        sessao.commit()


def bloquear_usuario_por_tentativas(usuario_id):
    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)
        usuario.bloqueado = True
        usuario.bloqueado_em = datetime.now()
        sessao.add(usuario)
        sessao.commit()


def desbloquear_usuario(usuario_id):
    """Ação de admin na tela de Usuários — só ela reabre uma conta
    travada por tentativas erradas (lembrar a senha certa sozinho não é
    suficiente, por desenho)."""
    with obter_sessao() as sessao:
        usuario = sessao.get(Usuario, usuario_id)
        usuario.bloqueado = False
        usuario.bloqueado_em = None
        usuario.tentativas_login_falhas = 0
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
