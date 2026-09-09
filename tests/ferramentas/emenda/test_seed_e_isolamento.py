from sqlmodel import delete, select

from app.ferramentas.nucleo_relatorios.db.jobs import (
    listar_jobs_manuais,
    listar_jobs_robo,
    registrar_processado,
)
from app.ferramentas.nucleo_relatorios.db.models import Job
from app.ferramentas.nucleo_relatorios.tipos import REGISTRO_TIPOS
from app.plataforma.db.models import Ferramenta
from app.plataforma.db.session import obter_sessao


ARQUIVO_TESTE_EMENDA = "teste_isolamento_emenda.pdf"
ARQUIVO_TESTE_RELATORIOS = "teste_isolamento_relatorios_vs_emenda.pdf"

# ID negativo de propósito — não colide com usuário real, mesmo padrão de
# tests/ferramentas/extratus_aburesi/test_seed_e_isolamento.py.
USUARIO_TESTE = -9199


def test_ferramenta_emenda_registrada_com_dados_corretos():
    with obter_sessao() as sessao:
        ferramenta = sessao.exec(
            select(Ferramenta).where(Ferramenta.slug == "emenda")
        ).first()

    assert ferramenta is not None
    assert ferramenta.nome == "Extratus - Emendas"
    assert ferramenta.url == "/emenda/fila-robo"
    assert ferramenta.suporta_fila_robo is True
    # Cor própria (roxo) — não deve ficar sem identidade (None cairia no
    # azul padrão da plataforma, ver seed.py::_SEM_COR_PROPRIA).
    assert ferramenta.cor_acento == "#7c3aed"


def test_tipo_emenda_registrado_no_motor_compartilhado():
    """Ver nucleo_relatorios/tipos.py — "emenda" precisa existir ao lado
    de "bancario" sem substituí-lo (extratus/extratus_aburesi continuam
    usando "bancario")."""
    assert "bancario" in REGISTRO_TIPOS
    assert "emenda" in REGISTRO_TIPOS

    tipo_emenda = REGISTRO_TIPOS["emenda"]
    assert tipo_emenda.chave == "emenda"
    assert tipo_emenda.pos_processar is not None
    assert tipo_emenda.template_docx_path.name == "emenda.docx"


def test_job_de_emenda_nao_aparece_em_relatorios_e_vice_versa():
    """Mesma prova de isolamento por `ferramenta_slug` que já existe pra
    extratus/extratus_aburesi (ver test_seed_e_isolamento.py de lá) —
    Emenda entra na MESMA tabela `Job` compartilhada (motor único), então
    a isolação inteira depende desse filtro nunca falhar silenciosamente."""
    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.arquivo_pdf.in_([ARQUIVO_TESTE_EMENDA, ARQUIVO_TESTE_RELATORIOS])))
        sessao.commit()

    try:
        registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_EMENDA,
            processo="0000000-00.2026.8.00.0800",
            relatorio_path="relatorio_teste_emenda.docx",
            destino_pdf="processados/" + ARQUIVO_TESTE_EMENDA,
            confianca="alta",
            usuario_id=USUARIO_TESTE,
            ferramenta_slug="emenda",
            tipo_relatorio="emenda",
        )
        registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_RELATORIOS,
            processo="0000000-00.2026.8.00.0801",
            relatorio_path="relatorio_teste_relatorios_vs_emenda.docx",
            destino_pdf="processados/" + ARQUIVO_TESTE_RELATORIOS,
            confianca="alta",
            usuario_id=USUARIO_TESTE,
            ferramenta_slug="extratus-relatorios",
        )

        nomes_emenda = {job.arquivo_pdf for job in listar_jobs_manuais(ferramenta_slug="emenda")}
        nomes_relatorios = {job.arquivo_pdf for job in listar_jobs_manuais(ferramenta_slug="extratus-relatorios")}

        assert ARQUIVO_TESTE_EMENDA in nomes_emenda
        assert ARQUIVO_TESTE_EMENDA not in nomes_relatorios

        assert ARQUIVO_TESTE_RELATORIOS in nomes_relatorios
        assert ARQUIVO_TESTE_RELATORIOS not in nomes_emenda
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.arquivo_pdf.in_([ARQUIVO_TESTE_EMENDA, ARQUIVO_TESTE_RELATORIOS])))
            sessao.commit()


