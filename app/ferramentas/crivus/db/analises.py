from datetime import date, datetime, timedelta

from sqlmodel import select

from app.ferramentas.crivus.db.models import (
    AnalisePublicacao,
    AnexoAnalise,
    ItemAcompanhamento,
    ItemAgendamento,
)
from app.plataforma.db.session import obter_sessao


def criar_analise_a_partir_da_ia(usuario_id, teor_publicacao, dados_ia, uso_ia, origem="individual",
                                  npjur=None, processo=None):
    """Persiste o resultado de `ia_cliente.analisar_publicacao` — cria a
    AnalisePublicacao e os itens de Acompanhamento/Agendamento, todos com
    `tipo_sugerido` == `tipo` (ainda não revisados, status "sugerido").

    `npjur`/`processo`, quando informados (modo individual, a pessoa já
    os vê na fila do NPJUR), têm prioridade sobre o que a própria IA
    tenta identificar lendo o teor — mais confiável que uma leitura
    automática. No modo lote (ainda não construído), viriam da planilha."""
    with obter_sessao() as sessao:
        analise = AnalisePublicacao(
            usuario_id=usuario_id,
            origem=origem,
            teor_publicacao=teor_publicacao,
            npjur=npjur,
            processo=processo or (dados_ia.get("processo") or None),
            carteira=dados_ia.get("carteira"),
            orgao_julgador=dados_ia.get("orgao_julgador") or None,
            carteira_detalhe=dados_ia.get("carteira_detalhe"),
            fase_processual=dados_ia.get("fase_processual"),
            posicao_parte=dados_ia.get("posicao_parte"),
            natureza_ato=dados_ia.get("natureza_ato"),
            quem_foi_intimado=dados_ia.get("quem_foi_intimado"),
            resumo_objetivo=dados_ia.get("resumo_objetivo"),
            comando_judicial=dados_ia.get("comando_judicial"),
            resultado_parte=dados_ia.get("resultado_parte"),
            resumo_ia=dados_ia.get("conclusao_operacional"),
            nivel_confianca=dados_ia.get("nivel_confianca"),
            tem_alerta_critico=bool(dados_ia.get("tem_alerta_critico")),
            texto_alerta_critico=dados_ia.get("texto_alerta_critico"),
            status="aguardando_revisao",
            modelo_ia=uso_ia.get("modelo"),
            tokens_entrada=uso_ia.get("tokens_entrada"),
            tokens_saida=uso_ia.get("tokens_saida"),
            custo_estimado_usd=uso_ia.get("custo_estimado_usd"),
        )
        sessao.add(analise)
        sessao.commit()
        sessao.refresh(analise)

        for item in dados_ia.get("acompanhamentos", []):
            sessao.add(ItemAcompanhamento(
                analise_id=analise.id,
                tipo_sugerido=item["tipo"],
                tipo=item["tipo"],
            ))

        hoje = date.today()
        for item in dados_ia.get("agendamentos", []):
            data_inicio = hoje + timedelta(days=item.get("dias_inicio", 0))
            data_fim = hoje + timedelta(days=item.get("dias_fim", 0))
            sessao.add(ItemAgendamento(
                analise_id=analise.id,
                tipo_sugerido=item["tipo"],
                tipo=item["tipo"],
                data_inicio_sugerida=data_inicio,
                data_fim_sugerida=data_fim,
                data_inicio=data_inicio,
                data_fim=data_fim,
            ))

        sessao.commit()
        sessao.refresh(analise)

        return analise


def obter_analise(analise_id):
    with obter_sessao() as sessao:
        return sessao.get(AnalisePublicacao, analise_id)


def listar_itens(analise_id):
    with obter_sessao() as sessao:
        acompanhamentos = sessao.exec(
            select(ItemAcompanhamento).where(ItemAcompanhamento.analise_id == analise_id)
        ).all()
        agendamentos = sessao.exec(
            select(ItemAgendamento).where(ItemAgendamento.analise_id == analise_id)
        ).all()
        return acompanhamentos, agendamentos


def _todos_prontos(analise_id, sessao):
    pendentes = sessao.exec(
        select(ItemAcompanhamento).where(
            ItemAcompanhamento.analise_id == analise_id,
            ItemAcompanhamento.status == "sugerido",
        )
    ).first()
    if pendentes:
        return False

    pendentes = sessao.exec(
        select(ItemAgendamento).where(
            ItemAgendamento.analise_id == analise_id,
            ItemAgendamento.status == "sugerido",
        )
    ).first()
    return pendentes is None


