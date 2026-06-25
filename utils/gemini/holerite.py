import os
import json
import re
import google.generativeai as genai

from utils.prompt_policy import aplicar_politica_prompt

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = genai.GenerativeModel("gemini-1.5-flash")

PROMPT = """
Extraia do holerite:

{
  "nome": "string",
  "cpf": "string",
  "competencia": "MM/AAAA",
  "liquido": "float"
}

Retorne SOMENTE JSON
"""


def extrair_holerite_inteligente(texto):

    if not texto:
        return {}

    try:
        response = MODEL.generate_content(aplicar_politica_prompt(PROMPT + "\n\n" + texto))
        txt = response.text.strip()

        txt = re.sub(r"```json|```", "", txt).strip()

        return json.loads(txt)

    except Exception as e:
        print("❌ Gemini erro:", e)
        return {}