def test_jobs_de_emenda_do_robo_tambem_isolados():
    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_EMENDA))
        sessao.commit()

    try:
        registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_EMENDA,
            processo="0000000-00.2026.8.00.0802",
            relatorio_path="relatorio_teste_emenda_robo.docx",
            destino_pdf=None,
            confianca="alta",
            usuario_id=None,
            ferramenta_slug="emenda",
            tipo_relatorio="emenda",
        )

        nomes_emenda = {job.arquivo_pdf for job in listar_jobs_robo(ferramenta_slug="emenda")}
        nomes_relatorios = {job.arquivo_pdf for job in listar_jobs_robo(ferramenta_slug="extratus-relatorios")}

        assert ARQUIVO_TESTE_EMENDA in nomes_emenda
        assert ARQUIVO_TESTE_EMENDA not in nomes_relatorios
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_EMENDA))
            sessao.commit()


def test_campos_extra_de_emenda_sao_persistidos_no_job():
    """`registrar_processado(campos_extra=...)` — ver core/pipeline.py e
    db/jobs.py — precisa gravar as colunas emenda_* de verdade, não só
    aceitar o parâmetro sem efeito."""
    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_EMENDA))
        sessao.commit()

    try:
        job = registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_EMENDA,
            processo="0000000-00.2026.8.00.0803",
            relatorio_path="relatorio_teste_emenda_campos.docx",
            destino_pdf=None,
            confianca="alta",
            usuario_id=USUARIO_TESTE,
            ferramenta_slug="emenda",
            tipo_relatorio="emenda",
            campos_extra={
                "emenda_data_intimacao": "03/11/2026",
                "emenda_prazo_dias": 4,
                "emenda_dias_uteis": False,
                "emenda_prazo_calculado": "09/11/2026",
                "emenda_prazo_ja_expirado": False,
                "emenda_veiculo_terceiro": True,
            },
        )

        with obter_sessao() as sessao:
            atualizado = sessao.get(Job, job.id)
            assert atualizado.emenda_data_intimacao == "03/11/2026"
            assert atualizado.emenda_prazo_dias == 4
            assert atualizado.emenda_dias_uteis is False
            assert atualizado.emenda_prazo_calculado == "09/11/2026"
            assert atualizado.emenda_prazo_ja_expirado is False
            assert atualizado.emenda_veiculo_terceiro is True
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_EMENDA))
            sessao.commit()


def test_job_bancario_sem_campos_extra_fica_com_colunas_emenda_nulas():
    """Nenhuma linha "bancario" deve ganhar valor nenhum nas colunas
    novas — são exclusivas do tipo "emenda" (ver docstring de Job em
    nucleo_relatorios/db/models.py)."""
    with obter_sessao() as sessao:
        sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_RELATORIOS))
        sessao.commit()

    try:
        job = registrar_processado(
            arquivo_pdf=ARQUIVO_TESTE_RELATORIOS,
            processo="0000000-00.2026.8.00.0804",
            relatorio_path=None,
            destino_pdf=None,
            confianca="alta",
            usuario_id=USUARIO_TESTE,
            ferramenta_slug="extratus-relatorios",
        )

        with obter_sessao() as sessao:
            atualizado = sessao.get(Job, job.id)
            assert atualizado.emenda_data_intimacao is None
            assert atualizado.emenda_prazo_dias is None
            assert atualizado.emenda_prazo_calculado is None
    finally:
        with obter_sessao() as sessao:
            sessao.exec(delete(Job).where(Job.arquivo_pdf == ARQUIVO_TESTE_RELATORIOS))
            sessao.commit()
