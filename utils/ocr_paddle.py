import os
import re
from typing import Any

import cv2
import numpy as np

_PADDLE_READERS = {}

os.environ.setdefault("FLAGS_use_onednn", "false")
os.environ.setdefault("FLAGS_use_mkldnn", "false")


def _precarregar_torch_runtime():
    try:
        import torch  # noqa: F401
    except Exception:
        pass


def _qualidade_texto(txt: str) -> float:
    if not txt:
        return 0.0
    n = len(txt)
    uteis = sum(ch.isalnum() for ch in txt)
    return round(min(1.0, (uteis / max(1, n)) * min(1.0, n / 800.0)), 4)


def paddle_disponivel() -> bool:
    try:
        _precarregar_torch_runtime()
        from paddleocr import PaddleOCR  # noqa: F401
        return True
    except Exception:
        return False


def _to_bgr(imagem: Any):
    arr = np.array(imagem)
    if len(arr.shape) == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    if arr.shape[2] == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    return arr


def executar_paddleocr_imagem(imagem, lang="pt"):
    if not paddle_disponivel():
        return {"texto": "", "linhas": [], "metodo": "paddleocr_indisponivel", "qualidade": 0.0}
    try:
        _precarregar_torch_runtime()
        from paddleocr import PaddleOCR

        if lang not in _PADDLE_READERS:
            try:
                _PADDLE_READERS[lang] = PaddleOCR(
                    lang=lang,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            except TypeError:
                _PADDLE_READERS[lang] = PaddleOCR(use_angle_cls=True, lang=lang)
        ocr = _PADDLE_READERS[lang]
        img = _to_bgr(imagem)
        try:
            raw = ocr.predict(img)
        except AttributeError:
            raw = ocr.ocr(img, cls=True)
        linhas = []
        textos = []
        for bloco in raw or []:
            if isinstance(bloco, dict):
                rec_texts = bloco.get("rec_texts") or []
                rec_scores = bloco.get("rec_scores") or []
                rec_boxes = bloco.get("rec_boxes")
                rec_polys = bloco.get("rec_polys")
                if rec_polys is None:
                    rec_polys = bloco.get("dt_polys")
                rec_boxes = rec_boxes if rec_boxes is not None else []
                rec_polys = rec_polys if rec_polys is not None else []
                for idx, txt in enumerate(rec_texts):
                    pts = rec_boxes[idx] if idx < len(rec_boxes) else (rec_polys[idx] if idx < len(rec_polys) else [])
                    arr_pts = np.array(pts).reshape(-1, 2) if len(pts) else np.array([])
                    if arr_pts.size:
                        xs, ys = arr_pts[:, 0], arr_pts[:, 1]
                        bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
                    else:
                        bbox = [0, 0, 0, 0]
                    conf = float(rec_scores[idx]) if idx < len(rec_scores) else 0.0
                    linhas.append({"texto": txt, "confianca": round(conf, 4), "bbox": bbox})
                    textos.append(txt)
                continue
            for item in bloco or []:
                pts, payload = item
                txt, conf = payload[0], float(payload[1])
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                bbox = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
                linhas.append({"texto": txt, "confianca": round(conf, 4), "bbox": bbox})
                textos.append(txt)
        texto = "\n".join(textos).strip()
        return {"texto": texto, "linhas": linhas, "metodo": "paddleocr", "qualidade": _qualidade_texto(texto)}
    except Exception:
        return {"texto": "", "linhas": [], "metodo": "paddleocr_falha", "qualidade": 0.0}


def executar_paddleocr_regiao(imagem, bbox, lang="pt"):
    x1, y1, x2, y2 = [int(v) for v in bbox]
    img = _to_bgr(imagem)
    h, w = img.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return {"texto": "", "linhas": [], "metodo": "paddleocr", "qualidade": 0.0}
    return executar_paddleocr_imagem(img[y1:y2, x1:x2], lang=lang)
