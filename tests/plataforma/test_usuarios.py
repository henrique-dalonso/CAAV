import pytest
from sqlmodel import delete, select

from app.plataforma.db.models import (
    AcessoFerramenta,
    CARGO_COLABORADOR,
    CARGO_COORDENADOR,
    Ferramenta,
    UltimoVistoAba,
    Usuario,
    UsuarioFerramenta,
)
from app.plataforma.db.session import obter_sessao
from app.plataforma.db.usuarios import (
    alternar_admin,
    buscar_usuario_por_nome_usuario,
    criar_usuario,
    definir_cargo,
    definir_ferramentas,
    excluir_usuario,
    ferramenta_pela_url,
    listar_ferramentas_manual_ids,
    listar_ferramentas_liberadas_ids,
    listar_ferramentas_mais_usadas,
    marcar_aba_vista,
    obter_ultimo_visto,
    registrar_acesso_ferramenta,
    usuario_tem_acesso_a_alguma_fila_robo,
    usuario_tem_acesso_manual,
)
from app.plataforma.web.rotulos import emblema_ferramenta, rotulo_perfil


NOME_COORDENADOR_TESTE = "teste_usuarios_coord"
NOME_COLABORADOR_TESTE = "teste_usuarios_colab"


def _todos_ferramenta_ids():
    with obter_sessao() as sessao:
        return set(sessao.exec(select(Ferramenta.id)).all())


def _buscar_ferramenta_id_por_slug(slug):
    with obter_sessao() as sessao:
        return sessao.exec(select(Ferramenta.id).where(Ferramenta.slug == slug)).first()


def _apagar_usuarios_teste_e_vinculos():
    with obter_sessao() as sessao:
        ids = sessao.exec(
            select(Usuario.id).where(
                Usuario.nome_usuario.in_([NOME_COORDENADOR_TESTE, NOME_COLABORADOR_TESTE])
            )
        ).all()

        # Precisa apagar os vínculos de ferramenta primeiro — se não, o
        # SQLite pode reciclar o mesmo id de usuário num teste seguinte e
        # "herdar" ferramentas de um usuário de teste já apagado.
        if ids:
            sessao.exec(delete(UsuarioFerramenta).where(UsuarioFerramenta.usuario_id.in_(ids)))
            sessao.exec(delete(AcessoFerramenta).where(AcessoFerramenta.usuario_id.in_(ids)))
            sessao.exec(delete(UltimoVistoAba).where(UltimoVistoAba.usuario_id.in_(ids)))

        sessao.exec(
            delete(Usuario).where(
                Usuario.nome_usuario.in_([NOME_COORDENADOR_TESTE, NOME_COLABORADOR_TESTE])
            )
        )
        sessao.commit()


@pytest.fixture
def limpar_usuarios_teste():
    _apagar_usuarios_teste_e_vinculos()
    yield
    _apagar_usuarios_teste_e_vinculos()


def test_criar_coordenador_libera_todas_ferramentas_por_padrao(limpar_usuarios_teste):
    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
    )

    assert listar_ferramentas_liberadas_ids(usuario.id) == _todos_ferramenta_ids()


def test_criar_coordenador_com_selecao_customizada_respeita_a_selecao(limpar_usuarios_teste):
    # A tela pré-marca tudo pro admin desmarcar o que não quiser — se
    # vier uma lista explícita (mesmo que parcial), não pode virar "tudo"
    # de novo por baixo dos panos.
    todas = _todos_ferramenta_ids()
    uma_ferramenta = {next(iter(todas))}

    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
        ferramenta_ids=list(uma_ferramenta),
    )

    assert listar_ferramentas_liberadas_ids(usuario.id) == uma_ferramenta


def test_criar_colaborador_nao_libera_ferramenta_nenhuma(limpar_usuarios_teste):
    usuario = criar_usuario(
        nome="Teste Colaborador",
        nome_usuario=NOME_COLABORADOR_TESTE,
        email="teste_usuarios_colab@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COLABORADOR,
    )

    assert listar_ferramentas_liberadas_ids(usuario.id) == set()


def test_criar_usuario_com_cargo_invalido_falha(limpar_usuarios_teste):
    with pytest.raises(ValueError):
        criar_usuario(
            nome="Teste Cargo Ruim",
            nome_usuario=NOME_COLABORADOR_TESTE,
            email="teste_usuarios_colab@example.com",
            senha="senhaTeste123",
            eh_admin=False,
            cargo="rei",
        )


