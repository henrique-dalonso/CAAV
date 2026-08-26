import re
from pathlib import Path

from pypdf import PdfReader


# Abaixo disso, consideramos que a página "não tem texto de verdade" —
# só um cabeçalho/carimbo solto, não o conteúdo real da página.
MINIMO_CARACTERES_PAGINA_COM_TEXTO = 30

# Carimbo de rodapé que o eproc/TJ grava em toda página de um evento com
# PDF anexado — inclusive em páginas cujo conteúdo real é só uma imagem
# escaneada, sem nenhuma camada de texto por trás. Descoberto em
# 2026-08-21 (Henrique, processo real de 274 páginas): 217 delas (79%)
# eram só esse carimbo, cada uma com ~60-70 caracteres — acima da régua
# de MINIMO_CARACTERES_PAGINA_COM_TEXTO — então a régua sozinha achava
# que a página "tinha texto", quando na verdade era 100% imagem (e o
# relatório saía com buracos silenciosos nessas páginas). Precisa
# remover o carimbo ANTES de medir.
PADRAO_CARIMBO_PAGINA_EPROC = re.compile(
    r"Processo\s+[\d.\-]+,\s*Evento\s+\d+,\s*\w+,\s*P[áa]gina\s+\d+",
    re.IGNORECASE,
)


def _texto_real_da_pagina(texto_bruto):
    """Texto de uma página descontando o carimbo de rodapé do eproc (ver
    PADRAO_CARIMBO_PAGINA_EPROC) — usado só pra MEDIR se a página tem
    conteúdo de verdade, não altera o texto enviado pra IA."""
    return PADRAO_CARIMBO_PAGINA_EPROC.sub("", texto_bruto).strip()


# Letras esperadas num documento em português — usada só pra detectar
# texto EMBARALHADO por fonte com mapeamento de caractere quebrado
# (achado real, Henrique, 2026-08-26, processo verdadeiro de 321
# páginas): algumas fontes embutidas no PDF (comuns em petição gerada
# por certos editores/templates de escritório) têm o ToUnicode CMap
# trocado — o PDF renderiza certinho na tela, mas o texto por trás sai
# tipo "coı pedido liıiĲaŘ" em vez de "com pedido liminar". Confirmado
# com pypdf E PyMuPDF (as duas bibliotecas devolvem o mesmo texto
# embaralhado) — não é bug de biblioteca, é a fonte do PDF mesmo.
LETRAS_PORTUGUES = set("abcdefghijklmnopqrstuvwxyzáàâãéèêíìîóòôõúùûüçñ")

# Calibrado com dado real do processo que motivou esse achado, não
# chute: nas páginas comprovadamente LIMPAS, a taxa nunca passou de 2%;
# nas comprovadamente EMBARALHADAS, nunca ficou abaixo de 9,7%. 5% fica
# no meio do vão, com folga de mais de 2x dos dois lados — pensado pra
# não arriscar marcar página boa como embaralhada (Henrique: "cuidado
# pra não... quebrar a qualidade atual").
LIMITE_PROPORCAO_LETRAS_ESTRANHAS = 0.05


def _parece_texto_embaralhado(texto_real):
    """True quando a página tem texto suficiente pra passar no teste de
    MINIMO_CARACTERES_PAGINA_COM_TEXTO, mas boa parte das letras não são
    do alfabeto português — sinal de fonte com mapeamento quebrado, não
    de PDF de verdade sem texto nenhum. Sem essa checagem, essas páginas
    contavam como "tem texto de verdade" e o conteúdo ilegível ia direto
    pra IA sem nenhum aviso — muito mais perigoso que o PDF realmente
    escaneado (que pelo menos já tinha tratamento)."""
    letras = [c for c in texto_real.lower() if c.isalpha()]

    if len(letras) < MINIMO_CARACTERES_PAGINA_COM_TEXTO:
        return False  # já cai na régua de "sem texto" de qualquer jeito

    estranhas = sum(1 for c in letras if c not in LETRAS_PORTUGUES)
    return (estranhas / len(letras)) > LIMITE_PROPORCAO_LETRAS_ESTRANHAS


