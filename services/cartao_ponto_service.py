from concurrent.futures import ThreadPoolExecutor, TimeoutError

from services.document_learning import aprender_documento, encontrar_layout
from utils.ocr.ocr_cartao_ponto import extrair_paginas_cartao_ponto
from utils.templates.template_engine import extrair_com_fallback
from utils.gemini.cartao_ponto import extrair_cartao_ponto_pdf
from utils.signature_detection import detectar_rubrica_global, detectar_rubricas_por_colaborador
from utils.yolo_signature_detection import (
    detectar_assinaturas_yolo,
    detectar_assinaturas_yolo_por_colaborador,
    yolo_disponivel,
)


def nome_suspeito(nome):
    upper = (nome or "").upper()
    termos_empresa = [
        "LTDA", "EIRELI", "ME ", "S/A", "CONSTRU", "MONTAGENS",
        "INDUSTRIAIS", "EMPRESA", "CNPJ", "HORARIO", "HORÁRIO",
        "TRABALHO", "FOLHA", "PONTO",
    ]
    return not nome or any(t in upper for t in termos_empresa)


def deve_revisar_com_gemini(caminho_arquivo, colaboradores):
    if not caminho_arquivo.lower().endswith(".pdf"):
        return False

    if not colaboradores:
        return True

    # PDFs de cartao ponto costumam trazer mais de um colaborador; quando o parser
    # encontra poucos nomes, forca revisao por IA para recuperar colaboradores faltantes.
    if len(colaboradores) < 2:
        return True

    if any(not (c.get("competencia") or "").strip() for c in colaboradores):
        return True

    if any(nome_suspeito(c.get("nome")) for c in colaboradores):
        return True

    # Quando OCR/parser ja retornou colaboradores plausiveis, evita chamada
    # adicional no Gemini para reduzir latencia.
    return False


def escolher_melhor_extracao(colaboradores_atual, resposta_gemini):
    colaboradores_gemini = resposta_gemini.get("colaboradores", []) if isinstance(resposta_gemini, dict) else []

    if not colaboradores_gemini:
        return colaboradores_atual

    atual_suspeito = any(nome_suspeito(c.get("nome")) for c in colaboradores_atual)
    gemini_suspeito = any(nome_suspeito(c.get("nome")) for c in colaboradores_gemini)

    if len(colaboradores_gemini) > len(colaboradores_atual):
        return colaboradores_gemini

    if atual_suspeito and not gemini_suspeito:
        return colaboradores_gemini

    if not colaboradores_atual:
        return colaboradores_gemini

    return colaboradores_atual


def extrair_cartao_ponto_pdf_com_timeout(caminho_arquivo, timeout_segundos=240):
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            futuro = executor.submit(extrair_cartao_ponto_pdf, caminho_arquivo)
            return futuro.result(timeout=timeout_segundos) or {"colaboradores": []}
    except TimeoutError:
        print(f"[PONTO] Timeout Gemini apos {timeout_segundos}s. Seguindo sem Gemini.")
        return {"colaboradores": []}
    except Exception as exc:
        print(f"[PONTO] Falha Gemini com timeout controlado: {exc}")
        return {"colaboradores": []}


# ==========================================================
# ✍️ DETECÇÃO DE ASSINATURA
# ==========================================================
def detectar_assinatura_imagem(caminho_pdf):
    try:
        with fitz.open(caminho_pdf) as doc:
            for pagina in doc:
                pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height,
                    pix.width,
                    pix.n,
                )
                gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

                altura = gray.shape[0]
                regiao = gray[int(altura * 0.65):altura, :]

                _, thresh = cv2.threshold(regiao, 180, 255, cv2.THRESH_BINARY_INV)

                kernel = np.ones((3, 3), np.uint8)
                cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

                contornos, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for cnt in contornos:
                    if 500 < cv2.contourArea(cnt) < 20000:
                        return True

        return False

    except Exception as e:
        print("❌ ERRO OpenCV:", e)
        return False


# Override da assinatura antiga: usa detector robusto para rubricas/manuscritos.
def detectar_assinatura_imagem(caminho_pdf):
    if yolo_disponivel():
        return bool(detectar_assinaturas_yolo(caminho_pdf))
    return detectar_rubrica_global(caminho_pdf)


def texto_indica_assinatura_digital(texto):
    texto_upper = (texto or "").upper()
    termos = [
        "DOCUMENTO ASSINADO ELETRONICAMENTE",
        "ASSINADO ELETRONICAMENTE",
        "ASSINATURA DIGITAL",
        "CERTIFICADO DIGITAL",
        "RELATÓRIO DE ASSINATURAS",
        "RELATORIO DE ASSINATURAS",
        "STATUS: ASSINADO",
        "TOKEN:",
    ]
    return any(termo in texto_upper for termo in termos)


