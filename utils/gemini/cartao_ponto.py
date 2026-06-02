import json
import os
import re

import google.generativeai as genai
import numpy as np
from PIL import Image

from utils.gemini_service import chamar_gemini, modelos_disponiveis


SYSTEM_PROMPT_CARTAO_PONTO = """
Voce e um especialista em Processamento de Linguagem Natural, Visao Computacional e auditoria de documentos de RH.

Objetivo:
Extrair registros de cartao ponto de qualquer layout, incluindo PDF digital, PDF escaneado, imagem, TXT, CSV ou planilha convertida em texto.

Contrato obrigatorio:
Retorne somente JSON valido, sem markdown, sem explicacoes e sem texto fora do JSON.

Schema obrigatorio:
{
  "status": "Processado|Revisar|Erro",
  "metodo_extracao": "Processamento Logico|OCR Tradicional|Inferencia de IA",
  "confianca_leitura": 0,
  "colaboradores": [
    {
      "nome_funcionario": "",
      "competencia": "MM/AAAA",
      "confianca_leitura": 0,
      "assinatura": {
        "presente": false,
        "tipo": "assinatura|rubrica|marca_manual|ausente",
        "confianca": 0,
        "revisao_humana": false
      },
      "registros": [
        {
          "data": "DD/MM/AAAA",
          "batidas": [
            {
              "tipo": "entrada|saida_intervalo|retorno_intervalo|saida|batida_1|batida_2|batida_3|batida_4",
              "horario": "HH:MM",
              "confianca": 0,
              "revisao_humana": false
            }
          ],
          "status_validacao": "OK|Revisar|Incompleto",
          "observacoes": []
        }
      ],
      "status_validacao": "OK|Revisar|Incompleto"
    }
  ],
  "observacoes": []
}

Mapeamento universal:
- Identifique Data, Entrada, Saida, Intervalo, Retorno de intervalo e Saida final independentemente do nome da coluna, ordem, idioma, abreviacao ou posicao visual.
- Considere sinonimos como: Data, Dia, Dt; Entrada, Ent, Entrada 1, 1a Entrada, ENT1; Saida, Sai, Saida 1, 1a Saida, SAI1; Entrada 2, Retorno, ENT2; Saida 2, SAI2.
- Horarios devem ser normalizados para HH:MM.
- Datas devem ser normalizadas para DD/MM/AAAA.
- Competencia deve ser MM/AAAA quando puder ser inferida por periodo, cabecalho ou maioria das datas.

Assinatura e rubrica:
- Verifique assinatura, rubrica, iniciais, risco manual ou marca manuscrita no campo de assinatura/recebimento.
- Associe a assinatura ao colaborador correto usando proximidade visual, nome impresso na mesma pagina, bloco do funcionario ou pagina imediatamente vinculada ao funcionario.
- Nao marque assinatura de um colaborador usando rubrica de outro colaborador.
- Se houver rubrica pequena, assinatura abreviada ou apenas iniciais manuscritas, use tipo "rubrica".
- Se houver risco manual evidente, mas sem formato claro de assinatura, use tipo "marca_manual".
- Se a evidencia visual for fraca, use presente false ou revisao_humana true com confianca abaixo de 70.

Tratamento de incerteza:
- Nunca invente nome, data ou horario.
- Se houver duvida sobre um horario, mantenha o valor mais provavel, reduza "confianca" e marque "revisao_humana": true.
- Se um horario estiver ilegivel, use horario vazio, confianca baixa e revisao_humana true.
- Use confianca_leitura entre 0 e 100 para o documento e por colaborador.

Validacao:
- Um dia com pelo menos duas batidas validas pode ser OK.
- Um dia com uma ou nenhuma batida deve ser Revisar ou Incompleto.
- Se houver varias pessoas no arquivo, retorne todas em colaboradores.
"""


def limpar_json(texto):
    texto = (texto or "").strip()
    texto = re.sub(r"```json|```", "", texto)
    inicio = texto.find("{")
    fim = texto.rfind("}")

    if inicio != -1 and fim != -1:
        texto = texto[inicio:fim + 1]

    return texto.strip()


def extrair_cartao_ponto(texto):
    if not texto or len(texto.strip()) < 10:
        print("Texto OCR muito curto ou vazio para processar no Gemini.")
        return {"colaboradores": []}

    prompt = f"{SYSTEM_PROMPT_CARTAO_PONTO}\n\nTEXTO OCR:\n{texto}"

    try:
        resposta_bruta = chamar_gemini(prompt)

        if isinstance(resposta_bruta, dict):
            dados = resposta_bruta
        elif isinstance(resposta_bruta, str):
            dados = json.loads(limpar_json(resposta_bruta))
        else:
            return {"colaboradores": []}

        if not isinstance(dados, dict) or "colaboradores" not in dados:
            return {"colaboradores": []}

        return normalizar_resposta_cartao_ponto(dados)

    except Exception as e:
        print("Erro Gemini cartao ponto:", e)
        return {"colaboradores": []}


def extrair_cartao_ponto_pdf(caminho_pdf):
    if not caminho_pdf or not os.path.exists(caminho_pdf):
        return {"colaboradores": []}

    try:
        arquivo = genai.upload_file(caminho_pdf, mime_type="application/pdf")
        modelo = modelos_disponiveis()[0]
        model = genai.GenerativeModel(modelo)
        response = model.generate_content(
            [SYSTEM_PROMPT_CARTAO_PONTO, arquivo],
            generation_config={"temperature": 0.05},
        )

        dados = json.loads(limpar_json(response.text))
        if isinstance(dados, dict) and isinstance(dados.get("colaboradores"), list):
            return normalizar_resposta_cartao_ponto(dados)

    except Exception as e:
        print("Erro Gemini PDF cartao ponto:", e)

    return {"colaboradores": []}


