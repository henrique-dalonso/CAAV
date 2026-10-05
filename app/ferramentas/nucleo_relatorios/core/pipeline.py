from pathlib import Path

from app.ferramentas.nucleo_relatorios.core.app_logger import registrar_log
from app.ferramentas.nucleo_relatorios.core.erros import separar_mensagem_e_detalhe
from app.ferramentas.nucleo_relatorios.core.pdf_isolado import executar_isolado
from app.ferramentas.nucleo_relatorios.core.processo_detector import analisar_pdf
from app.ferramentas.nucleo_relatorios.core.ia_cliente import gerar_relatorio_claude
from app.ferramentas.nucleo_relatorios.core.relatorio_manager import salvar_relatorio_docx
from app.ferramentas.nucleo_relatorios.core.output_manager import (
    gerar_caminho_unico,
    mover_para_erros,
    mover_por_confianca
)
from app.ferramentas.nucleo_relatorios.core.nomeador_relatorio import gerar_nome_relatorio
from app.ferramentas.nucleo_relatorios.db.jobs import registrar_processado, registrar_erro
from app.ferramentas.nucleo_relatorios.db.models import FERRAMENTA_SLUG_PADRAO


def obter_dados_deteccao(caminho_pdf):
    caminho_pdf = Path(caminho_pdf)

    # Processo separado, não só thread — pypdf é Python puro e nunca
    # libera o GIL (ver pdf_isolado.py).
    resultado = executar_isolado(analisar_pdf, caminho_pdf)

    dominante = resultado.get("dominante")
    confianca = resultado.get("confianca") or {
        "nivel": "revisao",
        "motivo": "Falha desconhecida ao avaliar a confiança da detecção.",
    }

    processo = dominante.get("processo") if dominante else caminho_pdf.stem

    return processo, confianca


def ajustar_confianca_pos_ia(confianca, uso_ia):
    """Processo grande demais pra uma chamada só (dividido em pedaços)
    e/ou que teve páginas removidas pela triagem de anexos de listagem de
    terceiros (ver ia_cliente.montar_diagnostico_com_triagem) — nos dois
    casos é um caminho mais novo e mais arriscado que o de chamada única
    normal, então nunca cai em "alta confiança" automática. Reaproveitada
    tanto por `processar_pdf` (fluxo síncrono/Robô) quanto por
    `core/pipeline_manual.py` (fluxo manual por gatilho), pra não haver
    dois lugares divergentes aplicando essa mesma regra."""
    # Resgate por transcrição (Henrique, diretoria, 2026-08-26) é caminho
    # ainda em validação — também nunca cai em "alta confiança" sozinho.
    motivo = montar_motivo_revisao_pos_ia(
        dividido=bool(uso_ia.get("dividido")),
        paginas_removidas=len(uso_ia.get("paginas_excluidas_triagem") or []),
        paginas_resgatadas=len(uso_ia.get("paginas_transcritas") or []),
    )

    if motivo:
        return {"nivel": "revisao", "motivo": motivo}

    return confianca


def montar_motivo_revisao_pos_ia(dividido, paginas_removidas, paginas_resgatadas):
    """Texto do "?" de revisão (Henrique, 2026-10-05). Usado também pelo
    Robô (robo_lote.py), pra os dois caminhos nunca divergirem. None quando
    nenhum dos caminhos arriscados foi usado."""
    medidas = []
    if paginas_removidas:
        medidas.append(
            "1 página removida automaticamente" if paginas_removidas == 1
            else f"{paginas_removidas} páginas removidas automaticamente"
        )
    if paginas_resgatadas:
        medidas.append(
            "1 página sem conteúdo seguro foi resgatada" if paginas_resgatadas == 1
            else f"{paginas_resgatadas} páginas sem conteúdo seguro foram resgatadas"
        )

    if not dividido and not medidas:
        return None

    frases = []
    if dividido:
        frases.append("O processo foi dividido em partes por ser grande demais para uma única análise.")
    if medidas:
        frases.append("Medidas de barateamento foram aplicadas: " + " e ".join(medidas) + ".")
    frases.append("Recomenda-se revisão manual.")

    return " ".join(frases)


def tratar_erro(
    pdf,
    processo,
    tipo_erro,
    erro,
    pasta_erros,
    usuario_id=None,
    solicitante_id=None,
    ferramenta_slug=FERRAMENTA_SLUG_PADRAO,
):
    """Registra uma falha de processamento (PDF, IA, docx ou movimentação)
    e move o PDF pra pasta de erros. Reaproveitada tanto pelo fluxo
    síncrono (`processar_pdf`) quanto pelo Robô (itens de um lote do
    Batch API que falharam, ou arquivos rejeitados antes mesmo de entrar
    num lote — ver `robo_lote.py`).

    `solicitante_id`: ver docstring de Job.solicitante_id — só usado pelo
    Robô (fluxo manual já usa `usuario_id`, que já É quem pediu)."""
    registrar_log(f"Erro ({tipo_erro}) ao processar {Path(pdf).name}: {erro}")

    mensagem, detalhe = separar_mensagem_e_detalhe(erro, tipo_erro)

    destino_pdf = None

    try:
        destino_pdf = mover_para_erros(pdf, pasta_erros)
        registrar_log(f"PDF movido para erros: {destino_pdf}")
    except Exception as erro_movimentacao:
        registrar_log(f"Erro ao mover PDF para erros: {erro_movimentacao}")

    registrar_erro(
        arquivo_pdf=Path(pdf).name,
        processo=processo,
        tipo_erro=tipo_erro,
        erro_mensagem=mensagem,
        erro_detalhe=detalhe,
        destino_pdf=destino_pdf,
        usuario_id=usuario_id,
        solicitante_id=solicitante_id,
        ferramenta_slug=ferramenta_slug,
    )

    return {
        "sucesso": False,
        "processo": processo,
        "tipo_erro": tipo_erro,
        "erro": mensagem,
    }


