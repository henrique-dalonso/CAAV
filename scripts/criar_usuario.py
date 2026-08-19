"""
Cria um usuário do CAAV (Célula Avançada Alonso & Verdiani).

Uso: rode a partir da pasta principal do projeto (mesma regra dos outros
comandos do Extratus):

    .venv\\Scripts\\python scripts\\criar_usuario.py

O script pergunta os dados interativamente e confirma tudo antes de salvar
no banco, pra evitar cadastro errado sem perceber.
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.plataforma.env  # noqa: E402, F401 — carrega o .env

from sqlmodel import select  # noqa: E402

from app.plataforma.auth import gerar_hash_senha  # noqa: E402
from app.plataforma.db.models import Ferramenta, Usuario, UsuarioFerramenta  # noqa: E402
from app.plataforma.db.seed import garantir_ferramentas_padrao  # noqa: E402
from app.plataforma.db.session import obter_sessao  # noqa: E402


def pedir_senha():
    """Tenta esconder a senha ao digitar. Se o terminal não suportar isso
    direito (alguns terminais do Windows falham silenciosamente e a senha
    fica vazia ou errada), avisa e pede de novo de forma visível.
    """
    senha = getpass.getpass("Senha: ")

    if len(senha) < 4:
        print(
            "\nAVISO: a senha capturada ficou muito curta ou vazia — "
            "esse terminal provavelmente não suporta esconder a digitação "
            "direito. Vou pedir de novo, mas agora ela vai aparecer na tela "
            "enquanto você digita."
        )
        senha = input("Senha (visível): ")

    return senha


def main():
    garantir_ferramentas_padrao()

    nome = input("Nome do colaborador: ").strip()
    nome_usuario = input("Nome de usuário (login, sem espaço): ").strip().lower()
    email = input("E-mail: ").strip().lower()
    senha = pedir_senha()
    eh_admin = input("É administrador? (s/N): ").strip().lower() == "s"

    print("\nConfira antes de salvar:")
    print(f"  Nome: {nome}")
    print(f"  Usuário (login): {nome_usuario}")
    print(f"  E-mail: {email}")
    print(f"  Senha: {'*' * len(senha)} ({len(senha)} caracteres)")
    print(f"  Administrador: {'sim' if eh_admin else 'não'}")

    if input("\nConfirma? (s/N): ").strip().lower() != "s":
        print("Cancelado, nada foi salvo.")
        sys.exit(0)

    with obter_sessao() as sessao:
        existente = sessao.exec(
            select(Usuario).where(
                (Usuario.nome_usuario == nome_usuario) | (Usuario.email == email)
            )
        ).first()

        if existente:
            print(f"\nJá existe um usuário com esse nome de usuário ou e-mail.")
            sys.exit(1)

        usuario = Usuario(
            nome=nome,
            nome_usuario=nome_usuario,
            email=email,
            senha_hash=gerar_hash_senha(senha),
            eh_admin=eh_admin,
        )

        sessao.add(usuario)
        sessao.commit()
        sessao.refresh(usuario)

        if eh_admin:
            print(
                f"\nUsuário '{nome}' criado como administrador — "
                "tem acesso automático a todas as ferramentas."
            )
        else:
            ferramentas = sessao.exec(select(Ferramenta)).all()

            if not ferramentas:
                print(f"\nUsuário '{nome}' criado (nenhuma ferramenta cadastrada ainda).")
                return

            print("\nFerramentas disponíveis:")
            for ferramenta in ferramentas:
                print(f"  [{ferramenta.id}] {ferramenta.nome}")

            escolha = input(
                "IDs liberados para este usuário (separados por vírgula): "
            ).strip()

            ids_escolhidos = [
                int(item) for item in escolha.split(",") if item.strip().isdigit()
            ]

            for ferramenta_id in ids_escolhidos:
                sessao.add(
                    UsuarioFerramenta(
                        usuario_id=usuario.id,
                        ferramenta_id=ferramenta_id,
                    )
                )

            sessao.commit()

            print(f"\nUsuário '{nome}' criado com acesso a {len(ids_escolhidos)} ferramenta(s).")


if __name__ == "__main__":
    main()
