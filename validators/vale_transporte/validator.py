import re
from typing import Dict, List

import fitz

from utils.ocr import extrair_texto_pdf_inteligente
from utils.digital_signature_detection import detectar_autenticacao_digital
from utils.yolo_signature_detection import detectar_assinaturas_yolo, yolo_disponivel


def _normalizar(texto: str) -> str:
    texto = str(texto or "").upper()
    texto = (
        texto.replace("Á", "A").replace("À", "A").replace("Â", "A").replace("Ã", "A")
        .replace("É", "E").replace("Ê", "E")
        .replace("Í", "I")
        .replace("Ó", "O").replace("Ô", "O").replace("Õ", "O")
        .replace("Ú", "U")
        .replace("Ç", "C")
    )
    return re.sub(r"\s+", " ", texto).strip()


def _limpar_nome(nome: str) -> str:
    n = _normalizar(nome)
    n = re.sub(r"^TERMO DE DISPENSA DE VALE TRANSPORTE\s+", "", n).strip()
    n = re.sub(r"\b(RG|CPF|DATA|TOKEN|STATUS|ASSINATURA|PONTOS DE AUTENTICACAO)\b.*$", "", n).strip()
    n = re.sub(r"\s{2,}", " ", n).strip()
    return n


def _extrair_paginas(caminho_pdf: str) -> List[str]:
    paginas = []
    try:
        with fitz.open(caminho_pdf) as doc:
            for page in doc:
                txt = page.get_text() or ""
                paginas.append(txt)
    except Exception:
        return []

    # fallback OCR se texto nativo veio muito pobre
    if sum(len((p or "").strip()) for p in paginas) < 300:
        ocr_txt = extrair_texto_pdf_inteligente(caminho_pdf) or ""
        if ocr_txt.strip():
            return [ocr_txt]

    return paginas


def _tipo_pagina(texto_norm: str) -> str:
    if "TERMO DE DISPENSA" in texto_norm and "VALE TRANSPORTE" in texto_norm:
        return "termo"
    if "RECIBO VALE TRANSPORTE" in texto_norm and "DECLARO TER RECEBIDO" in texto_norm:
        return "recibo"
    if any(t in texto_norm for t in ["COMPROVANTE DE TRANSFERENCIA", "AUTENTICACAO NO COMPROVANTE", "DADOS DA TRANSACAO", "PIX", "TEF"]):
        return "comprovante"
    if any(t in texto_norm for t in ["STATUS: ASSINADO", "RELATORIO DE ASSINATURAS", "ASSINADO DIGITALMENTE", "DOCUMENTO ASSINADO ELETRONICAMENTE", "ZAPSIGN"]):
        return "assinatura"
    return "outro"


def _nome_termo(texto: str) -> str:
    m = re.search(r"(?im)^\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]{7,100}),\s*brasileiro", texto)
    if m:
        n = _limpar_nome(m.group(1))
        if len(n) >= 8:
            return n
    return ""


def _nome_recibo(texto: str) -> str:
    p1 = re.search(r"(?im)RECIBO\s+VALE\s+TRANSPORTE[^\n]*\n\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]{5,100})", texto)
    if p1:
        n = _limpar_nome(p1.group(1))
        if len(n) >= 8:
            return n

    p2 = re.search(r"(?im)\bEU,\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]{5,100}),\s*RG", texto)
    if p2:
        n = _limpar_nome(p2.group(1))
        if len(n) >= 8:
            return n

    return ""


def _nome_comprovante(texto: str) -> str:
    p1 = re.search(r"(?is)DADOS\s+DE\s+QUEM\s+ESTA\s+RECEBENDO.*?\bNOME\b\s*\n\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]{5,100})", texto)
    if p1:
        n = _limpar_nome(p1.group(1))
        if len(n) >= 8:
            return n

    p2 = re.search(r"(?im)^\s*NOME\s*:\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]{5,100})", texto)
    if p2:
        n = _limpar_nome(p2.group(1))
        if len(n) >= 8:
            return n

    return ""


def _termo_nao_optante_ok(texto_norm: str) -> bool:
    return "VALE TRANSPORTE" in texto_norm and any(t in texto_norm for t in [
        "TERMO DE DISPENSA", "DISPENSA DE VALE TRANSPORTE", "NAO UTILIZARA O BENEFICIO", "NAO DESEJO USUFRUIR", "DESISTENCIA", "MEIO PROPRIO"
    ])


def _match_nome(a: str, b: str) -> bool:
    if not a or not b:
        return False
    na, nb = _normalizar(a), _normalizar(b)
    return na == nb or na in nb or nb in na


