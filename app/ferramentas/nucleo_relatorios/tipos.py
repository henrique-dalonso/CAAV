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


def _construir_registro():
    # Import atrasado (ver docstring do módulo) — ia_cliente.py importa
    # REGISTRO_TIPOS deste módulo como valor padrão, então este módulo não
    # pode importar ia_cliente.py no topo do arquivo.
    from app.ferramentas.nucleo_relatorios.core.ia_cliente import (
        FERRAMENTA_PEDACO,
        FERRAMENTA_RELATORIO,
    )

    bancario = TipoRelatorio(
        chave="bancario",
        nome_exibicao="Relatório Bancário",
        prompt_path=CONFIG_DIR / "instrucoes_relatorio.txt",
        template_docx_path=CONFIG_DIR / "relatorio_template.docx",
        schema_relatorio=FERRAMENTA_RELATORIO,
        schema_pedaco=FERRAMENTA_PEDACO,
    )

    return {"bancario": bancario}


REGISTRO_TIPOS: dict[str, TipoRelatorio] = _construir_registro()
