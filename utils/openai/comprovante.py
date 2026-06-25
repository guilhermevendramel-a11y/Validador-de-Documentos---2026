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


def extrair_comprovante_openai_pdf(caminho_pdf, texto_ocr="", max_paginas=6):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not caminho_pdf or not Path(caminho_pdf).exists():
        return {"pagamentos": [], "motivo": "openai_indisponivel"}

    try:
        imagens = _render_pdf_para_data_urls(caminho_pdf, max_paginas=max_paginas, dpi=220)
        prompt = aplicar_politica_prompt(
            """
Voce esta lendo comprovantes de pagamento/transferencia brasileiros com ajuda de OCR e visao.
O OCR pode falhar em trechos do documento, entao use as imagens e o texto como apoio.

Tarefa principal:
- Identifique apenas o(s) beneficiario(s) / colaborador(es) que receberam o pagamento.
- Extraia o valor pago de cada comprovante.
- Se existir data da transferencia, informe.
- Se o PDF tiver mais de um comprovante, devolva todos em uma lista.

Regras:
- Nao invente dados.
- Nao retorne empresa pagadora, CNPJ, agencia ou conta como nome do colaborador.
- Nao retorne valor zero a menos que o documento mostre explicitamente zero.
- Retorne somente JSON valido.

Schema:
{
  "pagamentos": [
    {
      "nome": "",
      "valor_pago": 0.0,
      "data_pagamento": "",
      "banco": "",
      "empresa_pagadora": "",
      "confianca": 0.0,
      "observacoes": []
    }
  ],
  "motivo": ""
}

Se o comprovante tiver apenas um pagamento, retorne uma lista com um unico item.
Se houver ruído no OCR, priorize o valor legível nas imagens.
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
            model=os.getenv("OPENAI_MODEL_COMPROVANTE", os.getenv("OPENAI_MODEL_CARTAO_PONTO", "gpt-4.1-mini-2025-04-14")),
            temperature=0,
        )
        if erro or not payload:
            return {"pagamentos": [], "motivo": erro or "falha_openai"}

        txt = _extrair_texto_resposta_openai(payload)
        dados = json.loads(_limpar_json(txt)) if txt else {}
        if not isinstance(dados, dict):
            return {"pagamentos": [], "motivo": "resposta_invalida"}

        itens = dados.get("pagamentos")
        if not isinstance(itens, list):
            itens = [dados] if dados.get("nome") or dados.get("valor_pago") or dados.get("valor") else []

        pagamentos = []
        for item in itens:
            if not isinstance(item, dict):
                continue
            nome = str(item.get("nome") or item.get("nome_colaborador") or "").strip()
            valor = _normalizar_valor(item.get("valor_pago") or item.get("valor") or item.get("liquido"))
            if not nome and valor <= 0:
                continue
            pagamentos.append(
                {
                    "nome": nome,
                    "valor_pago": valor,
                    "data_pagamento": str(item.get("data_pagamento") or item.get("data") or "").strip(),
                    "banco": str(item.get("banco") or "").strip(),
                    "empresa_pagadora": str(item.get("empresa_pagadora") or "").strip(),
                    "confianca": float(item.get("confianca") or 0.0),
                    "observacoes": list(item.get("observacoes") or []),
                }
            )

        return {
            "pagamentos": pagamentos,
            "motivo": str(dados.get("motivo") or "ok").strip() or "ok",
        }
    except Exception as exc:
        return {"pagamentos": [], "motivo": f"erro_openai: {exc}"}
