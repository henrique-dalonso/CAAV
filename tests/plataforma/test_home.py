from types import SimpleNamespace

from app.ferramentas.nucleo_relatorios.telas import REGISTRO_TELAS
from app.plataforma.web.routes.home import agrupar_ferramentas_extratus


def _ferramenta(slug, nome=None):
    return SimpleNamespace(slug=slug, nome=nome or slug)


SLUGS_FAMILIA = sorted({tela.slug_plataforma for tela in REGISTRO_TELAS.values()})


def test_agrupar_sem_nenhum_extratus_devolve_lista_igual():
    ferramentas = [_ferramenta("leitor-publicacoes", "Crivus")]

    resultado = agrupar_ferramentas_extratus(ferramentas)

    assert resultado == ferramentas


def test_agrupar_com_1_extratus_nao_agrupa():
    ferramentas = [_ferramenta(SLUGS_FAMILIA[0]), _ferramenta("leitor-publicacoes", "Crivus")]

    resultado = agrupar_ferramentas_extratus(ferramentas)

    assert resultado == ferramentas
    assert not any(isinstance(item, dict) for item in resultado)


def test_agrupar_com_2_ou_mais_extratus_agrupa_num_card_so():
    crivus = _ferramenta("leitor-publicacoes", "Crivus")
    ferramentas = [_ferramenta(slug) for slug in SLUGS_FAMILIA] + [crivus]

    resultado = agrupar_ferramentas_extratus(ferramentas)

    grupos = [item for item in resultado if isinstance(item, dict)]
    assert len(grupos) == 1

    grupo = grupos[0]
    assert grupo["agrupado"] is True
    assert grupo["nome"] == "Extratus"
    assert str(len(SLUGS_FAMILIA)) in grupo["descricao"]
    assert {item.slug for item in grupo["itens"]} == set(SLUGS_FAMILIA)

    # Crivus nunca entra no grupo, continua como item solto.
    assert crivus in resultado


def test_agrupar_mantem_posicao_alfabetica_da_primeira_ferramenta_da_familia():
    """O grupo entra onde a 1ª ferramenta da família apareceria na lista
    (já vem ordenada alfabeticamente por nome — ver
    listar_ferramentas_do_usuario), não sempre no início/fim."""
    crivus = _ferramenta("leitor-publicacoes", "Crivus")
    outra = _ferramenta("outra-ferramenta", "Zzz Depois")
    ferramentas = [crivus] + [_ferramenta(slug) for slug in SLUGS_FAMILIA] + [outra]

    resultado = agrupar_ferramentas_extratus(ferramentas)

    assert resultado[0] is crivus
    assert isinstance(resultado[1], dict)
    assert resultado[2] is outra
