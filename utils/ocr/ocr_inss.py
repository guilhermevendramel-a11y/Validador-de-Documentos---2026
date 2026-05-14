import pytesseract
import cv2
import numpy as np
from pdf2image import convert_from_path
import re
import fitz

# ============================================================
# PREPROCESSAMENTO (OTIMIZADO PARA DARF/INSS)
# ============================================================
def preprocessar_imagem(img):
    img = np.array(img)
    # Escala de cinza
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Aumento de contraste e nitidez
    gray = cv2.convertScaleAbs(gray, alpha=1.8, beta=10)
    # Threshold adaptativo para destacar números pequenos
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 31, 2
    )
    return thresh

# ============================================================
# NORMALIZAÇÃO DE TEXTO
# ============================================================
def normalizar_texto_ocr(texto):
    texto = texto.upper()
    # Corrige erros comuns de leitura de caracteres
    texto = texto.replace("|", "I").replace("O0", "00")
    # Remove espaços extras preservando quebras de linha para regex de proximidade
    texto = re.sub(r' +', ' ', texto)
    return texto

# ============================================================
# 🔥 EXTRAÇÃO INTELIGENTE DE COMPETÊNCIA (100% AJUSTADO)
# ============================================================
def extrair_competencia_do_texto(texto):
    texto_upper = normalizar_texto_ocr(texto)

    # --- ESTRATÉGIA 1: BUSCA POR "PA:" (MAIS CONFIÁVEL) ---
    # Captura o PA: numérico que aparece na tabela de composição
    m_pa = re.search(r"PA[:\s]*(\d{2}/\d{4})", texto_upper)
    if m_pa:
        return m_pa.group(1)

    # --- ESTRATÉGIA 2: MÊS POR EXTENSO (OUTUBRO/2025) ---
    meses_map = {
        "JANEIRO": "01", "FEVEREIRO": "02", "MARCO": "03", "MARÇO": "03",
        "ABRIL": "04", "MAIO": "05", "JUNHO": "06", "JULHO": "07", 
        "AGOSTO": "08", "SETEMBRO": "09", "OUTUBRO": "10", "NOVEMBRO": "11", "DEZEMBRO": "12"
    }

    # Regex para capturar PERÍODO DE APURAÇÃO seguido de mês por extenso
    # Aceita quebras de linha e espaços (\s*)
    regex_extenso = r"PER[ÍI]ODO\s+DE\s+APURA[CÇ][AÃ]O\s*\n?\s*([A-ZÇ]+)[/\s]*(\d{4})"
    m_ext = re.search(regex_extenso, texto_upper)

    if m_ext:
        nome_mes = m_ext.group(1)
        ano = m_ext.group(2)
        for mes_nome, mes_num in meses_map.items():
            if mes_nome in nome_mes:
                return f"{mes_num}/{ano}"

    # --- ESTRATÉGIA 3: FALLBACK MM/AAAA (ANTI-VENCIMENTO) ---
    # Busca datas MM/AAAA, mas usa Lookbehind (?<!\d/) para garantir 
    # que NÃO haja um dia antes (ex: ignora 19/11/2025, pega apenas 11/2025 se estiver isolado)
    datas_isoladas = re.findall(r"(?<!\d/)\b(\d{2}/\d{4})\b", texto_upper)
    if datas_isoladas:
        # Retorna a primeira data que não tenha um dia associado a ela
        return datas_isoladas[0]

    return None

# ============================================================
# OCR PRINCIPAL
# ============================================================
def extrair_texto_inss(pdf_path):
    print("\n📄 ================= OCR INSS (REVISADO) =================")

    try:
        textos = []
        with fitz.open(pdf_path) as doc:
            for pagina in doc:
                textos.append(pagina.get_text())
        texto_nativo = "\n".join(textos).strip()
        if len(texto_nativo) > 50:
            print("✅ [INSS] Texto nativo OK")
            return texto_nativo
    except Exception as exc:
        print(f"⚠️ [INSS] Leitura nativa falhou: {exc}")
    
    # DPI 300 é essencial para ler os valores pequenos do DARF
    imagens = convert_from_path(pdf_path, dpi=300)
    texto_final = ""

    for i, img in enumerate(imagens):
        print(f"📄 [INSS] Processando página {i+1}...")
        img_proc = preprocessar_imagem(img)
        
        # PSM 6 assume um bloco de texto uniforme
        texto = pytesseract.image_to_string(
            img_proc, lang="por", config="--oem 3 --psm 6"
        )
        texto_final += "\n" + texto

    # Debug de extração
    comp_detectada = extrair_competencia_do_texto(texto_final)
    print(f"🔍 [DEBUG] Competência Identificada: {comp_detectada}")
    
    return texto_final
