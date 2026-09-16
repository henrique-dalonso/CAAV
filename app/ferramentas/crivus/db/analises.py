from datetime import date, datetime, timedelta

from sqlmodel import or_, select

from app.ferramentas.crivus.db.models import (
    AnalisePublicacao,
    AnexoAnalise,
    ItemAcompanhamento,
    ItemAgendamento,
)
from app.plataforma.db.session import obter_sessao


def _preencher_analise_com_resultado_ia(sessao, analise, dados_ia, uso_ia):
    """Aplica os campos vindos da IA numa AnalisePublicacao JÁ PERSISTIDA
    (já tem id) e cria os itens de Acompanhamento/Agendamento — mesma
    lógica usada tanto pra criação imediata (Leitor Individual, via
    `criar_analise_a_partir_da_ia` abaixo) quanto pra conclusão de uma
    linha de lote que já existia antes, esperando (ver
    `concluir_analise_de_lote` em lotes_crivus.py). Henrique, 2026-09-14:
    extraído pra nunca duplicar como o JSON da IA vira linhas de banco.

    `analise.processo`, quando já vier preenchido (modo individual, a
    pessoa já viu na fila do NPJUR), tem prioridade sobre o que a
    própria IA tenta identificar lendo o teor — mais confiável que uma
    leitura automática. No modo lote, sempre vem None aqui, então o
    valor da IA prevalece."""
    analise.processo = analise.processo or (dados_ia.get("processo") or None)
    analise.carteira = dados_ia.get("carteira")
    analise.orgao_julgador = dados_ia.get("orgao_julgador") or None
    analise.carteira_detalhe = dados_ia.get("carteira_detalhe")
    analise.fase_processual = dados_ia.get("fase_processual")
    analise.posicao_parte = dados_ia.get("posicao_parte")
    analise.natureza_ato = dados_ia.get("natureza_ato")
    analise.quem_foi_intimado = dados_ia.get("quem_foi_intimado")
    analise.resumo_objetivo = dados_ia.get("resumo_objetivo")
    analise.comando_judicial = dados_ia.get("comando_judicial")
    analise.resultado_parte = dados_ia.get("resultado_parte")
    analise.resumo_ia = dados_ia.get("conclusao_operacional")
    analise.nivel_confianca = dados_ia.get("nivel_confianca")
    analise.tem_alerta_critico = bool(dados_ia.get("tem_alerta_critico"))
    analise.texto_alerta_critico = dados_ia.get("texto_alerta_critico")
    analise.status = "aguardando_revisao"
    analise.modelo_ia = uso_ia.get("modelo")
    analise.tokens_entrada = uso_ia.get("tokens_entrada")
    analise.tokens_saida = uso_ia.get("tokens_saida")
    analise.custo_estimado_usd = uso_ia.get("custo_estimado_usd")
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


def criar_analise_a_partir_da_ia(usuario_id, teor_publicacao, dados_ia, uso_ia, origem="individual",
                                  npjur=None, processo=None):
    """Persiste o resultado de `ia_cliente.analisar_publicacao` — cria a
    AnalisePublicacao e os itens de Acompanhamento/Agendamento, todos com
    `tipo_sugerido` == `tipo` (ainda não revisados, status "sugerido").

    `npjur`/`processo`, quando informados (modo individual, a pessoa já
    os vê na fila do NPJUR), têm prioridade sobre o que a própria IA
    tenta identificar lendo o teor — ver `_preencher_analise_com_resultado_ia`."""
    with obter_sessao() as sessao:
        analise = AnalisePublicacao(
            usuario_id=usuario_id,
            origem=origem,
            teor_publicacao=teor_publicacao,
            npjur=npjur,
            processo=processo,
        )
        sessao.add(analise)
        sessao.commit()
        sessao.refresh(analise)

        return _preencher_analise_com_resultado_ia(sessao, analise, dados_ia, uso_ia)


def obter_analise(analise_id):
    with obter_sessao() as sessao:
        return sessao.get(AnalisePublicacao, analise_id)