def _obter_item_editavel(sessao, analise_id, tipo_item, item_id):
    modelo = ItemAcompanhamento if tipo_item == "acompanhamento" else ItemAgendamento

    analise = sessao.get(AnalisePublicacao, analise_id)
    if analise and analise.status == "concluido":
        raise ValueError("Caso já concluído — não é mais possível corrigir itens.")

    item = sessao.get(modelo, item_id)
    if not item or item.analise_id != analise_id:
        raise ValueError("Item não encontrado nesta análise.")

    return item


def marcar_item_pronto(analise_id, tipo_item, item_id, novo_tipo=None, nova_data_inicio=None, nova_data_fim=None):
    """Botão "Pronto" (fora do modo edição) — aplica o que já estiver nos
    campos (sem alteração, se a pessoa nunca abriu o lápis) e confirma o
    item de vez. Nunca mexe em `tipo_sugerido`/`data_*_sugerida`, que
    preservam o que a IA disse originalmente pro double-check.

    Henrique, 2026-09-06: o <select> do tipo tem "required" no HTML (o
    interruptor "Pronto"/"Não Verificado" também barra antes de tentar
    ligar, ver crivus.js), mas um item recém-adicionado manualmente pode
    chegar aqui com tipo ainda vazio — trava de novo aqui embaixo, não dá
    pra confiar só na validação do navegador."""
    with obter_sessao() as sessao:
        item = _obter_item_editavel(sessao, analise_id, tipo_item, item_id)

        if novo_tipo:
            item.tipo = novo_tipo
        if tipo_item == "agendamento":
            if nova_data_inicio:
                item.data_inicio = nova_data_inicio
            if nova_data_fim:
                item.data_fim = nova_data_fim

        if not item.tipo:
            raise ValueError("Selecione um tipo antes de marcar como pronto.")

        item.status = "pronto"
        sessao.add(item)
        sessao.commit()
        sessao.refresh(item)

        return item


def salvar_edicao_item(analise_id, tipo_item, item_id, novo_tipo, nova_data_inicio=None, nova_data_fim=None):
    """Botão "Salvar Alterações" (dentro do modo edição, lápis já aberto)
    — Henrique, 2026-09-04: diferente de "Pronto", isso NÃO confirma o
    item. Aplica a correção e devolve pro estado "aguardando confirmação"
    (sempre "sugerido", mesmo que já estivesse "pronto" antes de reabrir
    o lápis) — a pessoa ainda precisa clicar "Pronto" depois de editar.

    Henrique, 2026-09-06: se a pessoa abrir o modo edição e clicar em
    salvar SEM mudar nada de fato, isso não pode desfazer um "Pronto" já
    dado — só conta como edição de verdade (e só então volta pra
    "sugerido") quando tipo ou datas realmente mudaram. Nem esse caso de
    "nada mudou" livra de exigir um tipo escolhido: "nada foi selecionado
    não pode ser salvo" vale sempre, mesmo num item recém-criado
    manualmente que nunca teve tipo nenhum."""
    with obter_sessao() as sessao:
        item = _obter_item_editavel(sessao, analise_id, tipo_item, item_id)

        if not novo_tipo:
            raise ValueError("Selecione um tipo antes de salvar.")

        mudou = item.tipo != novo_tipo
        if tipo_item == "agendamento":
            if nova_data_inicio and item.data_inicio != nova_data_inicio:
                mudou = True
            if nova_data_fim and item.data_fim != nova_data_fim:
                mudou = True

        if not mudou:
            return item

        item.tipo = novo_tipo
        if tipo_item == "agendamento":
            if nova_data_inicio:
                item.data_inicio = nova_data_inicio
            if nova_data_fim:
                item.data_fim = nova_data_fim

        item.status = "sugerido"
        sessao.add(item)
        sessao.commit()
        sessao.refresh(item)

        return item


def criar_agendamento_manual(analise_id):
    """Botão "+" abaixo da lista de Agendamentos — Henrique, 2026-09-04:
    acrescenta um agendamento que a IA não sugeriu. Nasce em branco (tipo
    vazio, datas de hoje) e a tela abre ele já em modo edição (ver
    detalhe.html: qualquer item sem tipo escolhido nasce aberto), pra
    pessoa preencher na hora.

    Henrique, 2026-09-06: tipo vazio (não mais NAO_IDENTIFICADO) de
    propósito — o dropdown mostra o placeholder neutro "(Selecione um
    tipo de agendamento)" já selecionado, em vez de vir com o item de
    escape-hatch da IA pré-marcado, que não faz sentido pra algo que a
    própria pessoa está criando do zero."""
    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, analise_id)
        if not analise:
            raise ValueError("Análise não encontrada.")
        if analise.status == "concluido":
            raise ValueError("Caso já concluído — não é mais possível adicionar agendamento.")

        hoje = date.today()
        item = ItemAgendamento(
            analise_id=analise_id,
            tipo_sugerido="",
            tipo="",
            data_inicio_sugerida=hoje,
            data_fim_sugerida=hoje,
            data_inicio=hoje,
            data_fim=hoje,
            criado_manualmente=True,
        )
        sessao.add(item)
        sessao.commit()
        sessao.refresh(item)

        return item


