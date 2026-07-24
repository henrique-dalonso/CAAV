from datetime import datetime


def obter_data_atual_formatada():
    return datetime.now().strftime("%d-%m-%Y")


def gerar_nome_relatorio(processo):
    data_atual = obter_data_atual_formatada()

    return f"relatorio_{processo}_{data_atual}.docx"