def finalizar_processamento(
    pdf,
    processo,
    confianca,
    dados_relatorio,
    uso_ia,
    pasta_saida,
    pasta_processados,
    pasta_revisao,
    pasta_erros,
    usuario_id=None,
    solicitante_id=None,
    tipo=None,
    ferramenta_slug=FERRAMENTA_SLUG_PADRAO,
):
    """Etapa final, depois que os dados do relatório já existem (vieram de
    uma chamada em tempo real ou de um resultado de lote coletado depois):
    gera o .docx, move o PDF conforme a confiança da detecção, e registra
    o Job. Reaproveitada por `processar_pdf` (fluxo síncrono) e pela
    coleta de resultados do Robô (`robo_lote.py`), pra não haver dois
    lugares divergentes fazendo a mesma coisa.

    `solicitante_id`: ver docstring de Job.solicitante_id — só usado pelo
    Robô. `tipo` (ver nucleo_relatorios/tipos.py) diz qual template .docx
    preencher — quando None, salvar_relatorio_docx cai no template
    "bancario" (único que existe hoje).

    `tipo.pos_processar`, quando definido (só "emenda" usa isso hoje —
    ver core/pos_processamento_emenda.py), roda ANTES do .docx ser
    preenchido: é aqui, e só aqui, que os 3 caminhos que convergem nesta
    função (fila manual, Robô, retomada pós-conferência) ganham a etapa
    determinística (não-IA) de cálculo de prazo fatal, sem precisar
    duplicar a chamada em cada um dos 3 lugares."""
    campos_extra_job = None

    if tipo is not None and tipo.pos_processar is not None:
        dados_relatorio, campos_extra_job = tipo.pos_processar(dados_relatorio)

    try:
        nome_relatorio = gerar_nome_relatorio(processo)
        caminho_saida_base = Path(pasta_saida) / nome_relatorio
        caminho_saida = gerar_caminho_unico(caminho_saida_base)

        template_docx_path = tipo.template_docx_path if tipo is not None else None
        salvar_relatorio_docx(dados_relatorio, caminho_saida, template_docx_path=template_docx_path)
    except Exception as erro:
        return tratar_erro(
            pdf, processo, "erro_docx", erro, pasta_erros, usuario_id, solicitante_id, ferramenta_slug=ferramenta_slug
        )

    try:
        destino_pdf = mover_por_confianca(
            pdf,
            confianca.get("nivel"),
            pasta_processados,
            pasta_revisao
        )
    except Exception as erro:
        return tratar_erro(
            pdf, processo, "erro_movimentacao", erro, pasta_erros, usuario_id, solicitante_id,
            ferramenta_slug=ferramenta_slug,
        )

    registrar_log(
        f"Relatório gerado (confiança {confianca.get('nivel')}): {caminho_saida}"
    )
    registrar_log(f"PDF movido para: {destino_pdf}")

    job = registrar_processado(
        arquivo_pdf=Path(pdf).name,
        processo=processo,
        relatorio_path=caminho_saida,
        destino_pdf=destino_pdf,
        confianca=confianca.get("nivel"),
        motivo_confianca=confianca.get("motivo"),
        uso_ia=uso_ia,
        usuario_id=usuario_id,
        solicitante_id=solicitante_id,
        ferramenta_slug=ferramenta_slug,
        tipo_relatorio=(tipo.chave if tipo is not None else None),
        campos_extra=campos_extra_job,
    )

    return {
        "sucesso": True,
        "status": job.status,
        "job_id": job.id,
        "processo": processo,
        "confianca": confianca.get("nivel"),
        "relatorio": str(caminho_saida),
        "pdf_destino": str(destino_pdf)
    }


def processar_pdf(
    pdf,
    pasta_saida,
    pasta_processados,
    pasta_erros,
    pasta_revisao,
    usuario_id=None,
    tipo=None,
    ferramenta_slug=FERRAMENTA_SLUG_PADRAO,
):
    """Processa um único PDF: detecta o processo, gera o relatório, move o
    arquivo conforme a confiança da detecção e registra o resultado.

    Usado tanto pelo modo linha de comando (app/main.py) quanto pela
    camada web (app/web) — a lógica de processar um PDF existe em um
    único lugar, para não haver dois caminhos que possam divergir.

    Confiança "alta" -> processados, status "sucesso".
    Qualquer outra confiança -> revisão humana, status "revisao"
    (o relatório ainda é gerado, só fica marcado pra conferência).
    Falhas de verdade (não conseguiu ler o PDF, gerar o relatório, etc.)
    -> pasta de erros, com o tipo de erro identificado por etapa.
    """
    try:
        processo, confianca = obter_dados_deteccao(pdf)
    except Exception as erro:
        return tratar_erro(pdf, None, "erro_pdf", erro, pasta_erros, usuario_id, ferramenta_slug=ferramenta_slug)

    try:
        dados_relatorio, uso_ia = gerar_relatorio_claude(pdf, processo, tipo=tipo)
    except Exception as erro:
        return tratar_erro(pdf, processo, "erro_ia", erro, pasta_erros, usuario_id, ferramenta_slug=ferramenta_slug)

    confianca = ajustar_confianca_pos_ia(confianca, uso_ia)

    return finalizar_processamento(
        pdf,
        processo,
        confianca,
        dados_relatorio,
        uso_ia,
        pasta_saida,
        pasta_processados,
        pasta_revisao,
        pasta_erros,
        usuario_id,
        tipo=tipo,
        ferramenta_slug=ferramenta_slug,
    )
