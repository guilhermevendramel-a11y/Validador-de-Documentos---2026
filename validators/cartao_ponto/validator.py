import os
import re
import tempfile
import cv2
import numpy as np
import pytesseract
import fitz

from validators.cartao_ponto.rules import validar_cartao_ponto


class CartaoPontoValidator:

    # ======================================================
    # 🔹 OCR
    # ======================================================
    def ocr_pagina(self, page):

        pix = page.get_pixmap(dpi=300)

        img = np.frombuffer(pix.samples, dtype=np.uint8)
        img = img.reshape(pix.height, pix.width, pix.n)

        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

        texto = pytesseract.image_to_string(gray, lang="por")

        return texto, img

    # ======================================================
    # 🔹 DETECTAR ASSINATURA
    # ======================================================
    def detectar_assinatura(self, img):
        try:
            h, w = img.shape[:2]
            rodape = img[int(h * 0.7):h, :]

            gray = cv2.cvtColor(rodape, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)

            cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            return any(300 < cv2.contourArea(c) < 15000 for c in cnts)

        except:
            return False

    # ======================================================
    # 🚀 ANALISAR
    # ======================================================
    def analisar(self, caminho_pdf):

        print("\n🚀 ================= PONTO VALIDATOR =================")

        from validators.cartao_ponto.template_engine import extrair_com_fallback

        doc = fitz.open(caminho_pdf)

        texto_completo = ""
        imagens_paginas = []

        # ==================================================
        # 🔹 EXTRAÇÃO DE TEXTO + IMAGEM
        # ==================================================
        for idx, page in enumerate(doc, start=1):

            print(f"\n📄 Página {idx}")

            texto = page.get_text()

            if not texto.strip():
                print("⚠️ Texto vazio → OCR")
                texto_ocr, img = self.ocr_pagina(page)
                texto += "\n" + texto_ocr
            else:
                pix = page.get_pixmap(dpi=150)

                img = np.frombuffer(pix.samples, dtype=np.uint8)
                img = img.reshape(pix.height, pix.width, pix.n)

                if pix.n == 4:
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                else:
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            texto_completo += "\n" + texto
            imagens_paginas.append(img)

        # ==================================================
        # 🔥 EXTRAÇÃO (ENGINE NOVO)
        # ==================================================
        colaboradores = extrair_com_fallback(texto_completo)

        if not colaboradores:
            print("❌ Nenhum colaborador identificado")

            return {
                "status": "erro",
                "colaboradores": [],
                "erros": ["Nenhum colaborador identificado"],
                "avisos": []
            }

        # ==================================================
        # 🔹 VALIDAÇÃO
        # ==================================================
        resultado_final = []

        for idx, col in enumerate(colaboradores):

            nome = col.get("nome")
            competencia = col.get("competencia")
            dias = col.get("dias_trabalhados", 0)
            horas = col.get("horas_total", 0)

            marcacoes_ok = dias >= 5

            # 🔥 agora assinatura funciona
            assinatura_ok = False
            if imagens_paginas:
                assinatura_ok = self.detectar_assinatura(imagens_paginas[-1])

            print("\n👤 Colaborador:", nome)
            print("📅 Competência:", competencia)
            print("📊 Dias:", dias)
            print("⏱ Horas:", horas)
            print("✍️ Assinatura:", assinatura_ok)

            resultado_final.append({
                "nome": nome,
                "competencia": competencia,
                "assinatura": assinatura_ok,
                "marcacoes": marcacoes_ok,
                "datado": True
            })

        # ==================================================
        # 🔥 RULES
        # ==================================================
        resultado_rules = validar_cartao_ponto(resultado_final)

        return {
            "status": resultado_rules["status"],
            "colaboradores": resultado_final,
            "erros": resultado_rules.get("erros", []),
            "avisos": resultado_rules.get("avisos", [])
        }


# ======================================================
# API
# ======================================================
def validar_cartao_ponto_json(pdf_bytes):

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        caminho_pdf = tmp.name

    try:
        validador = CartaoPontoValidator()
        resultado = validador.analisar(caminho_pdf)

        return {
            "status": resultado["status"],
            "documento": "Cartão Ponto",
            "mensagem": "Validação realizada com sucesso",
            "colaboradores": resultado["colaboradores"],
            "erros": resultado["erros"],
            "avisos": resultado["avisos"]
        }

    finally:
        if os.path.exists(caminho_pdf):
            os.remove(caminho_pdf)