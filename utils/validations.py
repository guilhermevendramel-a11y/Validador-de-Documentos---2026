import re
import unicodedata

# ============================================================
# 1. NORMALIZAÇÃO E LIMPEZA (ESSENCIAL PARA O GEMINI)
# ============================================================

def normalizar_nome(nome: str) -> str:
    """
    Remove acentos e sujeiras, padronizando para comparação.
    Ex: 'Joâo da S|lva' -> 'JOAO DA SILVA'
    """
    if not nome:
        return ""
    
    # Remove acentos (NFKD separa o caractere do acento)
    nfkd_form = unicodedata.normalize('NFKD', nome)
    nome_sem_acento = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    
    # Remove caracteres que não são letras ou espaços
    nome_limpo = re.sub(r'[^a-zA-Z\s]', ' ', nome_sem_acento)
    
    # Converte para maiúsculas e remove espaços duplos
    return " ".join(nome_limpo.split()).upper()


def limpar(texto: str) -> str:
    """
    Limpa o texto vindo do OCR para o Gemini ler melhor.
    """
    if not texto:
        return ""

    texto = texto.replace("\x0c", "\n") # Quebra de página vira quebra de linha
    texto = texto.replace("\r", "")
    
    # Normaliza espaços horizontais (tabs e espaços duplos)
    texto = re.sub(r"[ \t]+", " ", texto)
    
    # Remove excesso de linhas vazias para não gastar tokens à toa
    texto = re.sub(r"\n\s*\n", "\n", texto)

    return texto.strip()


# ============================================================
# 2. EXTRAÇÃO VIA REGEX (BACKUP SE A IA FALHAR)
# ============================================================

def extrair_competencia(texto: str):
    if not texto: return None
    texto_up = texto.upper()

    # Padrão: 07/2025 ou COMP. 07/2025
    padroes = [
        r"COMP\.?\s*APURA[CÇ][AÃ]O\s*(\d{2}\s*/\s*\d{4})",
        r"\b(0[1-9]|1[0-2])\s*[/\-]\s*(20\d{2})\b"
    ]

    for p in padroes:
        m = re.search(p, texto_up)
        if m:
            res = m.group(1).replace(" ", "")
            return res if "/" in res else f"{m.group(1)}/{m.group(2)}"
    return None

# Mantenha suas outras funções (extrair_valor, extrair_banco, etc) abaixo...

# ============================================================
# FUNÇÕES PARA FGTS E OUTROS (NECESSÁRIAS PARA O BUILD)
# ============================================================

def extrair_valor(texto: str):
    """
    Extrai valores monetários (ex: 1.250,00)
    """
    if not texto:
        return None
    # Busca padrões de R$ ou apenas números com vírgula
    match = re.search(r'(?:R\$?\s*)?(\d{1,3}(?:\.\d{3})*,\d{2})', texto)
    if match:
        return match.group(1)
    return None

def extrair_data_pagamento(texto: str):
    """
    Extrai datas no formato DD/MM/AAAA
    """
    if not texto:
        return None
    match = re.search(r'(\d{2}/\d{2}/\d{4})', texto)
    if match:
        return match.group(1)
    return None

# A função extrair_competencia nós já ajustamos antes, 
# certifique-se de que o nome está exatamente assim.