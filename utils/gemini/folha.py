import json
import os
import re

import google.generativeai as genai

from utils.prompt_policy import aplicar_politica_prompt


genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = genai.GenerativeModel("gemini-1.5-flash")


PROMPT_FOLHA = """
Voce e um especialista em folha de pagamento brasileira.

Sua tarefa e extrair dados ESTRUTURADOS do texto.

IMPORTANTE:
- Retorne APENAS JSON valido
- NAO escreva explicacoes
- NAO escreva texto fora do JSON
- NAO invente dados

FORMATO OBRIGATORIO:

{
  "empresa": "string ou null",
  "competencia": "MM/AAAA ou null",
  "colaboradores": [
    {
      "nome": "string"
    }
  ]
}

REGRAS:

1. EMPRESA:
- Buscar razao social
- NAO retornar CNPJ como empresa

2. COMPETENCIA:
- Sempre formato MM/AAAA
- Priorizar linhas como "Folha Mensal", "Competencia", "Periodo" e nomes de mes com ano

3. COLABORADORES:
- Retornar apenas NOMES REAIS
- IGNORAR:
  - CNPJ
  - Endereco
  - Titulos (FOLHA, TOTAL, INSS, etc)
  - Linhas com numeros
  - Cargo, funcao, CBO e matricula como nome
- Priorizar rotulos como "Nome do Funcionario", "Funcionario", "Colaborador" e "Empregado"
- Se houver mais de um colaborador, retorne todos os nomes encontrados

TEXTO:
"""


def limpar_json(texto):
    if not texto:
        return {}

    texto = re.sub(r"```json|```", "", texto).strip()
    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if match:
        texto = match.group(0)

    try:
        return json.loads(texto)
    except Exception as e:
        print("JSON invalido:", e)
        return {}


def extrair_folha_inteligente(texto_ocr: str):
    if not texto_ocr or len(texto_ocr.strip()) < 30:
        return {}

    try:
        print("\n[ FOLHA ] Enviando para Gemini...")
        response = MODEL.generate_content(aplicar_politica_prompt(PROMPT_FOLHA + texto_ocr))
        texto_resposta = response.text or ""
        print("\n[ FOLHA ] Resposta bruta:")
        print(texto_resposta[:1000])

        dados = limpar_json(texto_resposta)
        if not isinstance(dados, dict):
            return {}

        dados.setdefault("empresa", None)
        dados.setdefault("competencia", None)
        dados.setdefault("colaboradores", [])
        print("\n[ FOLHA ] JSON FINAL OK")
        return dados
    except Exception as e:
        print(f"\nERRO GEMINI: {e}")
        return {}
