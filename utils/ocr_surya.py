from typing import Any

import cv2
import numpy as np
from PIL import Image


_SURYA_PREDICTORS = None


def _qualidade_texto(txt: str) -> float:
    if not txt:
        return 0.0
    n = len(txt)
    uteis = sum(ch.isalnum() for ch in txt)
    return round(min(1.0, (uteis / max(1, n)) * min(1.0, n / 800.0)), 4)


def surya_disponivel() -> bool:
    try:
        from surya.detection import DetectionPredictor  # noqa: F401
        from surya.foundation import FoundationPredictor  # noqa: F401
        from surya.recognition import RecognitionPredictor  # noqa: F401
        return True
    except Exception:
        return False


def _to_pil_rgb(imagem: Any) -> Image.Image:
    arr = np.array(imagem)
    if len(arr.shape) == 2:
        arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
    elif arr.shape[2] == 4:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
    else:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(arr)


def _carregar_predictors():
    global _SURYA_PREDICTORS
    if _SURYA_PREDICTORS is None:
        from surya.detection import DetectionPredictor
        from surya.foundation import FoundationPredictor
        from surya.recognition import RecognitionPredictor

        foundation = FoundationPredictor()
        _SURYA_PREDICTORS = {
            "detection": DetectionPredictor(),
            "recognition": RecognitionPredictor(foundation),
        }
    return _SURYA_PREDICTORS


def executar_surya_ocr_imagem(imagem):
    if not surya_disponivel():
        return {"texto": "", "linhas": [], "metodo": "surya_indisponivel", "qualidade": 0.0}
    try:
        from surya.common.surya.schema import TaskNames

        pil_img = _to_pil_rgb(imagem)
        predictors = _carregar_predictors()
        preds = predictors["recognition"](
            [pil_img],
            task_names=[TaskNames.ocr_with_boxes],
            det_predictor=predictors["detection"],
            highres_images=[pil_img],
            math_mode=False,
        )
        linhas = []
        textos = []
        for line in (preds[0].text_lines if preds else []):
            txt = str(getattr(line, "text", "") or "").strip()
            if not txt:
                continue
            bbox = [int(v) for v in getattr(line, "bbox", [])] if getattr(line, "bbox", None) else [0, 0, 0, 0]
            conf = float(getattr(line, "confidence", 0.0) or 0.0)
            linhas.append({"texto": txt, "confianca": round(conf, 4), "bbox": bbox})
            textos.append(txt)
        texto = "\n".join(textos).strip()
        return {"texto": texto, "linhas": linhas, "metodo": "surya", "qualidade": _qualidade_texto(texto)}
    except Exception as exc:
        return {"texto": "", "linhas": [], "metodo": "surya_falha", "qualidade": 0.0, "erro": str(exc)}