def excluir_agendamento_manual(analise_id, item_id):
    """Lata de lixo do agendamento adicionado manualmente — Henrique,
    2026-09-06: diferente de "marcar desnecessário" (que só esconde,
    preservando o registro pro double-check), aqui é exclusão de
    verdade. Só faz sentido pra item `criado_manualmente=True`: não tinha
    sugestão nenhuma da IA pra "preservar" caso a pessoa tenha adicionado
    por engano — apagar é o correto, não esconder."""
    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, analise_id)
        if not analise:
            raise ValueError("Análise não encontrada.")
        if analise.status == "concluido":
            raise ValueError("Caso já concluído — não é mais possível excluir agendamento.")

        item = sessao.get(ItemAgendamento, item_id)
        if not item or item.analise_id != analise_id:
            raise ValueError("Item não encontrado nesta análise.")
        if not item.criado_manualmente:
            raise ValueError("Só é possível excluir agendamentos adicionados manualmente.")

        sessao.delete(item)
        sessao.commit()


def marcar_item_desnecessario(analise_id, tipo_item, item_id, desnecessario=True):
    with obter_sessao() as sessao:
        item = _obter_item_editavel(sessao, analise_id, tipo_item, item_id)

        item.status = "desnecessario" if desnecessario else "sugerido"
        sessao.add(item)
        sessao.commit()
        sessao.refresh(item)

        return item


def marcar_ciente_alerta_critico(analise_id):
    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, analise_id)
        analise.ciente_alerta_critico = True
        sessao.add(analise)
        sessao.commit()
        sessao.refresh(analise)
        return analise


def concluir_analise(analise_id):
    """Só conclui se: todos os itens estiverem "pronto" (ou
    "desnecessario", que também conta como revisado) e, havendo alerta
    crítico, a ciência já tiver sido marcada — Henrique, 2026-09-03:
    trava obrigatória, sem exceção."""
    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, analise_id)

        if analise.tem_alerta_critico and not analise.ciente_alerta_critico:
            raise ValueError("Confirme a ciência do alerta crítico antes de concluir o caso.")

        if not _todos_prontos(analise_id, sessao):
            raise ValueError("Ainda há itens de acompanhamento/agendamento não revisados.")

        analise.status = "concluido"
        analise.concluido_em = datetime.now()
        sessao.add(analise)
        sessao.commit()
        sessao.refresh(analise)

        return analise


def descartar_alteracoes(analise_id):
    """Botão "Descartar alterações e Voltar" — Henrique, 2026-09-06
    perguntou se isso REALMENTE desfaz o que já foi confirmado (não
    basta só voltar pra lista, já que "Pronto"/"Salvar Alterações" já
    gravam no banco na hora, não existe rascunho separado). Aqui devolve
    cada item ao que a IA sugeriu originalmente (tipo/datas voltam de
    tipo_sugerido/data_*_sugerida, status volta a "sugerido"), remove os
    agendamentos adicionados manualmente (não têm sugestão da IA pra
    voltar) e desfaz a ciência do alerta crítico."""
    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, analise_id)
        if not analise:
            raise ValueError("Análise não encontrada.")
        if analise.status == "concluido":
            raise ValueError("Caso já concluído: não é mais possível descartar alterações.")

        acompanhamentos = sessao.exec(
            select(ItemAcompanhamento).where(ItemAcompanhamento.analise_id == analise_id)
        ).all()
        for item in acompanhamentos:
            item.tipo = item.tipo_sugerido
            item.status = "sugerido"
            sessao.add(item)

        agendamentos = sessao.exec(
            select(ItemAgendamento).where(ItemAgendamento.analise_id == analise_id)
        ).all()
        for item in agendamentos:
            if item.criado_manualmente:
                sessao.delete(item)
                continue
            item.tipo = item.tipo_sugerido
            item.data_inicio = item.data_inicio_sugerida
            item.data_fim = item.data_fim_sugerida
            item.status = "sugerido"
            sessao.add(item)

        analise.ciente_alerta_critico = False
        sessao.add(analise)
        sessao.commit()


def adicionar_anexo(analise_id, usuario_id, nome_arquivo, caminho, tipo_mime, tamanho_bytes):
    with obter_sessao() as sessao:
        anexo = AnexoAnalise(
            analise_id=analise_id,
            usuario_id=usuario_id,
            nome_arquivo=nome_arquivo,
            caminho=str(caminho),
            tipo_mime=tipo_mime,
            tamanho_bytes=tamanho_bytes,
        )
        sessao.add(anexo)
        sessao.commit()
        sessao.refresh(anexo)
        return anexo