def test_promover_colaborador_a_coordenador_libera_todas_ferramentas(limpar_usuarios_teste):
    usuario = criar_usuario(
        nome="Teste Colaborador",
        nome_usuario=NOME_COLABORADOR_TESTE,
        email="teste_usuarios_colab@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COLABORADOR,
    )
    assert listar_ferramentas_liberadas_ids(usuario.id) == set()

    definir_cargo(usuario.id, CARGO_COORDENADOR)

    atualizado = buscar_usuario_por_nome_usuario(NOME_COLABORADOR_TESTE)
    assert atualizado.cargo == CARGO_COORDENADOR
    assert listar_ferramentas_liberadas_ids(usuario.id) == _todos_ferramenta_ids()


def test_rebaixar_coordenador_a_colaborador_nao_remove_ferramentas_ja_liberadas(
    limpar_usuarios_teste,
):
    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
    )
    liberadas_antes = listar_ferramentas_liberadas_ids(usuario.id)
    assert liberadas_antes == _todos_ferramenta_ids()

    definir_cargo(usuario.id, CARGO_COLABORADOR)

    # Rebaixar não deve tirar ferramenta nenhuma na hora — só o admin
    # ajusta manualmente se quiser restringir depois.
    assert listar_ferramentas_liberadas_ids(usuario.id) == liberadas_antes


class _UsuarioFalso:
    def __init__(self, eh_admin, cargo):
        self.eh_admin = eh_admin
        self.cargo = cargo


def test_rotulo_perfil_administrador():
    assert rotulo_perfil(_UsuarioFalso(eh_admin=True, cargo=CARGO_COLABORADOR)) == "Administrador"


def test_rotulo_perfil_coordenador():
    assert rotulo_perfil(_UsuarioFalso(eh_admin=False, cargo=CARGO_COORDENADOR)) == "Coordenador"


def test_rotulo_perfil_colaborador():
    assert rotulo_perfil(_UsuarioFalso(eh_admin=False, cargo=CARGO_COLABORADOR)) == "Colaborador"


def test_emblema_ferramenta_com_hifen_pega_uma_letra_de_cada_lado():
    assert emblema_ferramenta("Extratus - Aburesi") == "EA"
    assert emblema_ferramenta("Extratus - Relatórios") == "ER"


def test_emblema_ferramenta_sem_hifen_pega_so_a_primeira_letra():
    assert emblema_ferramenta("Crivus") == "C"


def test_emblema_ferramenta_vazio():
    assert emblema_ferramenta("") == ""


def test_colaborador_com_acesso_manual_tem_modo_manual(limpar_usuarios_teste):
    # Caso do "estagiário liberado pra urgência": colaborador comum, com
    # acesso_manual — só pode usar o fluxo Manual/URGENTE, não configurar
    # o robô (isso agora é admin-da-plataforma-only, ver admin_ferramentas.py).
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")

    usuario = criar_usuario(
        nome="Teste Colaborador",
        nome_usuario=NOME_COLABORADOR_TESTE,
        email="teste_usuarios_colab@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COLABORADOR,
        ferramenta_ids=[extratus_id],
        ferramentas_manual_ids=[extratus_id],
    )

    assert listar_ferramentas_manual_ids(usuario.id) == {extratus_id}
    assert usuario_tem_acesso_manual(usuario, "extratus") is True


def test_colaborador_sem_acesso_manual_nao_tem_manual(limpar_usuarios_teste):
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")

    usuario = criar_usuario(
        nome="Teste Colaborador",
        nome_usuario=NOME_COLABORADOR_TESTE,
        email="teste_usuarios_colab@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COLABORADOR,
        ferramenta_ids=[extratus_id],
    )

    assert usuario_tem_acesso_manual(usuario, "extratus") is False


def test_excluir_usuario_apaga_usuario_e_vinculos(limpar_usuarios_teste):
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")

    usuario = criar_usuario(
        nome="Teste Colaborador",
        nome_usuario=NOME_COLABORADOR_TESTE,
        email="teste_usuarios_colab@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COLABORADOR,
        ferramenta_ids=[extratus_id],
    )
    assert listar_ferramentas_liberadas_ids(usuario.id) == {extratus_id}

    excluir_usuario(usuario.id)

    assert buscar_usuario_por_nome_usuario(NOME_COLABORADOR_TESTE) is None
    assert listar_ferramentas_liberadas_ids(usuario.id) == set()


def test_criar_admin_ignora_ferramentas_mesmo_se_vierem_marcadas(limpar_usuarios_teste):
    # Regressão de um bug real: o bloco de cargo/ferramentas na tela de
    # criar usuário só fica ESCONDIDO (CSS) quando "Administrador? Sim" é
    # escolhido, não desabilitado — então checkboxes marcados antes de
    # trocar pra "Sim" ainda chegavam no POST. Isso criava vínculos
    # dormentes com acesso_manual=True que "ressurgiam" como acesso
    # indevido assim que a pessoa fosse rebaixada de admin depois.
    # criar_usuario tem que ignorar esses campos por completo quando
    # eh_admin=True, não só confiar que o front-end não vai mandá-los.
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")

    usuario = criar_usuario(
        nome="Teste Admin",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=True,
        cargo=CARGO_COORDENADOR,
        ferramenta_ids=[extratus_id],
        ferramentas_manual_ids=[extratus_id],
    )

    assert listar_ferramentas_liberadas_ids(usuario.id) == set()
    assert listar_ferramentas_manual_ids(usuario.id) == set()


