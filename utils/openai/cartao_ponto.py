import base64
import json
import os
import re
import urllib.request
import urllib.error

import fitz
import cv2
import numpy as np
from dotenv import load_dotenv

from utils.prompt_policy import aplicar_politica_prompt

load_dotenv(override=True)


def _limpar_json(texto):
    t = str(texto or "").strip()
    t = re.sub(r"```json|```", "", t, flags=re.IGNORECASE).strip()
    ini = t.find("{")
    fim = t.rfind("}")
    if ini >= 0 and fim > ini:
        t = t[ini : fim + 1]
    return t


def _extrair_texto_resposta_openai(payload):
    # Estruturas comuns do endpoint /v1/responses
    if isinstance(payload, dict):
        if isinstance(payload.get("output_text"), str) and payload.get("output_text").strip():
            return payload.get("output_text")
        out = payload.get("output") or []
        partes = []
        for item in out:
            for c in item.get("content") or []:
                txt = c.get("text")
                if isinstance(txt, str) and txt.strip():
                    partes.append(txt)
                elif isinstance(txt, dict) and isinstance(txt.get("value"), str):
                    partes.append(txt.get("value"))
        if partes:
            return "\n".join(partes)
    return ""


def imagem_cv2_para_data_url_jpeg(imagem, qualidade=85):
    """
    Recebe uma imagem OpenCV ou numpy array.
    Converte para JPEG.
    Retorna string no formato: data:image/jpeg;base64,...
    """
    if imagem is None:
        return ""
    arr = np.array(imagem)
    if arr.size == 0:
        return ""
    if len(arr.shape) == 2:
        arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    ok, enc = cv2.imencode(".jpg", arr, [int(cv2.IMWRITE_JPEG_QUALITY), int(max(40, min(95, qualidade)))])
    if not ok:
        return ""
    b64 = base64.b64encode(enc.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _post_openai_response(content, model=None, temperature=0):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None, "openai_sem_api_key"
    # Cartao ponto visual: usar apenas modelos com suporte robusto a input_image.
    modelos = [
        model or os.getenv("OPENAI_MODEL_CARTAO_PONTO", "gpt-4.1-mini-2025-04-14"),
        "gpt-4.1-mini-2025-04-14",
        "gpt-4.1-mini",
        "gpt-4.1",
    ]
    ultimo_erro = None
    for m in modelos:
        body = {
            "model": m,
            "temperature": temperature,
            "input": [{"role": "user", "content": content}],
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            return json.loads(raw), None
        except urllib.error.HTTPError as exc:
            try:
                ultimo_erro = exc.read().decode("utf-8", errors="ignore")[:400]
            except Exception:
                ultimo_erro = str(exc)
            continue
        except Exception as exc:
            ultimo_erro = str(exc)
            continue
    return None, f"erro_openai:{ultimo_erro or 'falha_modelo'}"


def analisar_pagina_cartao_ponto_openai_vision(
    imagem,
    pagina_numero,
    layout_detectado=None,
    competencia_esperada=None,
    nomes_esperados=None,
    tipo_pagina=None,
):
    """
    tipo_pagina:
    - frente
    - verso
    """
    # Compat: callers antigos passavam "tipo_pagina" (frente/verso).
    layout_in = str(layout_detectado or "").strip().lower()
    tipo_in = str(tipo_pagina or "").strip().lower()
    if not tipo_in:
        if layout_in in {"manual_verso", "assinatura_digital_log"}:
            tipo_in = "verso"
        elif layout_in in {"manual_frente"}:
            tipo_in = "frente"
        else:
            tipo_in = "frente"

    out = {
        "pagina": int(pagina_numero or 0),
        "tipo_pagina": tipo_in,
        "layout": layout_in or "",
        "nome": "",
        "nome_encontrado": False,
        "competencia": "",
        "marcacoes_encontradas": False,
        "assinatura": False,
        "assinatura_tipo": "ausente",
        "confianca": 0.0,
        "motivo": "",
        "avisos": [],
    }
    data_url = imagem_cv2_para_data_url_jpeg(imagem, qualidade=82)
    if not data_url:
        out["motivo"] = "imagem_invalida"
        return out
    print(f"[OPENAI VISION][P{out['pagina']}] layout_detectado={layout_in}")
    print(f"[OPENAI VISION][P{out['pagina']}] enviando input_image=True")
    print(f"[OPENAI VISION][P{out['pagina']}] tamanho_data_url={len(data_url)}")

    nomes_txt = ""
    if nomes_esperados:
        nomes_txt = "\nA lista de nomes esperados é:\n" + json.dumps(nomes_esperados, ensure_ascii=False)

    if out["tipo_pagina"] == "frente":
        prompt = aplicar_politica_prompt(f"""
Você está analisando uma página inteira de cartão ponto ou folha de ponto.
Layout sugerido: {layout_in or "desconhecido"}.
Tarefas:
1. Identifique o layout da página.
2. Extraia nome SOMENTE se houver campo claro: NOME, EMPREGADO, FUNCIONÁRIO/FUNCIONARIO/FUNCION., COLABORADOR, Dados do Colaborador, Assinatura de.
3. Não use como nome: razão social/empregador/empresa/função/cargo/CPF/CNPJ/CTPS/mês/ano/horários/rodapé/tabela.
4. Se for verso/2ª quinzena, não extraia nome.
5. Se for log de assinatura digital, extraia após "Assinatura de:".
6. Retorne competência, marcações e assinatura quando possível.
Responda somente JSON válido:
{{
  "layout": "",
  "nome": "",
  "nome_encontrado": false,
  "competencia": "",
  "marcacoes_encontradas": false,
  "assinatura": false,
  "assinatura_tipo": "ausente",
  "confianca": 0.0,
  "motivo": "",
  "avisos": []
}}
Se não conseguir ler com segurança, retorne nome vazio.{nomes_txt}
Regras obrigatórias para nome:
- deve ter entre 2 e 6 palavras;
- não pode ter números;
- não pode conter termos de empresa/cabeçalho/rodapé;
- se houver dúvida, ruído ou baixa legibilidade, retorne nome vazio e nome_encontrado=false;
- confianca deve ser baixa (<0.78) quando o nome estiver duvidoso.
Competência esperada: {competencia_esperada or "não informada"}.
""")
    else:
        prompt = aplicar_politica_prompt("""
Você está analisando uma página inteira de cartão ponto ou folha de ponto.
Esta página tende a ser VERSO/2ª QUINZENA ou complemento de assinatura.
Tarefas:
1. Não extraia nome do colaborador, exceto se for claramente "Assinatura de:" em log digital.
2. Identifique assinatura/rubrica no rodapé (recebimento/assinatura do empregado/ocorrências).
3. Informe se há marcações preenchidas.
Responda somente JSON válido:
{
  "layout": "",
  "nome": "",
  "nome_encontrado": false,
  "competencia": "",
  "marcacoes_encontradas": false,
  "assinatura": false,
  "assinatura_tipo": "ausente",
  "confianca": 0.0,
  "motivo": "",
  "avisos": []
}
""")

    content = [
        {"type": "input_text", "text": prompt},
        {"type": "input_image", "image_url": data_url},
    ]
    payload, erro = _post_openai_response(
        content,
        model=os.getenv("OPENAI_MODEL_CARTAO_PONTO", "gpt-4.1-mini-2025-04-14"),
        temperature=0,
    )
    if erro or not payload:
        out["motivo"] = erro or "falha_openai"
        return out
    txt = _extrair_texto_resposta_openai(payload)
    try:
        dados = json.loads(_limpar_json(txt)) if txt else {}
    except Exception:
        dados = {}
    print(f"[OPENAI VISION][P{out['pagina']}] resposta_bruta={txt[:800] if txt else ''}")
    if isinstance(dados, dict):
        out["layout"] = str(dados.get("layout") or out.get("layout") or "").strip().lower()
        out["nome"] = str(dados.get("nome") or "").strip()
        out["nome_encontrado"] = bool(dados.get("nome_encontrado")) and bool(out["nome"])
        out["competencia"] = str(dados.get("competencia") or "").strip()
        out["marcacoes_encontradas"] = bool(dados.get("marcacoes_encontradas"))
        out["assinatura"] = bool(dados.get("assinatura"))
        out["assinatura_tipo"] = str(dados.get("assinatura_tipo") or "ausente")
        out["confianca"] = float(dados.get("confianca") or 0.0)
        out["motivo"] = str(dados.get("motivo") or "")
        out["avisos"] = list(dados.get("avisos") or [])
    print(f"[OPENAI VISION][P{out['pagina']}] nome_retornado={out.get('nome')}")
    return out


def _render_pdf_para_data_urls(caminho_pdf, max_paginas=10, dpi=220):
    imgs = []
    with fitz.open(caminho_pdf) as doc:
        total = min(len(doc), max_paginas)
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        for i in range(total):
            page = doc[i]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            jpg = pix.tobytes("jpg")
            b64 = base64.b64encode(jpg).decode("ascii")
            imgs.append(f"data:image/jpeg;base64,{b64}")
    return imgs


def extrair_cartao_ponto_openai_pdf(caminho_pdf, competencia_esperada=None, perfil_leitura="auto"):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not caminho_pdf or (not os.path.exists(caminho_pdf)):
        return {"colaboradores": [], "motivo": "openai_indisponivel"}

    try:
        imagens = _render_pdf_para_data_urls(caminho_pdf, max_paginas=10, dpi=220)
        if not imagens:
            return {"colaboradores": [], "motivo": "sem_imagens"}

        prompt = (
            "Extraia os colaboradores de um cartão ponto. "
            "Retorne APENAS JSON válido no schema: "
            '{"colaboradores":[{"nome":"","competencia":"","assinatura":true,"marcacoes":true}]} . '
            "Não invente nomes. Ignore textos como LOCAL DO TRABALHO, FONTE, QUINZENA, SALDO, DESCONTOS. "
            f"Competência esperada: {competencia_esperada or 'não informada'}. "
            ""
        )

        content = [{"type": "input_text", "text": prompt}]
        for img in imagens:
            content.append({"type": "input_image", "image_url": img})

        modelos = [
            os.getenv("OPENAI_MODEL_CARTAO_PONTO", "gpt-4.1-mini-2025-04-14"),
            "gpt-4.1-mini-2025-04-14",
            "gpt-4.1-mini",
            "gpt-4.1",
        ]
        payload = None
        ultimo_erro = None
        for modelo in modelos:
            body = {
                "model": modelo,
                "temperature": 0,
                "input": [{"role": "user", "content": content}],
            }
            req = urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                payload = json.loads(raw)
                break
            except urllib.error.HTTPError as exc:
                detalhe = ""
                try:
                    detalhe = exc.read().decode("utf-8", errors="ignore")
                except Exception:
                    detalhe = str(exc)
                ultimo_erro = f"{exc.code}:{detalhe[:300]}"
                continue
        if payload is None:
            return {"colaboradores": [], "motivo": f"erro_openai: {ultimo_erro or 'falha_modelo'}"}
        txt = _extrair_texto_resposta_openai(payload)
        dados = json.loads(_limpar_json(txt)) if txt else {}
        cols = []
        for c in (dados.get("colaboradores") or []):
            nome = str(c.get("nome") or "").strip()
            if not nome:
                continue
            cols.append(
                {
                    "nome": nome,
                    "competencia": str(c.get("competencia") or competencia_esperada or "-").strip() or "-",
                    "assinatura": bool(c.get("assinatura")),
                    "marcacoes": bool(c.get("marcacoes")),
                    "marcacoes_encontradas": bool(c.get("marcacoes")),
                    "assinatura_tipo": "inconclusiva" if bool(c.get("assinatura")) else "ausente",
                    "assinatura_origem": "openai_fallback",
                    "assinatura_confianca": 0.7,
                    "paginas": [],
                    "motivos": [],
                    "avisos": ["Nome extraído via fallback OpenAI."],
                    "datado": True,
                }
            )
        return {"colaboradores": cols, "motivo": "ok"}
    except Exception as exc:
        return {"colaboradores": [], "motivo": f"erro_openai: {exc}"}
