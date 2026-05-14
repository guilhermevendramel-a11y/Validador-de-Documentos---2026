import json
import re
from utils.gemini_service import chamar_gemini


def extrair_fgts(texto):
    if not texto or len(texto.strip()) < 10:
        return {}

    prompt = f"""
Você é especialista em auditoria de FGTS Digital.

Analise o texto OCR abaixo.

O documento pode ser:
1. Relatório de trabalhadores
2. Guia FGTS / comprovante de pagamento

TAREFAS:

1. IDENTIFICAR EMPRESA
2. IDENTIFICAR CNPJ ou CNO
3. IDENTIFICAR COMPETÊNCIA (MM/AAAA)

4. IDENTIFICAR TOMADORES:
- Extraia cada CNPJ/CNO de tomador
- Para cada tomador, liste os colaboradores vinculados
- Para cada colaborador, extraia o valor FGTS se existir

5. VALORES:
- Se for RELATÓRIO:
  → extrair valores por colaborador
- Se for GUIA:
  → extrair valor total pago
  → extrair data de pagamento (se existir)

6. DOCUMENTOS PRESENTES:
Verifique se existem:
- Relação de Trabalhadores
- Relação de Categorias
- Relação de Estabelecimentos
- Relação de Tipos de Valor
- Relação de Tomadores

⚠️ REGRAS IMPORTANTES:
- Corrija erros de OCR automaticamente
- NÃO invente dados
- Retorne apenas JSON válido

SAÍDA:
{{
  "empresa": "",
  "cnpj_ou_cno": "",
  "competencia": "",
  "valor_total": 0,
  "data_pagamento": "",

  "tomadores": [
    {{
      "cnpj_ou_cno": "",
      "colaboradores": [
        {{
          "nome": "",
          "valor": 0
        }}
      ]
    }}
  ],

  "documentos_detectados": {{
    "relacao_trabalhadores": false,
    "relacao_categorias": false,
    "relacao_estabelecimentos": false,
    "relacao_tipo_valor": false,
    "relacao_tomadores": false
  }}
}}

TEXTO OCR:
{texto}
"""

    try:
        resposta = chamar_gemini(prompt)

        print("🧠 FGTS RAW:", resposta)

        # 🔥 Se já vier dict
        if isinstance(resposta, dict):
            return normalizar_saida(resposta)

        # 🔥 Se vier string
        if isinstance(resposta, str):
            resposta = limpar_json(resposta)
            dados = json.loads(resposta)
            return normalizar_saida(dados)

        return {}

    except Exception as e:
        print("❌ ERRO FGTS:", e)
        return {}


# 🔥 NOVO: normalização (SUPER IMPORTANTE)
def normalizar_saida(dados):
    if not isinstance(dados, dict):
        return {}

    dados.setdefault("empresa", "")
    dados.setdefault("cnpj_ou_cno", "")
    dados.setdefault("competencia", "")
    dados.setdefault("valor_total", 0)
    dados.setdefault("data_pagamento", "")
    dados.setdefault("tomadores", [])
    dados.setdefault("documentos_detectados", {})

    # 🔥 Garantir estrutura de tomadores
    tomadores_validos = []

    for t in dados.get("tomadores", []):
        if not isinstance(t, dict):
            continue

        colaboradores_validos = []

        for c in t.get("colaboradores", []):
            if not isinstance(c, dict):
                continue

            colaboradores_validos.append({
                "nome": c.get("nome", ""),
                "valor": float(c.get("valor", 0) or 0)
            })

        tomadores_validos.append({
            "cnpj_ou_cno": t.get("cnpj_ou_cno", ""),
            "colaboradores": colaboradores_validos
        })

    dados["tomadores"] = tomadores_validos

    # 🔥 garantir documentos
    docs = dados.get("documentos_detectados", {})
    dados["documentos_detectados"] = {
        "relacao_trabalhadores": docs.get("relacao_trabalhadores", False),
        "relacao_categorias": docs.get("relacao_categorias", False),
        "relacao_estabelecimentos": docs.get("relacao_estabelecimentos", False),
        "relacao_tipo_valor": docs.get("relacao_tipo_valor", False),
        "relacao_tomadores": docs.get("relacao_tomadores", False),
    }

    return dados


def limpar_json(texto):
    texto = texto.strip()
    texto = re.sub(r"```json|```", "", texto)

    inicio = texto.find("{")
    fim = texto.rfind("}")

    if inicio != -1 and fim != -1:
        texto = texto[inicio:fim + 1]

    return texto