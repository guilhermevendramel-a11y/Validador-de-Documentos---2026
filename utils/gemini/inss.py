import json
import re
from utils.gemini_service import chamar_gemini

def extrair_inss_inteligente(texto):
    if not texto or len(texto.strip()) < 10:
        return {}

    prompt = f"""
Você é especialista em auditoria previdenciária (INSS/DCTFWeb).
Analise o texto OCR de uma Guia DARF ou Relatório DCTFWeb abaixo.

TAREFAS:
1. IDENTIFICAR EMPRESA: Nome da Razão Social e CNPJ principal.
2. COMPETÊNCIA: Localize o "Período de Apuração" ou "Competência". 
   - IMPORTANTE: Converta meses por extenso para numeral (Ex: "Outubro/2025" vira "10/2025").
3. VALORES:
   - Extrair o "Valor Total do Documento" (se for Guia/DARF).
   - Extrair o "Valor Total do Débito" (se for Relatório DCTFWeb).
   - Identificar data de pagamento e valor pago (se houver comprovante anexo).

4. TOMADORES DE SERVIÇO / ESTABELECIMENTOS:
   - Procure por seções de tomadores (CNPJ/CNO) ou estabelecimentos.
   - Liste os trabalhadores vinculados a cada tomador e seus respectivos valores de contribuição.

5. ESTRUTURA DCTFWEB:
   - Verifique a presença das seções: "Débitos Apurados", "Créditos Vinculados" e "Saldo a Pagar".

⚠️ REGRAS:
- Retorne APENAS o JSON.
- Se houver várias datas, a competência é sempre o "Período de Apuração".
- Converta valores para float (use ponto para decimais).

SAÍDA DESEJADA:
{{
  "empresa": "",
  "cnpj": "",
  "competencia": "MM/AAAA",
  "valor_guia": 0.0,
  "valor_dctf": 0.0,
  "data_pagamento": "",
  "valor_pago": 0.0,
  "tomadores": [
    {{
      "cnpj_ou_cno": "",
      "colaboradores": [
        {{ "nome": "", "valor": 0.0 }}
      ]
    }}
  ],
  "estrutura_detectada": {{
    "debitos_apurados": false,
    "creditos_vinculados": false,
    "saldo_a_pagar": false
  }}
}}

TEXTO OCR:
{texto}
"""

    try:
        resposta = chamar_gemini(prompt)
        print("🧠 INSS GEMINI RAW:", resposta)

        if isinstance(resposta, dict):
            return normalizar_saida_inss(resposta)

        if isinstance(resposta, str):
            resposta = limpar_json_inss(resposta)
            dados = json.loads(resposta)
            return normalizar_saida_inss(dados)

        return {}

    except Exception as e:
        print("❌ ERRO INSS GEMINI:", e)
        return {}

def normalizar_saida_inss(dados):
    if not isinstance(dados, dict):
        return {}

    # Garantias de chaves básicas
    dados.setdefault("empresa", "")
    dados.setdefault("cnpj", "")
    dados.setdefault("competencia", "")
    dados.setdefault("valor_guia", 0.0)
    dados.setdefault("valor_dctf", 0.0)
    dados.setdefault("data_pagamento", "")
    dados.setdefault("valor_pago", 0.0)
    dados.setdefault("tomadores", [])
    
    # Normalizar Tomadores
    tomadores_limpos = []
    for t in dados.get("tomadores", []):
        colaboradores = []
        for c in t.get("colaboradores", []):
            colaboradores.append({
                "nome": str(c.get("nome", "")).upper(),
                "valor": float(c.get("valor", 0) or 0)
            })
        tomadores_limpos.append({
            "cnpj_ou_cno": t.get("cnpj_ou_cno", ""),
            "colaboradores": colaboradores
        })
    dados["tomadores"] = tomadores_limpos

    # Normalizar Estrutura
    est = dados.get("estrutura_detectada", {})
    dados["estrutura_detectada"] = {
        "debitos_apurados": est.get("debitos_apurados", False),
        "creditos_vinculados": est.get("creditos_vinculados", False),
        "saldo_a_pagar": est.get("saldo_a_pagar", False)
    }

    return dados

def limpar_json_inss(texto):
    texto = texto.strip()
    texto = re.sub(r"```json|```", "", texto)
    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio != -1 and fim != -1:
        texto = texto[inicio:fim + 1]
    return texto