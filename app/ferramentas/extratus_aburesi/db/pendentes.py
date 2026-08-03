from sqlmodel import select

from app.ferramentas.extratus_aburesi.db.models import ArquivoPendente
from app.plataforma.db.session import obter_sessao


def registrar_pendente(nome_arquivo, usuario_id):
    """Anota que `usuario_id` foi quem enviou `nome_arquivo` pra fila
    manual — usado depois pra filtrar a listagem/"processar tudo" só aos
    PDFs do próprio usuário, mesmo a pasta sendo compartilhada no disco.
    """
    with obter_sessao() as sessao:
        sessao.add(ArquivoPendente(nome_arquivo=nome_arquivo, usuario_id=usuario_id))
        sessao.commit()


def listar_nomes_pendentes_do_usuario(usuario_id):
    with obter_sessao() as sessao:
        consulta = select(ArquivoPendente.nome_arquivo).where(
            ArquivoPendente.usuario_id == usuario_id
        )
        return set(sessao.exec(consulta).all())


def remover_pendente(nome_arquivo, usuario_id):
    """Tira o registro de rastreio depois que o PDF sai da pasta_entrada
    (processado ou removido) — não mexe no arquivo em si."""
    with obter_sessao() as sessao:
        consulta = select(ArquivoPendente).where(
            ArquivoPendente.nome_arquivo == nome_arquivo,
            ArquivoPendente.usuario_id == usuario_id,
        )
        vinculo = sessao.exec(consulta).first()

        if vinculo:
            sessao.delete(vinculo)
            sessao.commit()
