from app.ferramentas.extratus_aburesi.db.models import RegistroConferencia
from app.plataforma.db.session import obter_sessao


def registrar_decisao(nome_arquivo, tipo_inconsistencia, decisao, usuario_id, processo_informado=None):
    """Ver docstring equivalente em app/ferramentas/extratus/db/
    conferencias.py (Extratus - Relatórios) — mesma lógica, tabela
    própria deste módulo (`_aburesi`)."""
    with obter_sessao() as sessao:
        registro = RegistroConferencia(
            nome_arquivo=nome_arquivo,
            tipo_inconsistencia=tipo_inconsistencia,
            decisao=decisao,
            usuario_id=usuario_id,
            processo_informado=processo_informado,
        )

        sessao.add(registro)
        sessao.commit()
        sessao.refresh(registro)

        return registro
