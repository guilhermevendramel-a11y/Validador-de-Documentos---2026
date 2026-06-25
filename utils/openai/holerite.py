import json
import os
from pathlib import Path

import fitz
import numpy as np
from dotenv import load_dotenv

from utils.openai.cartao_ponto import (
    _extrair_texto_resposta_openai,
    _post_openai_response,
    imagem_cv2_para_data_url_jpeg,
)
from utils.prompt_policy import aplicar_politica_prompt


load_dotenv(override=True)


def _limpar_json(texto):
    t = str(texto or "").strip()
    if not t:
        return ""
    ini = t.find("{")
    fim = t.rfind("}")
    if ini >= 0 and fim > ini:
        t = t[ini : fim + 1]
    return t


def _render_pdf_para_data_urls(caminho_pdf, max_paginas=6, dpi=220):
    imagens = []
    with fitz.open(caminho_pdf) as doc:
        limite = min(len(doc), max_paginas)
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        for i in range(limite):
            page = doc[i]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                arr = arr[:, :, :3]
            imagens.append(imagem_cv2_para_data_url_jpeg(arr, qualidade=85))
    return [img for img in imagens if img]


def _normalizar_valor(valor):
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)
    txt = str(valor).strip().replace("R$", "").replace("r$", "").replace(" ", "")
    txt = txt.replace(".", "").replace(",", ".")
    try:
        return round(float(txt), 2)
    except Exception:
        return 0.0


def extrair_holerite_openai_pdf(caminho_pdf, texto_ocr="", competencia_esperada=None, max_paginas=6):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not caminho_pdf or not Path(caminho_pdf).exists():
        return {"colaboradores": [], "motivo": "openai_indisponivel"}

    try:
        imagens = _render_pdf_para_data_urls(caminho_pdf, max_paginas=max_paginas, dpi=220)
        prompt = aplicar_politica_prompt(
            f"""
Voce esta lendo holerites brasileiros com ajuda de OCR e visao.
O OCR pode falhar em trechos do documento, entao use as imagens e o texto como apoio.

Tarefa principal:
- Identifique apenas o colaborador.
- Extraia o valor liquido ao lado do rotulo de valor liquido / liquido a receber / total liquido.
- Se existir assinatura/rubrica e data proxima, informe.

Regras:
- Nao invente dados.
- Nao retorne empresa, CNPJ ou valores de provento/desconto.
- Retorne somente JSON valido.

Schema:
{{
  "colaboradores": [
    {{
      "nome": "",
      "valor_liquido": 0.0,
      "competencia": "MM/AAAA",
      "assinatura": false,
      "tipo_assinatura": "ausente",
      "data_assinatura": "",
      "confianca": 0.0,
      "observacoes": []
    }}
  ],
  "motivo": ""
}}

Competencia esperada: {competencia_esperada or "nao informada"}.
"""
        )

        texto_base = str(texto_ocr or "").strip()
        if texto_base:
            prompt = f"{prompt}\n\nTEXTO OCR:\n{texto_base}"

        content = [{"type": "input_text", "text": prompt}]
        for img in imagens:
            content.append({"type": "input_image", "image_url": img})

        payload, erro = _post_openai_response(
            content,
            model=os.getenv("OPENAI_MODEL_HOLERITE", os.getenv("OPENAI_MODEL_CARTAO_PONTO", "gpt-4.1-mini-2025-04-14")),
            temperature=0,
        )
        if erro or not payload:
            return {"colaboradores": [], "motivo": erro or "falha_openai"}

        txt = _extrair_texto_resposta_openai(payload)
        dados = json.loads(_limpar_json(txt)) if txt else {}
        if not isinstance(dados, dict):
            return {"colaboradores": [], "motivo": "resposta_invalida"}

        itens = dados.get("colaboradores")
        if not isinstance(itens, list):
            itens = [dados] if dados.get("nome") or dados.get("valor_liquido") else []

        colaboradores = []
        for item in itens:
            if not isinstance(item, dict):
                continue
            nome = str(item.get("nome") or item.get("nome_colaborador") or "").strip()
            valor = _normalizar_valor(item.get("valor_liquido") or item.get("valor") or item.get("liquido"))
            if not nome and valor <= 0:
                continue
            assinatura_raw = item.get("assinatura")
            if isinstance(assinatura_raw, dict):
                assinatura = bool(assinatura_raw.get("presente"))
                tipo_assinatura = str(assinatura_raw.get("tipo") or "").strip() or ("assinatura" if assinatura else "ausente")
            else:
                assinatura = bool(assinatura_raw)
                tipo_assinatura = str(item.get("tipo_assinatura") or ("assinatura" if assinatura else "ausente")).strip()

            colaboradores.append(
                {
                    "nome": nome,
                    "valor_liquido": valor,
                    "competencia": str(item.get("competencia") or competencia_esperada or "").strip(),
                    "assinatura": assinatura,
                    "tipo_assinatura": tipo_assinatura,
                    "data_assinatura": str(item.get("data_assinatura") or item.get("data") or "").strip(),
                    "confianca": float(item.get("confianca") or 0.0),
                    "observacoes": list(item.get("observacoes") or []),
                }
            )

        return {
            "colaboradores": colaboradores,
            "motivo": str(dados.get("motivo") or "ok").strip() or "ok",
        }
    except Exception as exc:
        return {"colaboradores": [], "motivo": f"erro_openai: {exc}"}
