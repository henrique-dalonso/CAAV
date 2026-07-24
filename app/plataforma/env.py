"""Carrega variáveis de ambiente do arquivo .env (fora do git) assim que
qualquer parte do app for importada. Segredos (chave de sessão, chave de
IA) vivem só aqui — nunca em config.json.
"""

from dotenv import load_dotenv

load_dotenv()
