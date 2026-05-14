import os
from functools import lru_cache

import fitz
import numpy as np


DEFAULT_MODEL_PATH = os.path.join(os.getcwd(), "models", "assinatura_yolo.pt")


def caminho_modelo_yolo():
    return os.getenv("YOLO_SIGNATURE_MODEL") or DEFAULT_MODEL_PATH


def yolo_disponivel():
    return os.path.exists(caminho_modelo_yolo())


@lru_cache(maxsize=1)
def _carregar_modelo():
    from ultralytics import YOLO

    return YOLO(caminho_modelo_yolo())


def _prever_pagina(modelo, pix, conf):
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        arr = arr[:, :, :3]
    return modelo.predict(source=arr, conf=conf, verbose=False)


def detectar_assinaturas_yolo(caminho_pdf, conf=0.25, dpi=200):
    if not yolo_disponivel():
        return []

    try:
        modelo = _carregar_modelo()
    except Exception as exc:
        print(f"[YOLO] Modelo de assinatura indisponivel: {exc}")
        return []

    deteccoes = []

    try:
        with fitz.open(caminho_pdf) as doc:
            zoom = dpi / 72
            matriz = fitz.Matrix(zoom, zoom)

            for pagina_idx, pagina in enumerate(doc):
                pix = pagina.get_pixmap(matrix=matriz, alpha=False)
                # Fallback progressivo: reduz limiar caso assinatura esteja fraca no scan.
                tentativas_conf = [conf, 0.18, 0.12, 0.08]
                resultados = []
                for conf_atual in tentativas_conf:
                    resultados = _prever_pagina(modelo, pix, conf_atual)
                    if any(len(resultado.boxes) for resultado in resultados):
                        break

                for resultado in resultados:
                    for box in resultado.boxes:
                        score = float(box.conf[0])
                        cls = int(box.cls[0]) if box.cls is not None else 0
                        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
                        deteccoes.append(
                            {
                                "pagina": pagina_idx + 1,
                                "classe": cls,
                                "confianca": round(score, 4),
                                "bbox": [x1, y1, x2, y2],
                            }
                        )
    except Exception as exc:
        print(f"[YOLO] Erro ao detectar assinatura: {exc}")

    return deteccoes


def detectar_assinatura_yolo_global(caminho_pdf, conf=0.25):
    return bool(detectar_assinaturas_yolo(caminho_pdf, conf=conf))


def detectar_assinaturas_yolo_por_colaborador(caminho_pdf, nomes, conf=0.25, deteccoes=None):
    from utils.signature_detection import normalizar_nome, pagina_pertence_ao_colaborador

    resultado = {
        nome: {"assinatura": False, "confianca": 0, "paginas": [], "origem": "yolo"}
        for nome in nomes
        if nome
    }

    deteccoes = deteccoes if deteccoes is not None else detectar_assinaturas_yolo(caminho_pdf, conf=conf)
    if not deteccoes or not resultado:
        return resultado

    try:
        with fitz.open(caminho_pdf) as doc:
            textos = [normalizar_nome(pagina.get_text() or "") for pagina in doc]
    except Exception as exc:
        print(f"[YOLO] Erro ao ler paginas para vincular colaborador: {exc}")
        return resultado

    paginas_por_nome = {}
    for nome in resultado:
        nome_norm = normalizar_nome(nome)
        paginas = set()
        for idx, texto in enumerate(textos):
            if pagina_pertence_ao_colaborador(texto, nome_norm):
                paginas.add(idx + 1)
                if idx + 2 <= len(textos):
                    paginas.add(idx + 2)
        paginas_por_nome[nome] = paginas

    for deteccao in deteccoes:
        pagina = deteccao["pagina"]
        for nome, paginas in paginas_por_nome.items():
            if pagina in paginas:
                resultado[nome]["assinatura"] = True
                resultado[nome]["confianca"] = max(resultado[nome]["confianca"], deteccao["confianca"])
                if pagina not in resultado[nome]["paginas"]:
                    resultado[nome]["paginas"].append(pagina)

    return resultado