def _consulta_producao(origem, status, busca=None, data_de=None, data_ate=None, solicitante_id=None, nivel_confianca=None):
    """Filtros compartilhados por listar_analises/contar_analises — pra
    contagem/paginação sempre baterem com o mesmo recorte. Henrique,
    diretoria, 2026-09-15: "está faltando busca e filtros, igual o
    Extratus" — diferente da tela de Relatórios do Robô (carrega tudo e
    filtra no JS), Produção pagina de verdade no servidor (o acervo pode
    ter milhares de linhas vindas do Processamento em Lote), então o
    filtro também precisa ser no servidor — filtrar só o que já está
    carregado na página atual daria resultado incompleto/enganoso.

    `nivel_confianca` (Henrique, diretoria, 2026-09-16: "adicione um
    filtro, tipo o de usuário... para selecionar o grau de confiança")
    é um valor exato de um conjunto fechado (ALTO/MÉDIO/BAIXO, ver
    RÓTULO_CONFIANÇA_FEMININO em config/taxonomia.py) — igualdade
    simples, sem dropdown dinâmico igual solicitante_id (não precisa
    consultar quais níveis "de fato têm caso" — são só 3, sempre
    oferecidos)."""
    campo_data = AnalisePublicacao.concluido_em if status == "concluido" else AnalisePublicacao.criado_em

    consulta = select(AnalisePublicacao).where(
        AnalisePublicacao.origem == origem,
        AnalisePublicacao.status == status,
    )

    if busca:
        termo = f"%{busca.strip()}%"
        consulta = consulta.where(
            or_(AnalisePublicacao.npjur.ilike(termo), AnalisePublicacao.processo.ilike(termo))
        )
    if data_de:
        consulta = consulta.where(campo_data >= datetime.combine(data_de, datetime.min.time()))
    if data_ate:
        consulta = consulta.where(campo_data <= datetime.combine(data_ate, datetime.max.time()))
    if solicitante_id:
        consulta = consulta.where(AnalisePublicacao.usuario_id == solicitante_id)
    if nivel_confianca:
        consulta = consulta.where(AnalisePublicacao.nivel_confianca == nivel_confianca)

    return consulta


def listar_analises(origem, status, limite=50, offset=0, busca=None, data_de=None, data_ate=None, solicitante_id=None,
                     nivel_confianca=None):
    """Lista AnalisePublicacao pra tela Produção — sem checagem de dono,
    de propósito (Henrique, 2026-09-12: o acervo é do escritório inteiro,
    não do criador).

    Henrique, diretoria, 2026-09-15: as duas listas (Pendentes e
    Concluídos) agora vêm do mais novo pro mais antigo — "as novas devem
    aparecer por cima" (antes, Pendentes era do mais antigo pro mais
    novo, decisão de 2026-09-12 pra não deixar nada "apodrecer no
    fundo"; virou estressante depois que o Processamento em Lote passou
    a alimentar essa mesma fila com volume real)."""
    with obter_sessao() as sessao:
        consulta = _consulta_producao(origem, status, busca, data_de, data_ate, solicitante_id, nivel_confianca)

        campo_ordenacao = AnalisePublicacao.concluido_em if status == "concluido" else AnalisePublicacao.criado_em
        consulta = consulta.order_by(campo_ordenacao.desc())

        return sessao.exec(consulta.limit(limite).offset(offset)).all()


def contar_analises(origem, status, busca=None, data_de=None, data_ate=None, solicitante_id=None, nivel_confianca=None):
    with obter_sessao() as sessao:
        consulta = _consulta_producao(origem, status, busca, data_de, data_ate, solicitante_id, nivel_confianca)
        return len(sessao.exec(consulta.with_only_columns(AnalisePublicacao.id)).all())


def listar_solicitantes_ids(origem, status):
    """Henrique, diretoria, 2026-09-15: "mesmo comportamento do Extratus"
    — o dropdown "Solicitado por" só oferece quem de fato tem caso nesse
    recorte (aba+filtro atuais), não a base de usuários inteira (a
    maioria nunca mandou nada pra essa aba específica). Ignora
    busca/data/solicitante de propósito — a lista de opções não deve
    encolher só porque outro filtro já está aplicado."""
    with obter_sessao() as sessao:
        ids = sessao.exec(
            select(AnalisePublicacao.usuario_id)
            .where(AnalisePublicacao.origem == origem, AnalisePublicacao.status == status)
            .distinct()
        ).all()
        return set(ids)


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

    return item, analise