def normalizar_resposta_cartao_ponto(dados):
    colaboradores_normalizados = []

    for c in dados.get("colaboradores", []):
        assinatura_raw = c.get("assinatura", "")
        if isinstance(assinatura_raw, dict):
            assinatura_ok = bool(assinatura_raw.get("presente"))
        else:
            assinatura_str = str(assinatura_raw).lower()
            assinatura_ok = (
                assinatura_str in ["true", "sim", "ok"]
                or assinatura_raw is True
                or c.get("status_assinatura") is True
                or c.get("assinatura_presente") is True
            )

        registros = c.get("registros") or []
        marcacoes = c.get("marcacoes")
        if marcacoes is None:
            marcacoes = any((r.get("batidas") or []) for r in registros if isinstance(r, dict))

        colaboradores_normalizados.append({
            "nome": c.get("nome") or c.get("nome_corrigido") or c.get("nome_funcionario") or "",
            "competencia": c.get("competencia") or "",
            "assinatura": assinatura_ok,
            "datado": bool(c.get("datado", False) or registros),
            "marcacoes": bool(marcacoes),
            "metodo_extracao": c.get("metodo_extracao") or dados.get("metodo_extracao") or "Inferencia de IA",
            "confianca_leitura": c.get("confianca_leitura") or dados.get("confianca_leitura") or 0,
        })

    return {
        "colaboradores": colaboradores_normalizados,
        "metodo_extracao": dados.get("metodo_extracao") or "Inferencia de IA",
        "confianca_leitura": dados.get("confianca_leitura") or 0,
    }


def _imagem_para_pil(imagem):
    if imagem is None:
        return None
    arr = np.array(imagem)
    if arr.size == 0:
        return None
    if len(arr.shape) == 2:
        return Image.fromarray(arr)
    # BGR -> RGB
    return Image.fromarray(arr[:, :, ::-1])


def extrair_cartao_ponto_por_regiao_gemini(recortes, campos_pendentes):
    campos_pendentes = [str(c).strip().lower() for c in (campos_pendentes or []) if str(c).strip()]
    recortes = recortes or {}
    resposta_vazia = {
        "nome": "",
        "nome_encontrado": False,
        "competencia": "",
        "periodo_inicio": "",
        "periodo_fim": "",
        "marcacoes_encontradas": False,
        "assinatura": False,
        "assinatura_tipo": "inconclusiva",
        "assinatura_local": "desconhecido",
        "confianca": 0.0,
        "motivos": [],
        "avisos": [],
    }
    if not campos_pendentes:
        return dict(resposta_vazia)

    imagens_alvo = []
    if any(c in campos_pendentes for c in ["nome", "competencia"]):
        for k in ["topo", "cabecalho_esquerdo"]:
            img = _imagem_para_pil(recortes.get(k))
            if img is not None:
                imagens_alvo.append((k, img))
    if "marcacoes" in campos_pendentes:
        img = _imagem_para_pil(recortes.get("tabela"))
        if img is not None:
            imagens_alvo.append(("tabela", img))
    if "assinatura" in campos_pendentes:
        for k in ["coluna_assinatura", "rodape"]:
            img = _imagem_para_pil(recortes.get(k))
            if img is not None:
                imagens_alvo.append((k, img))
    if not imagens_alvo:
        img = _imagem_para_pil(recortes.get("total"))
        if img is not None:
            imagens_alvo.append(("total", img))

    if not imagens_alvo:
        out = dict(resposta_vazia)
        out["motivos"] = ["Sem recortes válidos para fallback IA."]
        return out

    prompt = f"""
Retorne somente JSON valido, sem markdown.
Objetivo: preencher somente os campos pendentes do cartao ponto.
Campos pendentes: {", ".join(campos_pendentes)}

Schema obrigatorio:
{{
  "nome": "",
  "nome_encontrado": true,
  "competencia": "",
  "periodo_inicio": "",
  "periodo_fim": "",
  "marcacoes_encontradas": true,
  "assinatura": true,
  "assinatura_tipo": "rubrica | assinatura_manual | assinatura_digital | ausente | inconclusiva",
  "assinatura_local": "rodape | coluna_assinatura | desconhecido",
  "confianca": 0.0,
  "motivos": [],
  "avisos": []
}}
"""
    try:
        model = genai.GenerativeModel(modelos_disponiveis()[0])
        payload = [prompt] + [img for _k, img in imagens_alvo]
        response = model.generate_content(payload, generation_config={"temperature": 0.05})
        raw = limpar_json(getattr(response, "text", "") or "")
        dados = json.loads(raw) if raw else {}
        if not isinstance(dados, dict):
            return dict(resposta_vazia)
        out = dict(resposta_vazia)
        out.update({k: dados.get(k, out.get(k)) for k in out.keys()})
        out["confianca"] = float(out.get("confianca") or 0.0)
        out["nome_encontrado"] = bool(out.get("nome_encontrado"))
        out["marcacoes_encontradas"] = bool(out.get("marcacoes_encontradas"))
        out["assinatura"] = bool(out.get("assinatura"))
        out["motivos"] = list(out.get("motivos") or [])
        out["avisos"] = list(out.get("avisos") or [])
        return out
    except Exception as exc:
        print("Erro Gemini por regiao cartao ponto:", exc)
        out = dict(resposta_vazia)
        out["motivos"] = [f"Falha IA por região: {exc}"]
        return out
