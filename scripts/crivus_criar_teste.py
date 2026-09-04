"""
Cria uma AnalisePublicacao de TESTE no Crivus (Leitor de Publicação),
sem chamar a IA — não gera nenhum gasto real. Serve só pra visualizar a
tela "Análise da Publicação" (o detalhe pós-leitura) navegando pela URL,
sem precisar colar um teor de verdade e pagar uma chamada.

Uso: rode a partir da pasta principal do projeto (mesma regra dos outros
comandos do Extratus):

    .venv\\Scripts\\python scripts\\crivus_criar_teste.py

O script pergunta pra qual usuário anexar o caso de teste (precisa ser um
usuário existente — a tela só abre pro dono do caso), garante acesso ao
Crivus se ainda não tiver, e imprime o caminho da URL no final.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.plataforma.env  # noqa: E402, F401 — carrega o .env

from sqlmodel import select  # noqa: E402

from app.ferramentas.crivus.db.analises import criar_analise_a_partir_da_ia  # noqa: E402
from app.plataforma.db.models import Usuario, UsuarioFerramenta  # noqa: E402
from app.plataforma.db.seed import garantir_ferramentas_padrao  # noqa: E402
from app.plataforma.db.session import obter_sessao  # noqa: E402
from app.plataforma.db.usuarios import definir_ferramentas, listar_todas_ferramentas  # noqa: E402


# Dados fictícios, no mesmo formato que a IA devolveria (ver
# core/ia_cliente.py) — um caso "normal", sem alerta crítico, com 1
# acompanhamento e 2 agendamentos (pra também mostrar como fica um combo
# de mais de um agendamento na tela).
DADOS_TESTE = {
    "processo": "0011223-45.2024.8.26.0100",
    "carteira": "ITAÚ",
    "orgao_julgador": "3ª Vara Cível de São Paulo",
    "carteira_detalhe": "Ação de cobrança de contrato de financiamento veicular movida pelo Itaú.",
    "fase_processual": "Fase de conhecimento, aguardando julgamento de embargos de declaração.",
    "posicao_parte": "Itaú é autor/exequente; parte contrária é o devedor (executado).",
    "natureza_ato": "Decisão que recebe embargos de declaração opostos pela parte contrária.",
    "quem_foi_intimado": "Itaú (parte contrária, exequente/autor no polo ativo).",
    "resumo_objetivo": "Juízo recebeu os embargos de declaração e determinou intimação das partes para manifestação em 5 dias.",
    "comando_judicial": "Recebo os embargos de declaração. Intimem-se as partes para manifestação no prazo legal.",
    "resultado_parte": "Neutro — trâmite processual normal, sem decisão de mérito favorável ou desfavorável.",
    "conclusao_operacional": (
        "Lançar o acompanhamento EMBARGOS DE DECLARAÇÃO e agendar MANIFESTAÇÃO "
        "com prazo de 5 dias corridos a partir da publicação (SLA interno "
        "padrão pra esse tipo de providência simples)."
    ),
    "nivel_confianca": "ALTO",
    "tem_alerta_critico": False,
    "texto_alerta_critico": None,
    "acompanhamentos": [
        {"tipo": "EMBARGOS DE DECLARAÇÃO"},
    ],
    "agendamentos": [
        {"tipo": "MANIFESTAÇÃO", "dias_inicio": 5, "dias_fim": 5},
        {"tipo": "VERIFICAR EXPEDIÇÃO DO MANDADO", "dias_inicio": 0, "dias_fim": 0},
    ],
}

TEOR_TESTE = (
    "[TESTE — não é uma publicação real] Ficam as partes intimadas da decisão "
    "que recebeu os embargos de declaração opostos, determinando manifestação "
    "no prazo de 5 dias."
)

# modelo=None e custo/tokens zerados de propósito — nunca chamou a IA,
# não pode aparecer como gasto real em nenhum painel de custos.
USO_SEM_CUSTO = {
    "modelo": None,
    "tokens_entrada": 0,
    "tokens_saida": 0,
    "custo_estimado_usd": 0.0,
}


def main():
    garantir_ferramentas_padrao()

    with obter_sessao() as sessao:
        usuarios = sessao.exec(select(Usuario)).all()

    if not usuarios:
        print("Nenhum usuário cadastrado ainda — crie um com scripts/criar_usuario.py primeiro.")
        sys.exit(1)

    print("Usuários existentes:")
    for usuario in usuarios:
        print(f"  [{usuario.id}] {usuario.nome} ({usuario.nome_usuario})")

    escolha = input("\nID do usuário que vai acessar essa tela de teste: ").strip()
    if not escolha.isdigit():
        print("ID inválido.")
        sys.exit(1)

    usuario_id = int(escolha)
    usuario = next((u for u in usuarios if u.id == usuario_id), None)
    if not usuario:
        print("Usuário não encontrado.")
        sys.exit(1)

    ferramentas = listar_todas_ferramentas()
    crivus_id = next(f.id for f in ferramentas if f.slug == "leitor-publicacoes")

    if not usuario.eh_admin:
        with obter_sessao() as sessao:
            ja_tem_acesso = sessao.exec(
                select(UsuarioFerramenta).where(
                    UsuarioFerramenta.usuario_id == usuario_id,
                    UsuarioFerramenta.ferramenta_id == crivus_id,
                )
            ).first()

        if not ja_tem_acesso:
            with obter_sessao() as sessao:
                permissoes_atuais = sessao.exec(
                    select(UsuarioFerramenta.ferramenta_id).where(UsuarioFerramenta.usuario_id == usuario_id)
                ).all()
            definir_ferramentas(usuario_id, list(permissoes_atuais) + [crivus_id])
            print(f"(usuário '{usuario.nome_usuario}' não tinha acesso ao Crivus — liberado agora)")

    analise = criar_analise_a_partir_da_ia(
        usuario_id,
        TEOR_TESTE,
        DADOS_TESTE,
        USO_SEM_CUSTO,
        origem="individual",
        npjur="0000099",
        processo=DADOS_TESTE["processo"],
    )

    print(f"\nCaso de teste criado (id {analise.id}), sem nenhum gasto de IA.")
    print(f"Acesse: /crivus/leitor-individual/{analise.id}")
    print(f"(logado como '{usuario.nome_usuario}' — o dono do caso é quem consegue abrir essa URL)")


if __name__ == "__main__":
    main()
