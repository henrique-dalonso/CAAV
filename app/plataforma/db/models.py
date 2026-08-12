from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


CARGO_COORDENADOR = "coordenador"
CARGO_COLABORADOR = "colaborador"
CARGOS_VALIDOS = (CARGO_COORDENADOR, CARGO_COLABORADOR)

TEMA_SISTEMA = "sistema"
TEMA_CLARO = "claro"
TEMA_ESCURO = "escuro"
TEMAS_VALIDOS = (TEMA_SISTEMA, TEMA_CLARO, TEMA_ESCURO)

# Paleta fechada pra cor do avatar (aba Preferências) — nunca aceita cor
# livre do usuário (a escolha vira `background` inline no HTML; uma lista
# fechada evita qualquer possibilidade de injeção via esse campo).
CORES_PERFIL_VALIDAS = (
    "#4f46e5",  # índigo (cor padrão do site)
    "#2563eb",  # azul
    "#0ea5e9",  # céu
    "#0d9488",  # verde-azulado
    "#16a34a",  # verde
    "#d97706",  # âmbar
    "#ea580c",  # laranja
    "#e11d48",  # rosa-vermelho
    "#7c3aed",  # roxo
    "#475569",  # grafite
)
COR_PERFIL_PADRAO = CORES_PERFIL_VALIDAS[0]


class Usuario(SQLModel, table=True):
    """Um colaborador com acesso ao Centro de Experiência do Colaborador.

    eh_admin dá acesso automático a todas as ferramentas e à área
    administrativa (custos, criação de usuário, etc.) — nível supremo,
    reservado pra dev/diretoria. Não tem relação com "cargo" abaixo.

    cargo é a hierarquia normal do escritório, só relevante quando
    eh_admin é False:
    - "coordenador": todas as ferramentas liberadas por padrão (ainda
      ajustável por ferramenta), mas SEM acesso a custo — isso é só de
      admin. Mais permissões de coordenador vêm depois.
    - "colaborador": sem nenhuma ferramenta liberada por padrão, precisa
      que um coordenador (ou admin) libere.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    nome: str
    nome_usuario: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    senha_hash: str

    eh_admin: bool = False
    cargo: str = Field(default=CARGO_COLABORADOR)
    ativo: bool = True

    # Trava por usuário (Henrique, 2026-08-11): 3 senhas erradas SEGUIDAS
    # (qualquer acerto no meio zera o contador, ver resetar_tentativas_falhas)
    # bloqueia a conta até um admin desbloquear na tela de Usuários — mesmo
    # que a pessoa lembre a senha certa depois, login continua recusado
    # enquanto bloqueado for True. Ver também TentativaLoginFalha, a trava
    # complementar por IP/rede.
    tentativas_login_falhas: int = Field(default=0)
    bloqueado: bool = Field(default=False)
    bloqueado_em: Optional[datetime] = Field(default=None)

    # "sistema" segue o tema do sistema operacional (padrão); "claro"/
    # "escuro" força a escolha independente do sistema. Por usuário, não
    # por navegador — segue a pessoa entre computadores do escritório.
    tema: str = Field(default=TEMA_SISTEMA)

    # Cor do avatar (bolinha com a inicial do nome) — escolha pessoal,
    # não depende mais da cor de destaque da ferramenta aberta.
    cor_perfil: str = Field(default=COR_PERFIL_PADRAO)

    criado_em: datetime = Field(default_factory=datetime.now)


class Ferramenta(SQLModel, table=True):
    """Uma ferramenta disponível no Centro de Experiência (ex: Extratus).

    suporta_fila_motor diz se essa ferramenta TEM o conceito de "fila do
    motor" pra começo de conversa (ex: os módulos do Extratus têm; Leitor
    de Publicações, por enquanto, não) — controla se a opção "Fila do
    motor" aparece pra conceder no painel de usuários. Não confundir com
    `UsuarioFerramenta.fila_motor` (se UM usuário específico tem esse
    acesso) — este campo aqui é sobre a ferramenta em si oferecer ou não
    essa possibilidade. `admin_ferramenta` não precisa do equivalente:
    faz sentido em qualquer ferramenta.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    nome: str
    slug: str = Field(unique=True, index=True)
    descricao: Optional[str] = None
    url: str
    suporta_fila_motor: bool = Field(default=False)

    # Identidade visual da ferramenta (bolinha na bandeja de apps/home,
    # tarja acima do título, botões/abas dentro dela) — None em qualquer
    # um deles cai no azul padrão da plataforma (ver base.css). Guarda
    # claro e escuro separados (em vez de calcular um a partir do outro)
    # porque a paleta escura da Aburesi não é só "a clara mais clara", é
    # uma escolha visual própria — copiado 1:1 do que já existia fixado
    # em CSS antes disso virar campo de banco.
    cor_acento: Optional[str] = None
    cor_acento_hover: Optional[str] = None
    cor_acento_fraco: Optional[str] = None
    cor_acento_escuro: Optional[str] = None
    cor_acento_hover_escuro: Optional[str] = None
    cor_acento_fraco_escuro: Optional[str] = None


class UsuarioFerramenta(SQLModel, table=True):
    """Liga um usuário a uma ferramenta que ele tem permissão de usar.

    admin_ferramenta é um nível extra, só relevante pra coordenador (admin
    já vê tudo por causa de eh_admin, colaborador não deveria ter isso
    marcado) — dá acesso às abas administrativas DENTRO daquela ferramenta
    específica (ex: Custos e Motor no Extratus), sem dar acesso à área de
    Administração da plataforma inteira.

    fila_motor é outro nível extra, independente de admin_ferramenta —
    diferente dele, faz sentido pra colaborador também (ex: um estagiário
    responsável só por alimentar a fila do motor). Dá acesso à aba de fila
    (upload em lote pra pasta universal do motor), sem dar acesso a
    ligar/desligar o motor nem às configurações dele.
    """

    usuario_id: Optional[int] = Field(
        default=None, foreign_key="usuario.id", primary_key=True
    )
    ferramenta_id: Optional[int] = Field(
        default=None, foreign_key="ferramenta.id", primary_key=True
    )
    admin_ferramenta: bool = Field(default=False)
    fila_motor: bool = Field(default=False)


class AcessoFerramenta(SQLModel, table=True):
    """Contador de uso — quantas vezes cada usuário abriu a página
    principal de cada ferramenta. Alimenta o bloco "Mais utilizadas" da
    home; puramente informativo, não afeta permissão nenhuma."""

    usuario_id: Optional[int] = Field(
        default=None, foreign_key="usuario.id", primary_key=True
    )
    ferramenta_id: Optional[int] = Field(
        default=None, foreign_key="ferramenta.id", primary_key=True
    )
    contagem: int = Field(default=0)
    ultimo_acesso: datetime = Field(default_factory=datetime.now)


class TentativaLoginFalha(SQLModel, table=True):
    """Trava por IP/rede (Henrique, 2026-08-11): guarda cada tentativa de
    login que falhou (senha errada, ou nome de usuário que nem existe).
    5 nomes de usuário DIFERENTES tentados pelo mesmo IP em 15 minutos
    indica alguém varrendo contas, não um colega errando a própria
    senha — isso já é pego pela trava por usuário (Usuario.bloqueado)
    sem precisar desta tabela. Só interessam os últimos 15 minutos: cada
    nova tentativa poda as linhas mais velhas (ver registrar_tentativa_
    falha em db/tentativas_login.py), então a tabela nunca cresce sem
    limite."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ip: str = Field(index=True)
    nome_usuario_tentado: str
    criado_em: datetime = Field(default_factory=datetime.now)
