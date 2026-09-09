"""Registro único das "telas" (screens) montadas em cima do motor
compartilhado (nucleo_relatorios) — hoje Extratus-Relatórios,
Extratus-Aburesi e Emenda, todas com Fila do Robô + Relatórios URGENTES +
Relatórios do Robô, diferindo só por `ferramenta_slug`/`tipo`/identidade
visual.

ANTES desta tarefa (Emenda, 2026-09-09), essas 3 telas precisavam ser
cadastradas manualmente em 5 lugares diferentes, cada um com seu próprio
dict copiado e colado por ferramenta:
  - app/plataforma/web/routes/admin_ferramentas.py::CONFIGURACOES_POR_CHAVE
  - app/plataforma/web/routes/admin_custos.py::CUSTOS_POR_CHAVE
  - app/plataforma/web/notificacoes.py::REGISTRO_NOTIFICACOES
  - app/plataforma/web/chaves_ferramentas.py::CHAVE_POR_SLUG
  - app/plataforma/nomes_paginas.py::NOMES_POR_PREFIXO
Cada ferramenta nova (Emenda sendo a 3ª) significava editar os 5 arquivos
à mão, sempre com risco de esquecer um. Este módulo é a fonte ÚNICA de
verdade — os 5 arquivos acima agora só fazem um loop sobre
`REGISTRO_TELAS` (ou usam direto), preservando exatamente o formato/
comportamento que cada um já tinha (inclusive o uso de `functools.partial`
pra amarrar `ferramenta_slug`, ver `ligado_a_ferramenta` abaixo).

Crivus NÃO entra aqui de propósito — é um motor genuinamente separado
(prompt/schema/pipeline próprios, nem usa `nucleo_relatorios`), não uma
tela a mais deste motor. Os 5 arquivos acima continuam com a entrada do
Crivus cadastrada à parte, do jeito que já estava.

NOTA ARQUITETURAL (achado ao desenhar isso, vale registrar): este módulo
mora dentro do motor compartilhado mas IMPORTA os pacotes de tela
(extratus, extratus_aburesi, emenda) — o inverso da direção de dependência
normal (tela depende do motor, não o contrário). Foi feito assim porque a
tarefa pediu explicitamente esse caminho (`nucleo_relatorios/telas.py`)
como o lugar único do registro, e mover pra dentro de `app/plataforma/`
exigiria decidir outro nome/local não pedido. Na prática isso é seguro
(nenhum dos 3 pacotes de tela importa `nucleo_relatorios.telas`, então não
há import circular), mas é uma inversão de dependência real que vale
revisar se o motor compartilhado um dia precisar ser usado sem nenhuma das
telas atuais."""

from dataclasses import dataclass
from functools import partial
from typing import Callable

from app.ferramentas.emenda.core import config_manager as _config_manager_emenda
from app.ferramentas.emenda.web.notificacoes import (
    listar_notificacoes as _listar_notificacoes_emenda,
    listar_notificacoes_pessoais as _listar_notificacoes_pessoais_emenda,
)
from app.ferramentas.emenda.web.rotulos import (
    rotulo_erro as _rotulo_erro_emenda,
    rotulo_status as _rotulo_status_emenda,
)
from app.ferramentas.extratus.core import config_manager as _config_manager_extratus
from app.ferramentas.extratus.web.notificacoes import (
    listar_notificacoes as _listar_notificacoes_extratus,
    listar_notificacoes_pessoais as _listar_notificacoes_pessoais_extratus,
)
from app.ferramentas.extratus.web.rotulos import (
    rotulo_erro as _rotulo_erro_extratus,
    rotulo_status as _rotulo_status_extratus,
)
from app.ferramentas.extratus_aburesi.core import config_manager as _config_manager_aburesi
from app.ferramentas.extratus_aburesi.web.notificacoes import (
    listar_notificacoes as _listar_notificacoes_aburesi,
    listar_notificacoes_pessoais as _listar_notificacoes_pessoais_aburesi,
)
from app.ferramentas.extratus_aburesi.web.rotulos import (
    rotulo_erro as _rotulo_erro_aburesi,
    rotulo_status as _rotulo_status_aburesi,
)
from app.ferramentas.nucleo_relatorios.core import prompt_manager as _prompt_manager
from app.ferramentas.nucleo_relatorios.tipos import REGISTRO_TIPOS, TipoRelatorio


