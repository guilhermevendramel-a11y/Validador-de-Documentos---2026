import json
import os
import re

import google.generativeai as genai
from dotenv import load_dotenv

from utils.prompt_policy import aplicar_politica_prompt


load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def limpar_json_resposta(texto):
    if not texto:
        return {}

    texto = re.sub(r"```json|```", "", texto).strip()
    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if match:
        texto = match.group(0)

    try:
        return json.loads(texto)
    except Exception as e:
        print(f"Aviso: erro ao converter JSON do Gemini: {e}")
        return {}


def modelos_disponiveis():
    preferidos = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ]

    try:
        disponiveis = [
            modelo.name.replace("models/", "")
            for modelo in genai.list_models()
            if "generateContent" in getattr(modelo, "supported_generation_methods", [])
        ]
        ordenados = [m for m in preferidos if m in disponiveis]
        ordenados.extend(m for m in disponiveis if m not in ordenados)
        return ordenados or preferidos
    except Exception as e:
        print(f"Aviso: nao foi possivel listar modelos Gemini: {e}")
        return preferidos


def chamar_gemini(prompt, generation_config=None):
    prompt = aplicar_politica_prompt(prompt)
    modelos = modelos_disponiveis()

    config = generation_config or {
        "temperature": 0.1,
        "response_mime_type": "application/json",
    }

    for modelo in modelos:
        try:
            print(f"Tentando modelo Gemini: {modelo}")
            model = genai.GenerativeModel(modelo)
            response = model.generate_content(prompt, generation_config=config)

            if response.text:
                print(f"Gemini respondeu com sucesso: {modelo}")
                return limpar_json_resposta(response.text)

        except Exception as e:
            print(f"Falha no modelo {modelo}: {e}")

    return {"erro": "Nenhum modelo respondeu corretamente"}


def normalizar_valor(valor):
    try:
        if isinstance(valor, str):
            valor = valor.replace(".", "").replace(",", ".")
        return round(float(valor), 2)
    except Exception:
        return 0.0


def extrair_salarios_liquidos(texto):
    texto = texto.upper()

    padroes = [
        r"L[ÍI]QUIDO\s*R?\$?\s*([\d\.,]+)",
        r"TOTAL\s+L[ÍI]QUIDO\s*R?\$?\s*([\d\.,]+)",
    ]

    valores = []
    for padrao in padroes:
        matches = re.findall(padrao, texto)
        for match in matches:
            valor = normalizar_valor(match)
            if 100 < valor < 50000:
                valores.append(valor)

    return list(dict.fromkeys(valores))