def test_promover_a_admin_apaga_vinculos_de_ferramenta_existentes(limpar_usuarios_teste):
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")

    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
        ferramenta_ids=[extratus_id],
        ferramentas_manual_ids=[extratus_id],
    )
    assert listar_ferramentas_manual_ids(usuario.id) == {extratus_id}

    alternar_admin(usuario.id)  # promove a admin da plataforma

    assert listar_ferramentas_liberadas_ids(usuario.id) == set()
    assert listar_ferramentas_manual_ids(usuario.id) == set()


def test_rebaixar_de_admin_nao_ressuscita_acesso_manual_antigo(limpar_usuarios_teste):
    # Este é o bug relatado por Henrique, reproduzido de ponta a ponta:
    # promover a admin (que apaga vínculos antigos) e depois rebaixar não
    # pode devolver acesso_manual — só acesso básico à ferramenta.
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")

    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
        ferramenta_ids=[extratus_id],
        ferramentas_manual_ids=[extratus_id],
    )

    alternar_admin(usuario.id)  # promove
    alternar_admin(usuario.id)  # rebaixa de novo

    atualizado = buscar_usuario_por_nome_usuario(NOME_COORDENADOR_TESTE)

    # Acesso básico à ferramenta volta (senão a pessoa fica sem usar nada),
    # mas acesso_manual NÃO deve vir de graça de novo.
    assert listar_ferramentas_liberadas_ids(usuario.id) == _todos_ferramenta_ids()
    assert listar_ferramentas_manual_ids(usuario.id) == set()
    assert usuario_tem_acesso_manual(atualizado, "extratus") is False


def test_colaborador_com_acesso_basico_tem_acesso_a_alguma_fila(limpar_usuarios_teste):
    # Fila do Robô virou acesso padrão (Henrique, diretoria, 2026-08-19)
    # — não depende mais de uma flag própria, só de ter acesso básico a
    # uma ferramenta que suporta Robô.
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")

    usuario = criar_usuario(
        nome="Teste Colaborador",
        nome_usuario=NOME_COLABORADOR_TESTE,
        email="teste_usuarios_colab@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COLABORADOR,
        ferramenta_ids=[extratus_id],
    )

    assert usuario_tem_acesso_a_alguma_fila_robo(usuario) is True


def test_colaborador_sem_ferramenta_nenhuma_nao_tem_acesso_a_alguma_fila(limpar_usuarios_teste):
    usuario = criar_usuario(
        nome="Teste Colaborador",
        nome_usuario=NOME_COLABORADOR_TESTE,
        email="teste_usuarios_colab@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COLABORADOR,
    )

    assert usuario_tem_acesso_a_alguma_fila_robo(usuario) is False


def test_admin_da_plataforma_sempre_tem_acesso_a_alguma_fila(limpar_usuarios_teste):
    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=True,
    )

    assert usuario_tem_acesso_a_alguma_fila_robo(usuario) is True


def test_registrar_acesso_incrementa_contagem(limpar_usuarios_teste):
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")
    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
        ferramenta_ids=[extratus_id],
    )

    registrar_acesso_ferramenta(usuario.id, extratus_id)
    registrar_acesso_ferramenta(usuario.id, extratus_id)
    registrar_acesso_ferramenta(usuario.id, extratus_id)

    with obter_sessao() as sessao:
        acesso = sessao.get(AcessoFerramenta, (usuario.id, extratus_id))

    assert acesso.contagem == 3


def test_mais_usadas_ordena_pela_contagem_e_respeita_permissao(limpar_usuarios_teste):
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")
    aburesi_id = _buscar_ferramenta_id_por_slug("extratus-aburesi")
    crivus_id = _buscar_ferramenta_id_por_slug("leitor-publicacoes")

    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
        # só libera extratus e aburesi -- crivus fica de fora
        ferramenta_ids=[extratus_id, aburesi_id],
    )

    registrar_acesso_ferramenta(usuario.id, aburesi_id)
    for _ in range(3):
        registrar_acesso_ferramenta(usuario.id, extratus_id)
    # tenta registrar uso de uma ferramenta que ele nao tem acesso (nao
    # deveria acontecer na pratica, mas a consulta tem que ignorar mesmo assim)
    registrar_acesso_ferramenta(usuario.id, crivus_id)

    mais_usadas = listar_ferramentas_mais_usadas(usuario)

    assert [f.slug for f in mais_usadas] == ["extratus", "extratus-aburesi"]