class VTValidator:
    def analisar(self, caminhos_pdf):
        paginas_info: List[Dict] = []
        texto_global_auth = []
        yolo_modelo_ok = yolo_disponivel()
        yolo_por_arquivo = {}
        yolo_deteccoes_total = 0

        for caminho in caminhos_pdf or []:
            caminho_key = str(caminho or "")
            if yolo_modelo_ok:
                deteccoes = detectar_assinaturas_yolo(caminho)
                yolo_por_arquivo[caminho_key] = len(deteccoes) > 0
                yolo_deteccoes_total += len(deteccoes)
            else:
                yolo_por_arquivo[caminho_key] = False
            paginas = _extrair_paginas(caminho)
            for idx, txt in enumerate(paginas):
                norm = _normalizar(txt)
                tipo = _tipo_pagina(norm)
                nome = ""
                if tipo == "termo":
                    nome = _nome_termo(txt)
                elif tipo == "recibo":
                    nome = _nome_recibo(txt)
                elif tipo == "comprovante":
                    nome = _nome_comprovante(txt)

                paginas_info.append({
                    "idx": len(paginas_info),
                    "tipo": tipo,
                    "texto": txt,
                    "norm": norm,
                    "nome": nome,
                    "arquivo": caminho_key,
                })
                texto_global_auth.append(txt)

        auth_digital = detectar_autenticacao_digital("\n".join(texto_global_auth))

        resultados = []

        # Fluxo A: termo de não optante
        termo_pages = [p for p in paginas_info if p["tipo"] == "termo"]
        assinatura_pages = [p for p in paginas_info if p["tipo"] == "assinatura"]
        for t in termo_pages:
            nome = t["nome"] or "COLABORADOR NAO IDENTIFICADO"
            termo_ok = _termo_nao_optante_ok(t["norm"])
            assinatura_ok = (
                any(0 <= s["idx"] - t["idx"] <= 2 for s in assinatura_pages)
                or ("ASSINATURA" in t["norm"])
                or bool(yolo_por_arquivo.get(t.get("arquivo")))
            )
            status = "OK" if (termo_ok and assinatura_ok) else "Pendente"
            resultados.append({
                "colaborador": nome,
                "status": status,
                "evidencia": "Não optante (Termo assinado e validado)" if status == "OK" else "Falta assinatura digital ou termo de não optante",
                "assinatura_digital": assinatura_ok,
                "termo_nao_optante": termo_ok,
            })

        # Fluxo B: recibo + comprovante
        recibo_pages = [p for p in paginas_info if p["tipo"] == "recibo"]
        comprovante_pages = [p for p in paginas_info if p["tipo"] == "comprovante"]
        usados_comp = set()
        for r in recibo_pages:
            nome_r = r["nome"]
            candidato = None
            # prioriza comprovante logo após recibo com nome compatível
            for c in comprovante_pages:
                if c["idx"] in usados_comp:
                    continue
                if not (0 < c["idx"] - r["idx"] <= 2):
                    continue
                if nome_r and c["nome"] and not _match_nome(nome_r, c["nome"]):
                    continue
                candidato = c
                break

            if candidato:
                usados_comp.add(candidato["idx"])

            nome = nome_r or (candidato["nome"] if candidato else "") or "COLABORADOR NAO IDENTIFICADO"
            recibo_ok = True
            comprovante_ok = candidato is not None
            status = "OK" if (recibo_ok and comprovante_ok and nome != "COLABORADOR NAO IDENTIFICADO") else "Pendente"
            resultados.append({
                "colaborador": nome,
                "status": status,
                "evidencia": "Recibo VT + comprovante de pagamento validados" if status == "OK" else "Falta recibo, comprovante ou nome do colaborador",
                "assinatura_digital": comprovante_ok,
                "termo_nao_optante": False,
            })

        # Se não classificou nada útil, tenta fallback global
        if not resultados:
            texto_global = "\n".join(p["texto"] for p in paginas_info)
            nome = _nome_termo(texto_global) or _nome_recibo(texto_global) or _nome_comprovante(texto_global) or "COLABORADOR NAO IDENTIFICADO"
            resultados = [{
                "colaborador": nome,
                "status": "Pendente",
                "evidencia": "Layout de VT não reconhecido",
                "assinatura_digital": False,
                "termo_nao_optante": False,
            }]

        total = len(resultados)
        ok = sum(1 for r in resultados if r["status"] == "OK")
        status_global = "Aprovado" if total and ok == total else ("Parcial" if ok > 0 else "Pendente")

        return {
            "status": status_global,
            "mensagem": "Validação de Vale Transporte concluída" if status_global != "Pendente" else "Há colaboradores sem evidência suficiente de VT",
            "validacoes": resultados,
            "autenticacao_digital": auth_digital,
            "assinatura_yolo": {
                "modelo_disponivel": yolo_modelo_ok,
                "deteccoes_totais": yolo_deteccoes_total,
            },
            "colaboradores": [
                {
                    "nome": r["colaborador"],
                    "assinatura": bool(r.get("assinatura_digital")),
                    "assinatura_tipo": "digital/comprovante" if r.get("assinatura_digital") else "ausente",
                    "status": r["status"],
                }
                for r in resultados
            ],
        }
