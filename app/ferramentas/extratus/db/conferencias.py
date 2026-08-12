from app.ferramentas.extratus.db.models import RegistroConferencia
from app.plataforma.db.session import obter_sessao


def registrar_decisao(nome_arquivo, tipo_inconsistencia, decisao, usuario_id, processo_informado=None):
    """Grava PRA SEMPRE quem decidiu o quê no painel de Conferências —
    ver docstring de RegistroConferencia (db/models.py) pra entender por
    que isso é uma tabela própria, não um campo a mais em ChecagemFila
    ou Job. Chamado pela rota (web/routes/fila.py) depois de já ter
    executado a ação de verdade (checagem_fila.aprovar_manualmente ou
    .descartar) — esse registro é só o histórico, não decide nada."""
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