def extrair_paginas_pdf(caminho_pdf):
    """Extrai o texto de cada página do PDF separadamente (sem juntar tudo
    numa string só) — usado tanto pelo diagnóstico normal quanto pela
    divisão em pedaços de processos grandes demais pra uma chamada só
    (ver `ia_cliente._dividir_paginas_em_pedacos`). Cada página já vem
    com seu marcador (`--- Página N de M ---`), pra IA poder referenciar
    de onde tirou cada informação mesmo quando o texto é lido em pedaços."""
    caminho_pdf = Path(caminho_pdf)
    leitor = PdfReader(str(caminho_pdf))

    total_paginas = len(leitor.pages)
    paginas = []

    for indice, pagina in enumerate(leitor.pages, start=1):
        conteudo = pagina.extract_text() or ""
        paginas.append({
            "numero": indice,
            "texto_bruto": conteudo,
            "texto_marcado": f"--- Página {indice} de {total_paginas} ---\n{conteudo}",
        })

    return paginas, total_paginas


def extrair_texto_pdf_com_diagnostico(caminho_pdf):
    """Extrai o texto de cada página do PDF (com marcador de página, pra IA
    poder referenciar de onde tirou cada informação) e devolve também um
    diagnóstico: quantas páginas vieram sem texto real. Uma proporção alta
    de páginas vazias é o sinal de que o PDF é digitalizado (escaneado,
    sem camada de texto) — precisa ser tratado diferente do PDF nativo.

    "Sem texto real" conta 2 situações — a página literalmente vazia
    (menos de MINIMO_CARACTERES_PAGINA_COM_TEXTO) E a página com texto
    embaralhado por fonte quebrada (ver _parece_texto_embaralhado) —
    juntas em paginas_sem_texto de propósito, pra parece_digitalizado
    tratar as duas como o mesmo sinal de "não dá pra confiar nesse
    texto" sem precisar de um caminho de código novo. paginas_embaralhadas
    fica separado só pra mensagem de erro poder ser mais específica.
    """
    paginas, total_paginas = extrair_paginas_pdf(caminho_pdf)

    paginas_vazias = 0
    paginas_embaralhadas = 0

    for pagina in paginas:
        texto_real = _texto_real_da_pagina(pagina["texto_bruto"])

        if len(texto_real) < MINIMO_CARACTERES_PAGINA_COM_TEXTO:
            paginas_vazias += 1
        elif _parece_texto_embaralhado(texto_real):
            paginas_embaralhadas += 1

    texto_completo = "\n\n".join(pagina["texto_marcado"] for pagina in paginas)

    return {
        "texto": texto_completo,
        "total_paginas": total_paginas,
        "paginas_sem_texto": paginas_vazias + paginas_embaralhadas,
        "paginas_embaralhadas": paginas_embaralhadas,
        "caracteres": len(texto_completo),
    }


# Mesmo limite usado em 2 lugares (Henrique, 2026-08-13): decide se o PDF
# vai pra IA como texto ou como imagem nativa (ia_cliente.py) E rebaixa a
# confiança da detecção do processo quando o documento é escaneado
# (processo_detector.ajustar_confianca_por_digitalizacao) — mora aqui, ao
# lado do diagnóstico que ele consome, pra não existir 2 definições
# divergentes do que "parece digitalizado" significa.
LIMITE_PROPORCAO_PAGINAS_SEM_TEXTO = 0.15


def parece_digitalizado(total_paginas, paginas_sem_texto):
    """True quando a proporção de páginas sem texto real sugere que o PDF
    é escaneado/digitalizado (sem camada de texto), não um PDF nativo do
    sistema do tribunal."""
    if total_paginas <= 0:
        return True

    return (paginas_sem_texto / total_paginas) > LIMITE_PROPORCAO_PAGINAS_SEM_TEXTO