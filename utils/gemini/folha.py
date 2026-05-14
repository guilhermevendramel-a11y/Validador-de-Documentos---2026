import os
import json
import re
import google.generativeai as genai


# ============================================================
# CONFIG
# ============================================================
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = genai.GenerativeModel("gemini-1.5-flash")


# ============================================================
# PROMPT OTIMIZADO 🔥
# ============================================================
PROMPT_FOLHA = """
Você é um especialista em folha de pagamento brasileira.

Sua tarefa é extrair dados ESTRUTURADOS do texto.

⚠️ IMPORTANTE:
- Retorne APENAS JSON válido
- NÃO escreva explicações
- NÃO escreva texto fora do JSON
- NÃO invente dados

====================================================

FORMATO OBRIGATÓRIO:

{
  "empresa": "string ou null",
  "competencia": "MM/AAAA ou null",
  "valor_total_folha": number ou null,
  "colaboradores": [
    {
      "nome": "string",
      "cpf": "string ou null",
      "salario_base": number ou null,
      "descontos": number ou null,
      "liquido": number ou null
    }
  ]
}

====================================================

REGRAS:

1. EMPRESA:
- Buscar razão social
- NÃO retornar CNPJ como empresa

2. COMPETÊNCIA:
- Sempre formato MM/AAAA

3. COLABORADORES:
- Retornar apenas NOMES REAIS
- IGNORAR:
  - CNPJ
  - Endereço
  - Títulos (FOLHA, TOTAL, INSS, etc)
  - Linhas com números

4. VALORES:
- Converter para número (sem R$, sem vírgula)
- Se não encontrar → null

====================================================

TEXTO:
"""


# ============================================================
# LIMPEZA JSON (ROBUSTA 🔥)
# ============================================================
def limpar_json(texto):

    if not texto:
        return {}

    # remove markdown
    texto = re.sub(r"```json|```", "", texto).strip()

    # extrai JSON válido
    match = re.search(r"\{.*\}", texto, re.DOTALL)

    if match:
        texto = match.group(0)

    try:
        return json.loads(texto)
    except Exception as e:
        print("❌ JSON inválido:", e)
        return {}


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================
def extrair_folha_inteligente(texto_ocr: str):

    if not texto_ocr or len(texto_ocr.strip()) < 30:
        return {}

    try:
        print("\n🧠 [FOLHA] Enviando para Gemini...")

        response = MODEL.generate_content(
            PROMPT_FOLHA + texto_ocr
        )

        texto_resposta = response.text or ""

        print("\n📥 [FOLHA] Resposta bruta:")
        print(texto_resposta[:1000])

        dados = limpar_json(texto_resposta)

        # 🔥 PROTEÇÃO EXTRA
        if not isinstance(dados, dict):
            return {}

        # garante estrutura mínima
        dados.setdefault("empresa", None)
        dados.setdefault("competencia", None)
        dados.setdefault("valor_total_folha", None)
        dados.setdefault("colaboradores", [])

        print("\n✅ [FOLHA] JSON FINAL OK")

        return dados

    except Exception as e:
        print(f"\n❌ ERRO GEMINI: {e}")
        return {}