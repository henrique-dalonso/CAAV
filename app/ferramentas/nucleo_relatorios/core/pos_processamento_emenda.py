"""Gancho de pós-processamento do tipo "emenda" (ver
nucleo_relatorios/tipos.py::TipoRelatorio.pos_processar), chamado por
`core/pipeline.py::finalizar_processamento` logo depois da IA responder —
funciona pros 3 caminhos que convergem ali (fila manual síncrona, Robô via
Batch API, retomada pós-conferência), então essa conta só precisa existir
neste único lugar.

Responsabilidade única: pegar os FATOS brutos que a IA extraiu (data da
intimação, quantidade de dias, se são úteis) e rodar o cálculo
determinístico de prazo fatal (calculadores/prazo_fatal.py) — nunca
delegado à IA, ver docstring daquele módulo. O resultado enriquece dois
lugares diferentes:
1. `dados` que vão pro template .docx (campos novos: data final calculada,
   já vencido, diverge do informado) — ver
   nucleo_relatorios/config/templates/emenda.docx.
2. Colunas próprias do Job (`Job.emenda_*`, ver db/models.py) — pra dar
   pra listar/filtrar relatório de emenda por prazo sem reabrir o .docx.
"""

from app.ferramentas.nucleo_relatorios.calculadores.prazo_fatal import calcular_prazo_fatal


FORMATO_DATA_EXIBICAO = "%d/%m/%Y"

# Campos que o schema (ia_cliente.FERRAMENTA_EMENDA) deixa OPCIONAIS, mas
# que o template (config/templates/emenda.docx) sempre referencia — um
# campo ausente vira `Undefined` do Jinja quando docxtpl renderiza, e
# iterar/testar um `Undefined` como lista quebra o render inteiro (achado
# escrevendo esta função: `checklist_verificacao`/`documentos_ja_nos_autos`
# não estão em `required` no schema de propósito, a IA pode não ter nada
# pra listar num caso simples). Normalizados aqui, sempre, ANTES do
# template rodar — nunca no template em si (Jinja tem `default()`, mas
# espalhar isso pelo .docx inteiro é mais frágil de manter que centralizar
# num único lugar em Python).
_CAMPOS_LISTA_COM_DEFAULT_VAZIO = ("checklist_verificacao", "documentos_ja_nos_autos")
_CAMPOS_TEXTO_COM_DEFAULT_VAZIO = (
    "npjur", "uf", "identificador_carteira", "processos_relacionados_detalhe",
)


def _formatar_ou_vazio(data_calculada):
    return data_calculada.strftime(FORMATO_DATA_EXIBICAO) if data_calculada else ""


def _normalizar_campos_opcionais(dados):
    dados = dict(dados)

    for campo in _CAMPOS_LISTA_COM_DEFAULT_VAZIO:
        if not isinstance(dados.get(campo), list):
            dados[campo] = []

    for campo in _CAMPOS_TEXTO_COM_DEFAULT_VAZIO:
        if not dados.get(campo):
            dados[campo] = ""

    dados["processos_relacionados_flag"] = bool(dados.get("processos_relacionados_flag"))

    return dados


def processar_emenda(dados):
    """`dados` é o dict devolvido por `ia_cliente.extrair_dados_e_uso`
    (chaves batendo com `FERRAMENTA_EMENDA`). Devolve
    `(dados_enriquecidos, campos_extra_job)` — ver docstring de
    `TipoRelatorio.pos_processar`.

    Se a IA não conseguiu localizar a data de intimação (campo vazio —
    "não localizado nos autos", regra do próprio prompt), o cálculo não
    roda: os campos de prazo do template ficam vazios/None e um aviso
    fica registrado no próprio `dados`, em vez de quebrar o processamento
    inteiro por causa de um dado que faltou no processo real (o mesmo
    princípio de "nunca invente, sinalize a ausência" que o prompt já
    pede pro texto da análise em si)."""
    dados = _normalizar_campos_opcionais(dados)

    data_intimacao = (dados.get("data_intimacao_confirmada") or "").strip()
    prazo_dias = dados.get("prazo_dias")
    prazo_dias_uteis = bool(dados.get("prazo_dias_uteis"))
    data_fatal_email_interno = (dados.get("data_fatal_email_interno") or "").strip() or None

    if not data_intimacao or not prazo_dias:
        dados["prazo_aviso_calculo"] = (
            "Não foi possível calcular o prazo fatal automaticamente: "
            "data de intimação confirmada e/ou quantidade de dias do "
            "prazo não foram localizados nos autos. Confirme manualmente."
        )
        dados["prazo_data_inicio_formatada"] = ""
        dados["prazo_data_final_calculada"] = ""
        dados["prazo_data_informada_formatada"] = ""
        dados["prazo_ja_vencido"] = False
        dados["prazo_diverge_do_informado"] = False

        campos_extra_job = {
            "emenda_data_intimacao": None,
            "emenda_prazo_dias": None,
            "emenda_dias_uteis": prazo_dias_uteis,
            "emenda_prazo_calculado": None,
            "emenda_prazo_ja_expirado": None,
            "emenda_veiculo_terceiro": bool(dados.get("veiculo_em_nome_terceiro")),
        }
        return dados, campos_extra_job

    resultado = calcular_prazo_fatal(
        data_intimacao,
        int(prazo_dias),
        prazo_dias_uteis,
        data_fatal_informada=data_fatal_email_interno,
    )

    dados["prazo_aviso_calculo"] = ""
    dados["prazo_data_inicio_formatada"] = _formatar_ou_vazio(resultado["data_inicio_contagem"])
    dados["prazo_data_final_calculada"] = _formatar_ou_vazio(resultado["data_final_calculada"])
    dados["prazo_ja_vencido"] = resultado["ja_vencido"]
    dados["prazo_diverge_do_informado"] = bool(resultado["diverge_do_informado"])
    dados["prazo_data_informada_formatada"] = _formatar_ou_vazio(resultado["data_fatal_informada"])

    campos_extra_job = {
        "emenda_data_intimacao": data_intimacao,
        "emenda_prazo_dias": int(prazo_dias),
        "emenda_dias_uteis": prazo_dias_uteis,
        "emenda_prazo_calculado": _formatar_ou_vazio(resultado["data_final_calculada"]),
        "emenda_prazo_ja_expirado": resultado["ja_vencido"],
        "emenda_veiculo_terceiro": bool(dados.get("veiculo_em_nome_terceiro")),
    }

    return dados, campos_extra_job
