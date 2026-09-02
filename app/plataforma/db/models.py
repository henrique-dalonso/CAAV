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

# Nome em português de cada cor acima — as 8 opções são visualmente
# idênticas (só muda a cor de fundo), então sem um nome nenhum leitor de
# tela consegue diferenciá-las (achado de acessibilidade, Rodada 12).
NOMES_CORES_PERFIL = {
    "#4f46e5": "índigo",
    "#2563eb": "azul",
    "#0ea5e9": "céu",
    "#0d9488": "verde-azulado",
    "#16a34a": "verde",
    "#d97706": "âmbar",
    "#ea580c": "laranja",
    "#e11d48": "rosa-vermelho",
    "#7c3aed": "roxo",
    "#475569": "grafite",
}


class Usuario(SQLModel, table=True):
    """Um colaborador com acesso ao CAAV (Célula Avançada Alonso & Verdiani).

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

    # "sistema" segue o tema do sistema operacional; "claro"/"escuro"
    # força a escolha independente do sistema. Por usuário, não por
    # navegador — segue a pessoa entre computadores do escritório.
    # Henrique, 2026-09-02: padrão passou de "sistema" pra "escuro" — o
    # modo claro ainda não está bem feito, então ninguém deveria cair
    # nele sem querer só por causa do SO/navegador da máquina; "sistema"
    # continua disponível pra quem escolher de propósito.
    tema: str = Field(default=TEMA_ESCURO)

    # Cor do avatar (bolinha com a inicial do nome) — escolha pessoal,
    # não depende mais da cor de destaque da ferramenta aberta.
    cor_perfil: str = Field(default=COR_PERFIL_PADRAO)

    criado_em: datetime = Field(default_factory=datetime.now)


class Ferramenta(SQLModel, table=True):
    """Uma ferramenta disponível no CAAV (ex: Extratus).

    suporta_fila_robo diz se essa ferramenta TEM o conceito de "fila do
    robô" pra começo de conversa (ex: os módulos do Extratus têm; Leitor
    de Publicações, por enquanto, não) — controla se a opção "Fila do
    robô" aparece pra conceder no painel de usuários. Não confundir com
    `UsuarioFerramenta.fila_robo` (se UM usuário específico tem esse
    acesso) — este campo aqui é sobre a ferramenta em si oferecer ou não
    essa possibilidade. `admin_ferramenta` não precisa do equivalente:
    faz sentido em qualquer ferramenta.
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    nome: str
    slug: str = Field(unique=True, index=True)
    descricao: Optional[str] = None
    url: str
    suporta_fila_robo: bool = Field(default=False)

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

    acesso_manual é o nível extra que restringe o fluxo Manual/URGENTE
    (Henrique, diretoria, 2026-08-19: o Robô virou o modo padrão — mais
    barato, mas não instantâneo — e o Manual passou a ser exclusivo de
    quem realmente precisa gerar algo na hora, custando mais caro por
    isso). É um checkbox livre — na prática só coordenador deve ganhar,
    mas nada impede abrir exceção pontual pra um colaborador específico.

    fila_robo NÃO é mais lido em lugar nenhum do código — a Fila do
    Robô virou acesso padrão de quem já usa a ferramenta (mesmo nível de
    "Relatórios do Robô", que já era assim). Coluna mantida no banco só
    por segurança/histórico, sem migração de DROP COLUMN estabelecida
    neste projeto — não reaproveitar esse campo pra nada novo.

    admin_ferramenta (nível extra "admin só desta ferramenta", dava acesso
    a Configurações do Robô sem ser admin da plataforma) foi REMOVIDO por
    completo (Henrique, diretoria, 2026-08-24): configurar uma ferramenta
    agora exige eh_admin sempre, sem meio-termo — "área extremamente
    sensível". Diferente de fila_robo, esse campo saiu do model E foi
    dropado do banco de verdade (ver COLUNAS_OBSOLETAS, db/session.py),
    porque era uma permissão ativa (afetava quem tinha acesso a quê), não
    só uma coluna morta.
    """

    usuario_id: Optional[int] = Field(
        default=None, foreign_key="usuario.id", primary_key=True
    )
    ferramenta_id: Optional[int] = Field(
        default=None, foreign_key="ferramenta.id", primary_key=True
    )
    fila_robo: bool = Field(default=False)
    acesso_manual: bool = Field(default=False)


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


class UltimoVistoAba(SQLModel, table=True):
    """Quando cada usuário viu por último uma aba específica de uma
    ferramenta — alimenta os badges "+N" do menu do Extratus (Henrique,
    2026-08-13): em vez de uma contagem total que só cresce, o número
    mostra só o que é novo desde a última visita a ESSA aba. Mesmo padrão
    de chave composta que `AcessoFerramenta` já usa (sem `id` próprio).

    `ferramenta_slug` é string solta (não FK pra `Ferramenta`) de
    propósito — quem chama já sabe de qual ferramenta está falando (é
    sempre chamado de dentro do próprio módulo), evitando uma consulta a
    mais só pra resolver o id."""

    usuario_id: Optional[int] = Field(
        default=None, foreign_key="usuario.id", primary_key=True
    )
    ferramenta_slug: str = Field(primary_key=True)
    aba: str = Field(primary_key=True)
    visto_em: datetime = Field(default_factory=datetime.now)


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
