# Lista fechada de tipos de ACOMPANHAMENTO e AGENDAMENTO usada pela IA e
# pela tela de correção do Leitor de Publicação — curada a partir dos 2
# manuais em `app/ferramentas/crivus/config/` (Prompt PUBLICAÇÕES.docx +
# COMPLEMENTAR - MANUAL.docx), extraídos célula a célula das tabelas do
# docx (python-docx), não digitados de memória.
#
# IMPORTANTE — validar com o time antes de tratar como definitivo: várias
# células do manual misturam o NOME do tipo com a REGRA condicional (ex:
# "OBF, se houver. Se decisão monocrática: DISPENSA...") — essa curadoria
# tentou separar um do outro, mas foi feita por leitura de IA, não por
# quem conhece a operação. Não existe lista oficial exportada do NPJUR
# pra conferir contra (Henrique, 2026-09-03) — por isso a tela de
# correção sempre deve aceitar um item "NÃO IDENTIFICADO / outro"
# (ver core, ainda a construir) em vez de forçar só essas opções.

TIPOS_ACOMPANHAMENTO = [
    "ACÓRDÃO - AGRAVO DE INSTRUMENTO NÃO CONHECIDO",
    "ACÓRDÃO - RESP/REXT NÃO CONHECIDO",
    "ACÓRDÃO APELAÇÃO IMPROVIDA",
    "ACÓRDÃO APELAÇÃO PROVIDA",
    "ACÓRDÃO RECURSO DE APELAÇÃO DA PARTE CONTRÁRIA IMPROVIDO",
    "ACÓRDÃO RECURSO DE APELAÇÃO DA PARTE CONTRÁRIA PROVIDO/PARCIALMENTE PROVIDO",
    "ACÓRDÃO RECURSO DE APELAÇÃO PARCIALMENTE PROVIDA",
    "ACÓRDÃO – AGRAVO DE INSTRUMENTO NÃO CONHECIDO/IMPROVIDO",
    "ACÓRDÃO – AGRAVO DE INSTRUMENTO PARCIALMENTE PROVIDO",
    "ACÓRDÃO – RECURSO IMPROVIDO",
    "ACÓRDÃO – RECURSO PROVIDO/PARCIALMENTE PROVIDO",
    "AGRAVO EM RECURSO ESPECIAL/PARTE CONTRÁRIA",
    "AGUARDANDO AUDIÊNCIA DE CONCILIAÇÃO",
    "ALVARÁ LEVANTAMENTO DEFERIDO",
    "BLOQUEIO DO VEÍCULO DEFERIDO",
    "CARTA PRECATÓRIA - EXPEDIDA",
    "CERTIDÃO NEGATIVA 1",
    "CERTIDÃO NEGATIVA 2",
    "CERTIDÃO NEGATIVA 3",
    "CERTIDÃO NEGATIVA >3",
    "CITAÇÃO EM CASO DE VEÍCULO APREENDIDO",
    "CITAÇÃO NEGATIVA",
    "CITAÇÃO PESSOAL E POR HORA CERTA FRUSTRADA",
    "CITAÇÃO POSITIVA",
    "CONTESTAÇÃO",
    "CONTESTAÇÃO COM RECONVENÇÃO",
    "CONVERSÃO EM AÇÃO DE EXECUÇÃO – DEFERIDA",
    "CUMPRIMENTO DE SENTENÇA BANCO EXECUTADO",
    "CUMPRIMENTO DE SENTENÇA BANCO EXEQUENTE",
    "CUSTAS FINAIS PAGAS",
    "DECISÃO QUE NEGA SEGUIMENTO AO RESP/REXT",
    "DECLÍNIO DE COMPETÊNCIA",
    "DESBLOQUEIO EFETIVADO",
    "DESPACHO",
    "DETERMINAÇÃO JUDICIAL PARA RESTITUIÇÃO DO BEM",
    "EDITAL DE CITAÇÃO",
    "EFEITO SUSPENSIVO CONCEDIDO NO AGRAVO DE INSTRUMENTO",
    "EFEITO SUSPENSIVO NEGADO NO AGRAVO – DECISÃO MONOCRÁTICA",
    "EMBARGOS DE DECLARAÇÃO DA PARTE CONTRÁRIA",
    "EMBARGOS DE DECLARAÇÃO DESACOLHIDOS",
    "EMBARGOS DE DECLARAÇÃO ACOLHIDOS",
    "EMBARGOS DE TERCEIRO",
    "EMBARGOS À EXECUÇÃO",
    "EMENDA A INICIAL - DESPACHO",
    "EXCEÇÃO DE COMPETÊNCIA",
    "EXCEÇÃO DE PRÉ-EXECUTIVIDADE",
    "EXTINÇÃO DO REQUERIMENTO DE APREENSÃO",
    "INTIMAÇÃO PARA PAGAMENTO DE CUSTAS",
    "LIMINAR DEFERIDA",
    "LIMINAR DEFERIDA COM IMPEDIMENTO REMOÇÃO/VENDA DO BEM",
    "LIMINAR INDEFERIDA",
    "MANDADO COM OFICIAL – DILIGÊNCIA",
    "OFÍCIO DEFERIDO",
    "OFÍCIO INDEFERIDO",
    "PENHORA ON-LINE DEFERIDA",
    "PROCESSO SUSPENSO",
    "PROIBIÇÃO JUDICIAL DE RETIRADA DO VEÍCULO DA COMARCA",
    "PUBLICAÇÃO",
    "PURGA DA MORA",
    "RECURSO DE APELAÇÃO/PARTE CONTRÁRIA",
    "RECURSO ESPECIAL/PARTE CONTRÁRIA",
    "RESULTADO DE OFÍCIO",
    "REVOGADA LIMINAR NA AÇÃO CONTRA",
    "SENTENÇA HOMOLOGATÓRIA",
    "SENTENÇA IMPROCEDENTE",
    "SENTENÇA PROCEDENTE",
    "SENTENÇA – EXTINÇÃO SEM RESOLUÇÃO DO MÉRITO",
    "SENTENÇA – EXTINÇÃO COM RESOLUÇÃO DO MÉRITO",
    "TRÂNSITO EM JULGADO",
]

