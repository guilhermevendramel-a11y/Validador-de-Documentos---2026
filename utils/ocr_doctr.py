from typing import Any

import cv2
import numpy as np


_DOCTR_MODEL = None


def _qualidade_texto(txt: str) -> float:
    if not txt:
        return 0.0
    n = len(txt)
    uteis = sum(ch.isalnum() for ch in txt)
    return round(min(1.0, (uteis / max(1, n)) * min(1.0, n / 800.0)), 4)


def doctr_disponivel() -> bool:
    try:
        from doctr.models import ocr_predictor  # noqa: F401
        return True
    except Exception:
        return False


def _to_rgb(imagem: Any):
    arr = np.array(imagem)
    if len(arr.shape) == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
    if arr.shape[2] == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def _bbox_abs(geometry, width, height):
    try:
        (x1, y1), (x2, y2) = geometry
        return [int(x1 * width), int(y1 * height), int(x2 * width), int(y2 * height)]
    except Exception:
        return [0, 0, 0, 0]


def executar_doctr_imagem(imagem):
    if not doctr_disponivel():
        return {"texto": "", "linhas": [], "metodo": "doctr_indisponivel", "qualidade": 0.0}
    try:
        from doctr.models import ocr_predictor

        global _DOCTR_MODEL
        if _DOCTR_MODEL is None:
            _DOCTR_MODEL = ocr_predictor(pretrained=True)
        img = _to_rgb(imagem)
        h, w = img.shape[:2]
        result = _DOCTR_MODEL([img])
        data = result.export()
        linhas = []
        textos = []
        for page in data.get("pages", []):
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    words = line.get("words", [])
                    texto_linha = " ".join(str(word.get("value", "")).strip() for word in words).strip()
                    if not texto_linha:
                        continue
                    confs = [float(word.get("confidence", 0.0) or 0.0) for word in words]
                    bbox = _bbox_abs(line.get("geometry"), w, h)
                    linhas.append({
                        "texto": texto_linha,
                        "confianca": round(sum(confs) / max(1, len(confs)), 4),
                        "bbox": bbox,
                    })
                    textos.append(texto_linha)
        texto = "\n".join(textos).strip()
        return {"texto": texto, "linhas": linhas, "metodo": "doctr", "qualidade": _qualidade_texto(texto)}
    except Exception as exc:
        return {"texto": "", "linhas": [], "metodo": "doctr_falha", "qualidade": 0.0, "erro": str(exc)}