def montar_resumo_assinaturas(colaboradores):
    total = len(colaboradores)
    digitais = sum(1 for col in colaboradores if col.get("assinatura_tipo") == "digital")
    manuais = sum(1 for col in colaboradores if col.get("assinatura_tipo") == "manual/rubrica")
    ausentes = sum(1 for col in colaboradores if not col.get("assinatura"))

    tipos = []
    if digitais:
        tipos.append("Assinatura digital")
    if manuais:
        tipos.append("Manual/Rubrica")
    if not tipos:
        tipos.append("Nao identificada")

    return {
        "total_colaboradores": total,
        "assinatura_digital": digitais,
        "assinatura_manual_rubrica": manuais,
        "assinatura_ausente": ausentes,
        "tipo_predominante": " + ".join(tipos),
    }


# ==========================================================
# 📊 STATUS FINAL
# ==========================================================
def avaliar_status(colaboradores):
    total = len(colaboradores)

    if total == 0:
        return "Reprovado"

    aprovados = sum(
        1 for c in colaboradores
        if c["marcacoes"] and c["assinatura"] and c["competencia_ok"]
    )

    if aprovados == total:
        return "Aprovado"
    elif aprovados > 0:
        return "Parcial"

    return "Reprovado"


# ==========================================================
# 🚀 SERVICE PRINCIPAL
# ==========================================================
def processar_cartao_ponto(caminho_arquivo, competencia_esperada=None):

    print("\n🚀 ================= CARTÃO PONTO =================")

    paginas = extrair_paginas_cartao_ponto(caminho_arquivo)
    colaboradores_extraidos = None

    if not paginas:
        print("OCR sem paginas legiveis. Tentando Gemini diretamente no PDF.")
        resposta_gemini = extrair_cartao_ponto_pdf_com_timeout(caminho_arquivo)
        colaboradores_extraidos = resposta_gemini.get("colaboradores", [])

        if not colaboradores_extraidos:
            return {
                "status": "Reprovado",
                "mensagem": "Falha no OCR e na leitura por IA.",
                "sucesso": False,
                "colaboradores": []
            }

        paginas = []

    # ======================================================
    # 🔥 TEXTO COMPLETO COM PROTEÇÃO
    # ======================================================
    texto_completo = ""

    for p in paginas:
        texto = p.get("texto", "")

        # 🔥 ignora lixo OCR
        if not texto or len(texto.strip()) < 10:
            continue

        texto_completo += "\n" + texto

    if not texto_completo.strip() and not colaboradores_extraidos:
        print("Documento sem texto legivel. Tentando Gemini diretamente no PDF.")
        resposta_gemini = extrair_cartao_ponto_pdf_com_timeout(caminho_arquivo)
        colaboradores_extraidos = resposta_gemini.get("colaboradores", [])

    if not texto_completo.strip() and not colaboradores_extraidos:
        return {
            "status": "Reprovado",
            "mensagem": "Documento sem texto legivel para OCR ou IA.",
            "sucesso": False,
            "colaboradores": []
        }

    # ======================================================
    # 🔥 EXTRAÇÃO INTELIGENTE
    # ======================================================
    print("\n================ TEXTO EXTRAÍDO =================")
    print(texto_completo[:1000])  # evita travar o terminal
    print("=================================================")

    if colaboradores_extraidos is None:
        layout_conhecido, confianca_layout = encontrar_layout("cartao_ponto", texto_completo)
        colaboradores_extraidos = extrair_com_fallback(texto_completo)
        if layout_conhecido:
            print(
                f"[PONTO] Layout aprendido identificado: {layout_conhecido.get('modelo')} "
                f"(confianca={round(confianca_layout, 2)})"
            )

    if not colaboradores_extraidos:
        print("Extracao por texto falhou. Tentando Gemini diretamente no PDF.")
        resposta_gemini = extrair_cartao_ponto_pdf_com_timeout(caminho_arquivo)
        colaboradores_extraidos = resposta_gemini.get("colaboradores", [])

    if deve_revisar_com_gemini(caminho_arquivo, colaboradores_extraidos):
        print("Resultado OCR/parser suspeito ou incompleto. Revisando com Gemini.")
        resposta_gemini = extrair_cartao_ponto_pdf_com_timeout(caminho_arquivo)
        colaboradores_extraidos = escolher_melhor_extracao(colaboradores_extraidos, resposta_gemini)

    print("👥 EXTRAIDOS:", colaboradores_extraidos)

    if not colaboradores_extraidos:
        print("❌ Nenhum colaborador encontrado após extração")

        return {
            "status": "Reprovado",
            "mensagem": "Nenhum colaborador válido identificado.",
            "sucesso": False,
            "colaboradores": []
        }

    # ======================================================
    # 🔹 ASSINATURA (IMAGEM + TEXTO)
    # ======================================================
    assinatura_digital_global = texto_indica_assinatura_digital(texto_completo)

    # ======================================================
    # 🔹 NORMALIZAÇÃO FINAL
    # ======================================================
    lista_colaboradores = []
    nomes_vistos = set()
    nomes_extraidos = [c.get("nome") for c in colaboradores_extraidos if c.get("nome")]
    yolo_habilitado = yolo_disponivel()
    deteccoes_yolo = detectar_assinaturas_yolo(caminho_arquivo) if yolo_habilitado else []
    confianca_yolo_global = max((d.get("confianca", 0) for d in deteccoes_yolo), default=0)
    assinaturas_por_nome = (
        detectar_assinaturas_yolo_por_colaborador(
            caminho_arquivo, nomes_extraidos, deteccoes=deteccoes_yolo
        )
        if yolo_habilitado
        else detectar_rubricas_por_colaborador(caminho_arquivo, nomes_extraidos)
    )
    assinatura_global = bool(deteccoes_yolo) if yolo_habilitado else detectar_assinatura_imagem(caminho_arquivo)

    for col in colaboradores_extraidos:

        nome = col.get("nome")
        competencia = col.get("competencia")
        dias = col.get("dias_trabalhados", 0) or 0
        horas = col.get("horas_total", 0) or 0
        marcacoes_detectadas = bool(col.get("marcacoes"))
        assinatura_informada = "assinatura" in col
        assinatura_detectada = bool(col.get("assinatura"))

        try:
            dias = int(float(dias))
        except Exception:
            dias = 0

        try:
            horas = float(horas)
        except Exception:
            horas = 0

        if not nome:
            continue

        nome_formatado = nome.strip().title()
        nome_key = nome_formatado.lower()

        # 🔥 remove duplicados
        if nome_key in nomes_vistos:
            continue

        nomes_vistos.add(nome_key)

        # ==================================================
        # 🔥 VALIDAÇÕES REAIS
        # ==================================================
        marcacoes_ok = marcacoes_detectadas or (dias >= 5 and horas >= 20)

        competencia_ok = True
        if competencia_esperada and competencia:
            competencia_ok = competencia == competencia_esperada

        assinatura_visual = (
            assinaturas_por_nome.get(nome, {}).get("assinatura")
            or assinaturas_por_nome.get(nome_formatado, {}).get("assinatura")
        )
        if assinatura_informada:
            assinatura_final = assinatura_detectada
            if not assinatura_final and col.get("verificar_assinatura_visual"):
                assinatura_final = bool(assinatura_visual)
        else:
            assinatura_final = assinatura_visual or assinatura_global
        assinatura_final = assinatura_final or assinatura_digital_global
        assinatura_confianca = (
            assinaturas_por_nome.get(nome, {}).get("confianca")
            or assinaturas_por_nome.get(nome_formatado, {}).get("confianca")
            or 0
        )

        if assinatura_visual:
            assinatura_tipo = "manual/rubrica"
            assinatura_origem = "yolo" if yolo_habilitado else "opencv"
        elif assinatura_digital_global and assinatura_final:
            assinatura_tipo = "digital"
            assinatura_origem = "texto"
        elif assinatura_final:
            assinatura_tipo = "manual/rubrica"
            assinatura_origem = "yolo" if (yolo_habilitado and assinatura_global) else "gemini"
        else:
            assinatura_tipo = "ausente"
            assinatura_origem = "nao_identificada"
        if assinatura_confianca == 0 and assinatura_final and yolo_habilitado and assinatura_global:
            assinatura_confianca = confianca_yolo_global

        lista_colaboradores.append({
            "nome": nome_formatado,
            "competencia": competencia or "-",
            "competencia_ok": competencia_ok,
            "assinatura": assinatura_final,
            "assinatura_tipo": assinatura_tipo,
            "assinatura_origem": assinatura_origem,
            "assinatura_confianca": assinatura_confianca,
            "marcacoes": marcacoes_ok,
            "datado": True
        })

    # ======================================================
    # 🔥 RESULTADO FINAL
    # ======================================================
    try:
        aprender_documento(
            "cartao_ponto",
            texto_completo,
            {
                "quantidade_colaboradores": len(lista_colaboradores),
                "nomes": [c.get("nome") for c in lista_colaboradores if c.get("nome")][:20],
                "competencias": sorted(
                    {c.get("competencia") for c in lista_colaboradores if c.get("competencia") and c.get("competencia") != "-"}
                )[:10],
                "tem_marcacoes": any(bool(c.get("marcacoes")) for c in lista_colaboradores),
            },
            origem=caminho_arquivo,
        )
    except Exception as exc:
        print(f"[PONTO] Aviso: nao foi possivel atualizar aprendizado: {exc}")

    return {
        "status": avaliar_status(lista_colaboradores),
        "mensagem": f"{len(lista_colaboradores)} colaborador(es) processado(s).",
        "sucesso": True,
        "assinaturas": montar_resumo_assinaturas(lista_colaboradores),
        "colaboradores": lista_colaboradores
    }
