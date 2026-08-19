"""
Backup diário do Extratus: banco de dados + pastas de relatórios/PDFs
dos dois módulos (Relatórios e Aburesi).

Como usar:
1. Troque BACKUP_DESTINO abaixo pra um disco/rede SEPARADO da VM (backup
   no mesmo disco não protege contra falha do disco — só ajuda contra
   erro humano, tipo apagar algo sem querer).
2. Rode uma vez à mão pra conferir:
       .venv\\Scripts\\python.exe scripts\\backup.py
3. Agende no Agendador de Tarefas do Windows (Criar Tarefa → gatilho
   diário, ex: 3h da manhã → ação: executar o mesmo comando acima, com
   "Iniciar em" apontando pra pasta raiz do projeto).

Usa a API de backup nativa do SQLite (Connection.backup) — segura mesmo
com o site rodando ao mesmo tempo, não precisa parar nada.
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# TROQUE AQUI antes de agendar de verdade — aponte pra outro disco/rede.
BACKUP_DESTINO = Path(r"D:\Backups\Extratus")

RETENCAO_DIAS = 14

PASTAS_DADOS = [
    "app/ferramentas/extratus/dados/processados",
    "app/ferramentas/extratus/dados/relatorios_prontos",
    "app/ferramentas/extratus/dados/revisao",
    "app/ferramentas/extratus/dados/erros",
    "app/ferramentas/extratus_aburesi/dados/processados",
    "app/ferramentas/extratus_aburesi/dados/relatorios_prontos",
    "app/ferramentas/extratus_aburesi/dados/revisao",
    "app/ferramentas/extratus_aburesi/dados/erros",
]


def backup_banco(destino):
    origem = PROJECT_ROOT / "banco" / "plataforma.db"
    if not origem.exists():
        print(f"Aviso: banco não encontrado em {origem}, pulando.")
        return

    conexao_origem = sqlite3.connect(str(origem))
    conexao_destino = sqlite3.connect(str(destino / "plataforma.db"))
    with conexao_destino:
        conexao_origem.backup(conexao_destino)
    conexao_origem.close()
    conexao_destino.close()


def backup_pastas(destino):
    for pasta_relativa in PASTAS_DADOS:
        origem = PROJECT_ROOT / pasta_relativa
        if not origem.exists():
            continue

        alvo = destino / pasta_relativa
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(origem, alvo, dirs_exist_ok=True)


def limpar_backups_antigos():
    if not BACKUP_DESTINO.exists():
        return

    limite = datetime.now().timestamp() - (RETENCAO_DIAS * 86400)
    for pasta in BACKUP_DESTINO.iterdir():
        if pasta.is_dir() and pasta.stat().st_mtime < limite:
            shutil.rmtree(pasta, ignore_errors=True)


def main():
    carimbo = datetime.now().strftime("%Y-%m-%d_%H-%M")
    destino = BACKUP_DESTINO / carimbo
    destino.mkdir(parents=True, exist_ok=True)

    backup_banco(destino)
    backup_pastas(destino)
    limpar_backups_antigos()

    print(f"Backup concluído em {destino}")


if __name__ == "__main__":
    main()
