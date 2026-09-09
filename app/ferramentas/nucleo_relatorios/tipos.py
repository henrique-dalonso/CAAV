"""Registro de "tipos de relatório" que o motor compartilhado
(app/ferramentas/nucleo_relatorios/) sabe gerar — hoje só existe
"bancario" (o relatório processual que Extratus-Relatórios sempre gerou),
mas o motor foi desenhado pra caber novos tipos (EMENDA, CONDENAÇÃO) sem
duplicar pipeline/robô/checagem de novo, como Extratus-Aburesi teve que
fazer no passado.

`TipoRelatorio` é o único lugar que diz, pra um tipo: qual prompt usar,
qual template .docx preencher, e qual schema de "tool use" a IA precisa
seguir (tanto o do relatório inteiro quanto o usado só na etapa de
"pedaço", quando um processo é grande demais pra uma chamada só — ver
core/ia_cliente.py). Os dicts de schema em si continuam morando em
ia_cliente.py (são específicos de "bancario" hoje) — este módulo só os
referencia, pra não ter duas fontes de verdade divergentes se um tipo
novo precisar de ajuste fino no schema.

Import atrasado (dentro da função) pra evitar ciclo: ia_cliente.py, pra
usar REGISTRO_TIPOS como valor padrão quando `tipo` não é passado, importa
deste módulo — se este módulo importasse ia_cliente.py logo no topo, seria
um import circular.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.plataforma.paths import PROJECT_ROOT


CONFIG_DIR = PROJECT_ROOT / "app" / "ferramentas" / "nucleo_relatorios" / "config"


@dataclass(frozen=True)
class TipoRelatorio:
    chave: str
    nome_exibicao: str
    prompt_path: Path
    template_docx_path: Path
    # Schemas de "tool use" da IA (ver ia_cliente.FERRAMENTA_RELATORIO/
    # FERRAMENTA_PEDACO) — cada tipo pode ter seus próprios campos.
    schema_relatorio: dict
    schema_pedaco: dict
    # Gancho opcional (None pra "bancario", o caso original que nunca
    # precisou disso) chamado por `core/pipeline.py::finalizar_processamento`
    # logo depois da IA responder, ANTES de preencher o .docx e registrar
    # o Job — pensado pra tipo que precisa de uma etapa determinística
    # (não-IA) sobre os dados brutos antes de virarem relatório final.
    # "emenda" usa isso pra rodar `calculadores/prazo_fatal.py` (ver
    # nucleo_relatorios/core/pos_processamento_emenda.py) — a conta de
    # data nunca é feita pela IA, só os fatos brutos (data da intimação,
    # quantidade de dias) que ela extrai.
    #
    # Assinatura: `pos_processar(dados: dict) -> tuple[dict, dict]` —
    # devolve (dados_para_o_template, campos_extra_para_o_job). O primeiro
    # dict é usado no lugar do `dados` original pra preencher o .docx
    # (pode conter campos NOVOS, calculados, além dos que a IA devolveu);
    # o segundo vira colunas extras do Job (ver
    # db/models.py::Job.emenda_*), só faz sentido pro tipo que as
    # declarar — nunca None, mas pode ser um dict vazio.
    pos_processar: Optional[Callable[[dict], tuple]] = None


def _construir_registro():
    # Import atrasado (ver docstring do módulo) — ia_cliente.py importa
    # REGISTRO_TIPOS deste módulo como valor padrão, então este módulo não
    # pode importar ia_cliente.py no topo do arquivo.
    from app.ferramentas.nucleo_relatorios.core.ia_cliente import (
        FERRAMENTA_EMENDA,
        FERRAMENTA_PEDACO,
        FERRAMENTA_RELATORIO,
    )
    from app.ferramentas.nucleo_relatorios.core.pos_processamento_emenda import processar_emenda

    bancario = TipoRelatorio(
        chave="bancario",
        nome_exibicao="Relatório Bancário",
        prompt_path=CONFIG_DIR / "instrucoes_relatorio.txt",
        template_docx_path=CONFIG_DIR / "relatorio_template.docx",
        schema_relatorio=FERRAMENTA_RELATORIO,
        schema_pedaco=FERRAMENTA_PEDACO,
    )

    # EMENDA — 1º tipo novo no motor compartilhado além de "bancario"
    # (2026-09-09). Prompt/template moram numa subpasta própria por tipo
    # (config/prompts/, config/templates/), diferente do jeito "achatado"
    # de "bancario" (que já existia antes desse mecanismo de múltiplos
    # tipos e não vale a pena remexer só por consistência estética) — é
    # assim que o próximo tipo (CONDENAÇÃO) também vai morar, cada um no
    # seu arquivo dentro da mesma subpasta.
    #
    # `schema_pedaco` reaproveita FERRAMENTA_PEDACO (pensado originalmente
    # pra "bancario") — decisão consciente: uma emenda/despacho é sempre
    # um documento curto (a decisão do juízo + o processo em si), então
    # dividir em pedaços é um caminho de exceção rara aqui. Quando isso
    # acontecer, o pedaço só precisa extrair cronologia/documentos brutos
    # de cada trecho pro resumo de redução (ver
    # ia_cliente._formatar_resumo_para_reducao) — a chamada de redução
    # final continua usando FERRAMENTA_EMENDA de verdade, então nenhuma
    # informação específica de emenda se perde, só o "mapa" intermediário
    # é genérico. Ver relatório de entrega (2026-09-09) — se emenda um dia
    # tiver documentos tipicamente grandes, vale criar um schema de pedaço
    # dedicado.
    emenda = TipoRelatorio(
        chave="emenda",
        nome_exibicao="Análise de Emenda/Despacho",
        prompt_path=CONFIG_DIR / "prompts" / "emenda.txt",
        template_docx_path=CONFIG_DIR / "templates" / "emenda.docx",
        schema_relatorio=FERRAMENTA_EMENDA,
        schema_pedaco=FERRAMENTA_PEDACO,
        pos_processar=processar_emenda,
    )

    return {"bancario": bancario, "emenda": emenda}


REGISTRO_TIPOS: dict[str, TipoRelatorio] = _construir_registro()