@dataclass(frozen=True)
class TelaConfig:
    # Chave pública usada nas URLs /admin/custos/<chave_admin> e
    # /admin/ferramentas/<chave_admin> — igual a `Ferramenta.slug` pras 2
    # ferramentas mais novas (extratus-aburesi, emenda), mas DIVERGENTE
    # pra extratus-relatorios (slug travado em "extratus" por permissão/
    # favorito já gravado, ver docstring de chaves_ferramentas.py).
    chave_admin: str
    # `Ferramenta.slug` de verdade (tabela plataforma) — usado em
    # permissão (`usuario_tem_acesso`) e no próprio CHAVE_POR_SLUG.
    slug_plataforma: str
    # `ferramenta_slug` das tabelas do motor compartilhado (Job/
    # ChecagemFila/TriagemManual/LoteRobo/ItemLoteRobo) — ver
    # nucleo_relatorios/db/models.py::FERRAMENTA_SLUG_PADRAO. Coincide com
    # `slug_plataforma` hoje (1:1), mas são conceitos diferentes.
    ferramenta_slug: str
    nome_exibicao: str
    # Prefixo real de URL do módulo (onde as rotas de fato moram) —
    # diferente de `chave_admin` pra extratus-relatorios (rotas em
    # "/extratus", chave admin "extratus-relatorios").
    url_base: str
    tipo: TipoRelatorio
    config_manager: object
    listar_notificacoes: Callable
    listar_notificacoes_pessoais: Callable
    rotulo_status: Callable
    rotulo_erro: Callable


REGISTRO_TELAS: dict[str, TelaConfig] = {
    "extratus-relatorios": TelaConfig(
        chave_admin="extratus-relatorios",
        slug_plataforma="extratus",
        ferramenta_slug="extratus-relatorios",
        nome_exibicao="Extratus - Relatórios",
        url_base="/extratus",
        tipo=REGISTRO_TIPOS["bancario"],
        config_manager=_config_manager_extratus,
        listar_notificacoes=_listar_notificacoes_extratus,
        listar_notificacoes_pessoais=_listar_notificacoes_pessoais_extratus,
        rotulo_status=_rotulo_status_extratus,
        rotulo_erro=_rotulo_erro_extratus,
    ),
    "extratus-aburesi": TelaConfig(
        chave_admin="extratus-aburesi",
        slug_plataforma="extratus-aburesi",
        ferramenta_slug="extratus-aburesi",
        nome_exibicao="Extratus - Aburesi",
        url_base="/extratus-aburesi",
        tipo=REGISTRO_TIPOS["bancario"],
        config_manager=_config_manager_aburesi,
        listar_notificacoes=_listar_notificacoes_aburesi,
        listar_notificacoes_pessoais=_listar_notificacoes_pessoais_aburesi,
        rotulo_status=_rotulo_status_aburesi,
        rotulo_erro=_rotulo_erro_aburesi,
    ),
    "emenda": TelaConfig(
        chave_admin="emenda",
        slug_plataforma="emenda",
        ferramenta_slug="emenda",
        nome_exibicao="Extratus - Emendas",
        url_base="/emenda",
        tipo=REGISTRO_TIPOS["emenda"],
        config_manager=_config_manager_emenda,
        listar_notificacoes=_listar_notificacoes_emenda,
        listar_notificacoes_pessoais=_listar_notificacoes_pessoais_emenda,
        rotulo_status=_rotulo_status_emenda,
        rotulo_erro=_rotulo_erro_emenda,
    ),
}


def ligado_a_ferramenta(funcao, ferramenta_slug):
    """`functools.partial` amarrando `ferramenta_slug` — usado pra TODA
    tela, inclusive extratus-relatorios (que antes desta tarefa chamava
    essas funções SEM esse argumento, contando com o default do próprio
    módulo `nucleo_relatorios` = "extratus-relatorios" batendo por
    coincidência). Vira explícito pras 3 telas por igual agora — mesma
    regra que esta tarefa aplicou em código novo: nunca confiar num
    default silencioso pra acertar a ferramenta certa."""
    return partial(funcao, ferramenta_slug=ferramenta_slug)


def prompt_manager_da_tela(tela: TelaConfig):
    """`nucleo_relatorios.core.prompt_manager` é um módulo só (as funções
    aceitam `tipo=` opcional) — a tela de Configurações
    (admin_ferramentas.py) sempre chamava essas funções SEM passar `tipo`,
    o que funcionava por acaso enquanto só "bancario" existia (era o
    default). Com "emenda" existindo, isso precisa ficar explícito: esta
    função devolve um objeto com a MESMA interface do módulo
    (extensao_esperada_prompt/obter_metadados_prompt/listar_versoes_prompt/
    substituir_instrucoes_relatorio/ativar_versao_prompt), cada método já
    amarrado ao `tipo` certo — quem chama (admin_ferramentas.py) nem
    precisa saber que existe mais de um tipo."""

    class _PromptManagerAmarradoAoTipo:
        extensao_esperada_prompt = staticmethod(
            partial(_prompt_manager.extensao_esperada_prompt, tipo=tela.tipo)
        )
        obter_metadados_prompt = staticmethod(
            partial(_prompt_manager.obter_metadados_prompt, tipo=tela.tipo)
        )
        listar_versoes_prompt = staticmethod(
            partial(_prompt_manager.listar_versoes_prompt, tipo=tela.tipo)
        )
        substituir_instrucoes_relatorio = staticmethod(
            partial(_prompt_manager.substituir_instrucoes_relatorio, tipo=tela.tipo)
        )
        ativar_versao_prompt = staticmethod(
            partial(_prompt_manager.ativar_versao_prompt, tipo=tela.tipo)
        )

    return _PromptManagerAmarradoAoTipo()