# Henrique, diretoria, 2026-09-15: teto de 15 dias corridos após a
# publicação — o maior prazo recursal do CPC, unificado pelo art. 1.003,
# §5º (apelação, agravo, REsp, RE etc., todos em 15 dias úteis; só
# Embargos de Declaração é menor, 5 dias). Usado como trava única e
# simples por enquanto — o Renato (sócio) confirmou que a IA não é
# confiável pra calcular SLA sozinha, então quem revisa TEM que digitar
# a data manualmente, e essa data nunca pode passar do prazo máximo
# legal. Ajuste futuro possível: um catálogo por tipo de agendamento em
# vez de um teto único (nem todo tipo tem prazo legal fixo — muitos
# dependem do prazo que o próprio juiz determinou no despacho, ver
# discussão com Henrique 2026-09-15).
LIMITE_DIAS_PRAZO_AGENDAMENTO = 15


def _data_publicacao_referencia(analise):
    """Base pra calcular o prazo máximo de agendamento. origem="lote" já
    traz a data real da publicação (`data_publicacao_original`); no
    Leitor Individual esse campo não existe (a pessoa cola o teor na
    hora que lê a publicação na fila do NPJUR) — `criado_em` serve de
    proxy razoável nesse caso, assumindo que o teor é colado no mesmo
    dia em que a publicação foi lida."""
    return analise.data_publicacao_original or analise.criado_em.date()


def data_maxima_agendamento(analise):
    """Versão pública de `_data_publicacao_referencia` + o teto de dias —
    usada pela tela (detalhe.html) pra desenhar `min`/`max` no seletor de
    data, além da trava de verdade em `_validar_prazo_agendamento`."""
    return _data_publicacao_referencia(analise) + timedelta(days=LIMITE_DIAS_PRAZO_AGENDAMENTO)


def _validar_prazo_agendamento(analise, nova_data_inicio, nova_data_fim):
    """Henrique, diretoria, 2026-09-15: a data de um agendamento nunca
    pode ficar no passado (óbvio), nem passar do prazo máximo legal
    (LIMITE_DIAS_PRAZO_AGENDAMENTO dias corridos após a publicação) —
    trava de verdade no servidor, não só no seletor de data da tela."""
    hoje = date.today()
    data_maxima = data_maxima_agendamento(analise)

    for rotulo, data_escolhida in (("início", nova_data_inicio), ("fim", nova_data_fim)):
        if data_escolhida is None:
            continue
        if data_escolhida < hoje:
            raise ValueError(f"A data de {rotulo} não pode ser anterior a hoje.")
        if data_escolhida > data_maxima:
            raise ValueError(
                f"A data de {rotulo} não pode passar de {data_maxima.strftime('%d/%m/%Y')} "
                f"({LIMITE_DIAS_PRAZO_AGENDAMENTO} dias após a publicação)."
            )


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
        item, analise = _obter_item_editavel(sessao, analise_id, tipo_item, item_id)

        if novo_tipo:
            item.tipo = novo_tipo
        if tipo_item == "agendamento":
            data_inicio_final = nova_data_inicio or item.data_inicio
            data_fim_final = nova_data_fim or item.data_fim
            _validar_prazo_agendamento(analise, data_inicio_final, data_fim_final)
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
        item, analise = _obter_item_editavel(sessao, analise_id, tipo_item, item_id)

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

        if tipo_item == "agendamento":
            data_inicio_final = nova_data_inicio or item.data_inicio
            data_fim_final = nova_data_fim or item.data_fim
            _validar_prazo_agendamento(analise, data_inicio_final, data_fim_final)

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
    """Henrique, 2026-09-06: Acompanhamento NUNCA pode virar
    "desnecessario" — sempre há exatamente 1 por análise; se estiver
    errado, corrige-se (edita o tipo), não se descarta. Reverter
    (desnecessario=False) continua liberado por segurança (caminho de
    conserto pra qualquer registro antigo que já tenha entrado nesse
    estado antes dessa regra existir)."""
    if tipo_item == "acompanhamento" and desnecessario:
        raise ValueError(
            "Acompanhamento não pode ser marcado como desnecessário — sempre há exatamente 1, corrija o tipo em vez de descartar."
        )

    with obter_sessao() as sessao:
        item, _analise = _obter_item_editavel(sessao, analise_id, tipo_item, item_id)

        item.status = "desnecessario" if desnecessario else "sugerido"
        sessao.add(item)
        sessao.commit()
        sessao.refresh(item)

        return item


def marcar_ciente_alerta_critico(analise_id):
    with obter_sessao() as sessao:
        analise = sessao.get(AnalisePublicacao, analise_id)
        if analise.status == "concluido":
            raise ValueError("Caso já concluído — não é mais possível alterar.")

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

        if analise.status == "concluido":
            raise ValueError("Caso já concluído.")

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
