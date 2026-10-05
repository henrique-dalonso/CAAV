class ErroParaUsuario(RuntimeError):
    """Falha cuja mensagem já foi escrita pra quem usa a tela — vai pro Job
    como está. Qualquer outra exceção é tratada como técnica: a tela mostra
    uma frase genérica por etapa e o texto cru fica só pro admin (ver
    separar_mensagem_e_detalhe)."""


MENSAGEM_POR_TIPO_ERRO = {
    "erro_pdf": "Não foi possível ler esse PDF. Entre em contato com o suporte técnico.",
    "erro_ia": "Falha na comunicação com a IA. Reenvie esse caso para processamento.",
    "erro_docx": "Falha ao salvar o relatório em Word. Reenvie esse caso para processamento.",
    "erro_movimentacao": "Falha ao mover o arquivo depois de gerar o relatório. Entre em contato com o suporte técnico.",
}

MENSAGEM_ERRO_DESCONHECIDO = "Falha inesperada no processamento. Entre em contato com o suporte técnico."


# Inconsistências da triagem (Conferências, sininho, motivo gravado) —
# mesmos textos pra Fila do Robô (db/checagem_fila.py) e URGENTE
# (db/triagem_manual.py).
TEXTO_DUPLICADO_RELATORIO = "Esse número de processo já possui um relatório gerado pela ferramenta."
TEXTO_DUPLICADO_EM_ANDAMENTO = "Esse número de processo já está sendo processado na fila da ferramenta."
TEXTO_NAO_ENCONTRADO = "Número do processo não localizado/identificado."
TEXTO_FALHA_LEITURA = "Não foi possível ler esse PDF. Entre em contato com o suporte técnico."


# Envio de arquivos recusado (Fila do Robô e URGENTE). Mesmos textos que
# os scripts das telas usam antes do envio (fila.js/gerar_relatorio.js).
MOTIVO_EXTENSAO_INCORRETA = "o arquivo não se trata de um PDF (extensão incorreta)"
MOTIVO_CONTEUDO_INVALIDO = "o arquivo não se trata de um PDF (conteúdo inválido, apesar da extensão .pdf)"
MOTIVO_DUPLICADO_NA_FILA = "o arquivo já existe na fila do robô (duplicado)"

MENSAGEM_LIMITE_ENVIOS = (
    "Muitos arquivos enviados em um curto período de tempo, aguarde alguns minutos e tente novamente."
)
MENSAGEM_PROCESSO_INVALIDO = "Insira um NÚMERO DE PROCESSO válido para liberar esse arquivo."
MENSAGEM_PENDENCIA_RESOLVIDA = "Essa pendência já foi resolvida. Não há nada a ser feito aqui!"


def motivo_tamanho_excedido(limite_mb):
    return f"o arquivo é grande demais (mais que {limite_mb}MB)"


def montar_mensagem_recusados(quantidade_enviados, recusados):
    """`recusados`: [(nome do arquivo, motivo)]. Uma linha por arquivo —
    o banner mostra as quebras de linha (white-space: pre-line)."""
    linhas = [f"{quantidade_enviados} arquivo(s) enviado(s). Os seguintes arquivos foram recusados:"]
    linhas += [f'- Arquivo "{nome}" → MOTIVO: {motivo}.' for nome, motivo in recusados]
    return "\n".join(linhas)


def motivo_liberacao_manual(nome_aprovador=None):
    if nome_aprovador:
        return (
            f"Esse caso foi liberado manualmente por {nome_aprovador} após uma "
            "inconsistência ter sido apontada para conferência."
        )
    return "Esse caso foi liberado manualmente após uma inconsistência ter sido apontada para conferência."


def separar_mensagem_e_detalhe(erro, tipo_erro):
    """Devolve (mensagem pra tela, detalhe técnico ou None)."""
    if isinstance(erro, ErroParaUsuario):
        return str(erro), None

    mensagem = MENSAGEM_POR_TIPO_ERRO.get(tipo_erro, MENSAGEM_ERRO_DESCONHECIDO)
    detalhe = str(erro).strip() or type(erro).__name__
    return mensagem, detalhe