TIPOS_AGENDAMENTO = [
    "AGRAVO DE INSTRUMENTO",
    "AGRAVO DE INSTRUMENTO – CONTRAMINUTA",
    "AGRAVO EM RESP/REXT - CONTRA-MINUTA",
    "AGRAVO INTERNO",
    "ANÁLISE DE GUIA – EPC",
    "ANÁLISE DE GUIA – RECURSO EPC",
    "ANÁLISE DE VIABILIDADE – OPOSIÇÃO AO JULGAMENTO VIRTUAL",
    "APELAÇÃO",
    "AREsp",
    "AUDIÊNCIA DE CONCILIAÇÃO",
    "CARTEIRA – DESISTÊNCIA DA AÇÃO",
    "CUMPRIMENTO DE OBRIGAÇÃO DE FAZER",
    "CUMPRIMENTO DE SENTENÇA",
    "DISPENSA DE RECURSO",
    "DISPENSA DE RECURSO - RESP",
    "DISTRIBUIR PRECATÓRIA",
    "EMBARGOS DE DECLARAÇÃO",
    "EMBARGOS DE DECLARAÇÃO – MANIFESTAÇÃO",
    "EMBARGOS DE TERCEIROS - IMPUGNAÇÃO",
    "EMENDA À INICIAL",
    "IMPUGNAÇÃO A EXCEÇÃO DE PRÉ-EXECUTIVIDADE",
    "IMPUGNAÇÃO A PURGA DA MORA",
    "IMPUGNAÇÃO AO CUMPRIMENTO DE SENTENÇA",
    "IMPUGNAÇÃO AOS EMBARGOS",
    "MANIFESTAR 5 DIAS SOB PENA DE EXTINÇÃO",
    "MANIFESTAR CERTIDÃO NEGATIVA DO OFICIAL DE JUSTIÇA",
    "MANIFESTAÇÃO",
    "MANIFESTAÇÃO EM CUMPRIMENTO DE SENTENÇA",
    "MANIFESTAÇÃO NA PRECATÓRIA",
    "MANIFESTAÇÃO NO RECURSO",
    "MANIFESTAÇÃO PERICIAL",
    "MANIFESTAÇÃO – REQUERER CITAÇÃO DO RÉU",
    "MANIFESTAÇÃO-PRODUÇÃO DE PROVAS/JULGAMENTO ANTECIPADO",
    "MEMORIAIS",
    "PAGAMENTO DE CONDENAÇÃO",
    "PRAZO PARA LEVANTAMENTO JUDICIAL",
    "RECURSO DE APELAÇÃO",
    "RECURSO DE APELAÇÃO – CONTRARRAZÕES",
    "RECURSO ESPECIAL",
    "RECURSO ESPECIAL – CONTRARRAZÕES",
    "REPORTE CONTESTAÇÃO",
    "REPORTE DE RECURSO",
    "REPORTE – ACÓRDÃO",
    "REPORTE – ACÓRDÃO RESP",
    "REPORTE – SENTENÇA",
    "RÉPLICA",
    "VERIFICAR EXPEDIÇÃO DO MANDADO",
]