def test_mais_usadas_vazio_para_quem_nunca_usou(limpar_usuarios_teste):
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")
    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
        ferramenta_ids=[extratus_id],
    )

    assert listar_ferramentas_mais_usadas(usuario) == []


# --- UltimoVistoAba — badges "+N" das abas (Henrique, 2026-08-13) ---

def test_obter_ultimo_visto_none_quando_nunca_visitou(limpar_usuarios_teste):
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")
    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
        ferramenta_ids=[extratus_id],
    )

    assert obter_ultimo_visto(usuario.id, "extratus", "relatorios") is None


def test_marcar_aba_vista_depois_obter_ultimo_visto_preenchido(limpar_usuarios_teste):
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")
    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
        ferramenta_ids=[extratus_id],
    )

    marcar_aba_vista(usuario.id, "extratus", "relatorios")

    assert obter_ultimo_visto(usuario.id, "extratus", "relatorios") is not None


def test_marcar_aba_vista_atualiza_registro_existente_em_vez_de_duplicar(limpar_usuarios_teste):
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")
    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
        ferramenta_ids=[extratus_id],
    )

    marcar_aba_vista(usuario.id, "extratus", "relatorios")
    primeira_visita = obter_ultimo_visto(usuario.id, "extratus", "relatorios")

    marcar_aba_vista(usuario.id, "extratus", "relatorios")
    segunda_visita = obter_ultimo_visto(usuario.id, "extratus", "relatorios")

    assert segunda_visita >= primeira_visita

    with obter_sessao() as sessao:
        total = sessao.exec(
            select(UltimoVistoAba).where(
                UltimoVistoAba.usuario_id == usuario.id,
                UltimoVistoAba.ferramenta_slug == "extratus",
                UltimoVistoAba.aba == "relatorios",
            )
        ).all()
        assert len(total) == 1


def test_marcar_aba_vista_nao_afeta_outra_aba(limpar_usuarios_teste):
    extratus_id = _buscar_ferramenta_id_por_slug("extratus")
    usuario = criar_usuario(
        nome="Teste Coordenador",
        nome_usuario=NOME_COORDENADOR_TESTE,
        email="teste_usuarios_coord@example.com",
        senha="senhaTeste123",
        eh_admin=False,
        cargo=CARGO_COORDENADOR,
        ferramenta_ids=[extratus_id],
    )

    marcar_aba_vista(usuario.id, "extratus", "relatorios")

    assert obter_ultimo_visto(usuario.id, "extratus", "relatorios-robo") is None


# --- ferramenta_pela_url — cor/marca de identidade em qualquer sub-página
# do módulo (Henrique, 2026-09-02: achado real, "marca-sistema-ferramenta"
# só aparecia em /extratus/fila (nome antigo da tela, hoje /fila-robo),
# voltava pra "Alonso & Verdiani" nas outras abas do MESMO módulo —
# comparava contra Ferramenta.url, que virou o link do ÍCONE, não mais o
# prefixo do módulo). ---

def test_ferramenta_pela_url_reconhece_qualquer_subpagina_do_modulo():
    assert ferramenta_pela_url("/extratus/fila-robo").slug == "extratus"
    assert ferramenta_pela_url("/extratus/relatorios-robo").slug == "extratus"
    assert ferramenta_pela_url("/extratus/relatorios-urgentes").slug == "extratus"
    assert ferramenta_pela_url("/extratus/").slug == "extratus"


def test_ferramenta_pela_url_nao_confunde_extratus_com_aburesi():
    # "/extratus-aburesi/..." também começa com a string "extratus" —
    # sem a barra de fronteira, um startswith ingênuo confundiria os dois.
    assert ferramenta_pela_url("/extratus-aburesi/fila-robo").slug == "extratus-aburesi"
    assert ferramenta_pela_url("/extratus-aburesi/relatorios-robo").slug == "extratus-aburesi"


def test_ferramenta_pela_url_fora_de_qualquer_modulo_devolve_none():
    assert ferramenta_pela_url("/admin") is None
    assert ferramenta_pela_url("/") is None
    assert ferramenta_pela_url("/login") is None


def test_ferramenta_pela_url_funciona_mesmo_com_slug_diferente_da_url():
    # Crivus: slug "leitor-publicacoes" (nunca muda, é o identificador de
    # permissão) mas rotas em "/crivus/..." — comparar por slug nunca
    # bateria; por segmento de url.py (Ferramenta.url = "/crivus/") bate.
    ferramenta = ferramenta_pela_url("/crivus/")
    assert ferramenta is not None
    assert ferramenta.slug == "leitor-publicacoes"
    assert ferramenta.nome == "Crivus"
