from typing import Any

import cv2
import numpy as np


_EASY_READERS = {}


def _qualidade_texto(txt: str) -> float:
    if not txt:
        return 0.0
    n = len(txt)
    uteis = sum(ch.isalnum() for ch in txt)
    return round(min(1.0, (uteis / max(1, n)) * min(1.0, n / 800.0)), 4)


def easyocr_disponivel() -> bool:
    try:
        import easyocr  # noqa: F401
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


def _normalizar_lang(lang):
    if not lang:
        return ("pt", "en")
    if isinstance(lang, str):
        return (lang,)
    return tuple(lang)


def executar_easyocr_imagem(imagem, lang=("pt", "en")):
    langs = _normalizar_lang(lang)
    if not easyocr_disponivel():
        return {"texto": "", "linhas": [], "metodo": "easyocr_indisponivel", "qualidade": 0.0}
    try:
        import easyocr

        if langs not in _EASY_READERS:
            _EASY_READERS[langs] = easyocr.Reader(list(langs), gpu=False)
        reader = _EASY_READERS[langs]
        raw = reader.readtext(_to_rgb(imagem), detail=1, paragraph=False)
        linhas = []
        textos = []
        for pts, txt, conf in raw or []:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            bbox = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
            txt = str(txt or "").strip()
            if not txt:
                continue
            linhas.append({"texto": txt, "confianca": round(float(conf or 0.0), 4), "bbox": bbox})
            textos.append(txt)
        texto = "\n".join(textos).strip()
        return {"texto": texto, "linhas": linhas, "metodo": "easyocr", "qualidade": _qualidade_texto(texto)}
    except Exception as exc:
        return {"texto": "", "linhas": [], "metodo": "easyocr_falha", "qualidade": 0.0, "erro": str(exc)}