# Valor especial reservado — não é bem um "tipo" de providência, é a
# ausência dela (ex: liminar deferida sem impedimento não gera
# agendamento nenhum). Fica fora de TIPOS_AGENDAMENTO de propósito, pra
# não aparecer misturado na lista de opções reais.
SEM_AGENDAMENTO = "SEM AGENDAMENTO"

# Escape hatch obrigatório — mesma regra "NÃO INVENTAR" do prompt mestre:
# quando a IA (ou a pessoa corrigindo) não encontra correspondência real
# nas listas acima, sinaliza em vez de forçar um tipo errado.
NAO_IDENTIFICADO = "NÃO IDENTIFICADO — validar nomenclatura no NPJUR"

# SLA interno (Manual, seção 8) — "primeira data" / "segunda data" =
# quantos dias corridos após a leitura somar pra calcular a DATA INÍCIO e
# a DATA FIM que o NPJUR exige por agendamento. É controle interno, não o
# prazo judicial/legal real (esse a IA identifica à parte, na leitura).
# dias_inicio/dias_fim: None quando o manual não dá um número fixo (ex:
# D+1 já é tratado à parte, "salvo regra especial" fica pra IA decidir
# com o contexto do caso).
SLA_AGENDAMENTO = {
    "DISPENSA DE RECURSO": {"dias_inicio": 2, "dias_fim": 2},
    "EMBARGOS DE DECLARAÇÃO": {"dias_inicio": 2, "dias_fim": 4},
    "RÉPLICA": {"dias_inicio": 5, "dias_fim": 14},
    "RÉPLICA – ITAÚ": {"dias_inicio": 5, "dias_fim": 10},
    # Agravo, apelação, agravo interno, RESP, AREsp — regra geral, "salvo
    # regra especial" (a IA pode ajustar com o contexto do caso concreto).
    "RECURSOS (GERAL)": {"dias_inicio": 7, "dias_fim": 14},
    "AGRAVO DE INSTRUMENTO POR EMENDA DE COMPROVAÇÃO DA MORA – ITAÚ": {"dias_inicio": 5, "dias_fim": 10},
    "EMENDA À INICIAL": {"dias_inicio": 5, "dias_fim": 10},
    "ANÁLISE DE GUIA – EPC": {"dias_inicio": 1, "dias_fim": 1},
    "ANÁLISE DE GUIA – RECURSO EPC": {"dias_inicio": 1, "dias_fim": 1},
    "DISPENSA DE RECURSO - RESP": {"dias_inicio": 1, "dias_fim": 1},
}
