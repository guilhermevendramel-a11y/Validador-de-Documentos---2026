import os
import re
from functools import lru_cache
from pathlib import Path

import cv2
import fitz
import numpy as np
import pytesseract
import utils.tesseract_config  # noqa: F401

from utils.signature_detection import normalizar_nome, pagina_pertence_ao_colaborador

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = ROOT_DIR / "models" / "assinatura_yolo.pt"


def caminho_modelo_yolo():
    modelos = caminhos_modelos_yolo()
    return modelos[0] if modelos else DEFAULT_MODEL_PATH


def _coletar_modelos_por_env():
    bruto = os.getenv("YOLO_SIGNATURE_MODEL", "").strip()
    if not bruto:
        return []

    candidatos = []
    for parte in re.split(r"[;,]", bruto):
        parte = parte.strip()
        if not parte:
            continue
        p = Path(parte)
        if p.is_dir():
            candidatos.extend(sorted(p.rglob("*.pt")))
        else:
            candidatos.append(p)
    return candidatos


def _coletar_modelos_treinados_locais():
    candidatos = []

    pasta_modelos = ROOT_DIR / "models"
    if pasta_modelos.exists():
        candidatos.extend(sorted(pasta_modelos.glob("*.pt")))

    pasta_runs = ROOT_DIR / "runs" / "detect"
    if pasta_runs.exists():
        candidatos.extend(sorted(pasta_runs.glob("**/weights/best.pt")))
        candidatos.extend(sorted(pasta_runs.glob("**/weights/last.pt")))

    return candidatos


def caminhos_modelos_yolo():
    modelos = []
    vistos = set()

    for p in [*_coletar_modelos_por_env(), *_coletar_modelos_treinados_locais(), DEFAULT_MODEL_PATH]:
        try:
            p_norm = p.resolve()
        except Exception:
            p_norm = Path(p)
        chave = str(p_norm).lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        if p_norm.exists() and p_norm.suffix.lower() == ".pt":
            modelos.append(p_norm)

    return modelos


def yolo_disponivel():
    return len(caminhos_modelos_yolo()) > 0


@lru_cache(maxsize=16)
def _carregar_modelo(model_path):
    from ultralytics import YOLO

    return YOLO(str(model_path))


def classificar_zona_vertical(y1, y2, altura):
    if altura <= 0:
        return "indefinida"
    centro = (float(y1) + float(y2)) / 2.0
    ratio = centro / float(altura)
    if ratio < 0.33:
        return "topo"
    if ratio < 0.66:
        return "meio"
    return "rodape"


def renderizar_pdf_paginas(caminho_pdf, dpi=200):
    imagens = []
    zoom = dpi / 72.0
    with fitz.open(caminho_pdf) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
            imagens.append(arr)
    return imagens


def extrair_texto_pagina_com_fallback(page, imagem=None):
    texto = (page.get_text() or "").strip()
    if len(texto) >= 60:
        return texto

    if imagem is None:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        imagem = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

    if len(imagem.shape) == 3 and imagem.shape[2] == 4:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_RGBA2RGB)

    gray = cv2.cvtColor(imagem, cv2.COLOR_RGB2GRAY) if len(imagem.shape) == 3 else imagem
    adapt = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)

    txt1 = pytesseract.image_to_string(gray, lang="por", config="--oem 3 --psm 6")
    txt2 = pytesseract.image_to_string(adapt, lang="por", config="--oem 3 --psm 6")
    return txt2 if len(txt2) > len(txt1) else txt1


def calcular_distancia_boxes(box_a, box_b):
    if not box_a or not box_b:
        return 1e9

    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    acx, acy = (ax1 + ax2) / 2.0, (ay1 + ay2) / 2.0
    bcx, bcy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
    return float(((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5)


def detectar_nomes_com_ocr_data(imagem, nomes):
    resultado = {nome: [] for nome in nomes if nome}
    if not resultado:
        return resultado

    if len(imagem.shape) == 3 and imagem.shape[2] == 4:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_RGBA2RGB)
    gray = cv2.cvtColor(imagem, cv2.COLOR_RGB2GRAY) if len(imagem.shape) == 3 else imagem

    data = pytesseract.image_to_data(gray, lang="por", config="--oem 3 --psm 6", output_type=pytesseract.Output.DICT)
    tokens = []
    n = len(data.get("text", []))
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        conf = float(data.get("conf", ["-1"])[i] or -1)
        if conf < 25:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        tokens.append({
            "texto": normalizar_nome(txt),
            "bbox": [float(x), float(y), float(x + w), float(y + h)],
        })

    for nome in list(resultado.keys()):
        nome_norm = normalizar_nome(nome)
        partes = [p for p in nome_norm.split() if len(p) >= 3]
        for tk in tokens:
            if nome_norm in tk["texto"] or any(p in tk["texto"] for p in partes):
                resultado[nome].append(tk["bbox"])

    return resultado


def _normalizar_detect_box(box):
    x1, y1, x2, y2 = [float(v) for v in box]
    w = max(0.0, x2 - x1)
    h = max(0.0, y2 - y1)
    area = w * h
    centro = [x1 + w / 2.0, y1 + h / 2.0]
    return x1, y1, x2, y2, w, h, area, centro


def _iou(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0

    area_a = max(0.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(0.0, (bx2 - bx1) * (by2 - by1))
    union = area_a + area_b - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


def combinar_deteccoes_ensemble(deteccoes, iou_threshold=0.55):
    if not deteccoes:
        return []

    ordenadas = sorted(deteccoes, key=lambda d: float(d.get("confianca") or 0), reverse=True)
    combinadas = []

    for det in ordenadas:
        bbox = det.get("bbox")
        pagina = det.get("pagina")
        if not bbox:
            combinadas.append(det)
            continue

        duplicada = False
        for base in combinadas:
            if base.get("pagina") != pagina or not base.get("bbox"):
                continue
            if _iou(bbox, base.get("bbox")) >= iou_threshold:
                modelos = set(base.get("modelos") or [])
                modelos.update(det.get("modelos") or [])
                if not modelos and base.get("modelo"):
                    modelos.add(base.get("modelo"))
                if not modelos and det.get("modelo"):
                    modelos.add(det.get("modelo"))
                base["modelos"] = sorted(modelos)
                base["qtd_modelos"] = len(base["modelos"])
                base["confianca"] = max(float(base.get("confianca") or 0), float(det.get("confianca") or 0))
                duplicada = True
                break

        if not duplicada:
            novo = dict(det)
            if "modelos" not in novo:
                novo["modelos"] = [novo["modelo"]] if novo.get("modelo") else []
            novo["qtd_modelos"] = len(novo.get("modelos") or [])
            combinadas.append(novo)

    return combinadas


def detectar_assinaturas_yolo(caminho_pdf, conf=0.25, dpi=200, paginas_alvo=None):
    modelos_paths = caminhos_modelos_yolo()
    if not modelos_paths:
        print("[YOLO] Nenhum modelo treinado disponivel.")
        return []
    deteccoes = []

    try:
        imagens = renderizar_pdf_paginas(caminho_pdf, dpi=dpi)
        print(f"[YOLO] modelos={len(modelos_paths)} paginas={len(imagens)}")

        for modelo_path in modelos_paths:
            try:
                modelo = _carregar_modelo(str(modelo_path))
            except Exception as exc:
                print(f"[YOLO] Falha ao carregar modelo {modelo_path.name}: {exc}")
                continue

            nomes_classes = getattr(modelo, "names", {}) or {}
            print(f"[YOLO] inferindo com modelo={modelo_path.name}")

            for pagina_idx, img in enumerate(imagens, start=1):
                if paginas_alvo and pagina_idx not in paginas_alvo:
                    continue
                tentativas_conf = [conf, 0.18, 0.12, 0.08]
                resultados = []
                for conf_atual in tentativas_conf:
                    resultados = modelo.predict(source=img, conf=conf_atual, verbose=False)
                    if any(len(r.boxes) for r in resultados):
                        break

                for resultado in resultados:
                    for box in resultado.boxes:
                        score = float(box.conf[0])
                        cls = int(box.cls[0]) if box.cls is not None else 0
                        x1, y1, x2, y2, w, h, area, centro = _normalizar_detect_box(box.xyxy[0])
                        h_img = img.shape[0] if hasattr(img, "shape") else 0
                        classe_nome = nomes_classes.get(cls, "assinatura") if isinstance(nomes_classes, dict) else "assinatura"
                        deteccao = {
                            "pagina": pagina_idx,
                            "classe": cls,
                            "classe_nome": classe_nome,
                            "confianca": round(score, 4),
                            "bbox": [x1, y1, x2, y2],
                            "centro": [round(centro[0], 2), round(centro[1], 2)],
                            "largura": round(w, 2),
                            "altura": round(h, 2),
                            "area": round(area, 2),
                            "zona_vertical": classificar_zona_vertical(y1, y2, h_img),
                            "origem": "yolo",
                            "modelo": modelo_path.name,
                            "modelos": [modelo_path.name],
                        }
                        deteccoes.append(deteccao)

    except Exception as exc:
        print(f"[YOLO] Erro na inferencia: {exc}")

    deteccoes = combinar_deteccoes_ensemble(deteccoes)
    print(f"[YOLO] total_deteccoes_ensemble={len(deteccoes)}")
    return deteccoes


def detectar_assinatura_yolo_global(caminho_pdf, conf=0.25):
    return bool(detectar_assinaturas_yolo(caminho_pdf, conf=conf))


def _mapear_paginas_por_nome(caminho_pdf, nomes):
    nomes_validos = [n for n in nomes if n]
    paginas_por_nome = {nome: set() for nome in nomes_validos}
    textos_paginas = []

    with fitz.open(caminho_pdf) as doc:
        for idx, page in enumerate(doc, start=1):
            txt = extrair_texto_pagina_com_fallback(page)
            txt_norm = normalizar_nome(txt)
            textos_paginas.append(txt_norm)
            for nome in nomes_validos:
                if pagina_pertence_ao_colaborador(txt_norm, normalizar_nome(nome)):
                    paginas_por_nome[nome].add(idx)

    return paginas_por_nome, textos_paginas


def vincular_deteccoes_a_colaboradores(caminho_pdf, nomes, deteccoes):
    resultado = {
        nome: {
            "assinatura": False,
            "confianca": 0.0,
            "paginas": [],
            "bbox": None,
            "zona": None,
            "classe_nome": None,
            "origem": "yolo",
            "motivo": "Nenhuma deteccao vinculada.",
        }
        for nome in nomes if nome
    }

    if not resultado:
        return resultado
    if not deteccoes:
        return resultado

    paginas_por_nome, _ = _mapear_paginas_por_nome(caminho_pdf, list(resultado.keys()))

    try:
        imagens = renderizar_pdf_paginas(caminho_pdf, dpi=200)
    except Exception:
        imagens = []

    deteccoes_por_pagina = {}
    for d in deteccoes:
        deteccoes_por_pagina.setdefault(d.get("pagina"), []).append(d)

    for nome in resultado:
        paginas_nome = paginas_por_nome.get(nome) or set()
        candidatas = []
        for p in paginas_nome:
            candidatas.extend(deteccoes_por_pagina.get(p, []))

        if len(candidatas) == 1:
            d = candidatas[0]
            resultado[nome].update({
                "assinatura": True,
                "confianca": d.get("confianca", 0),
                "paginas": [d.get("pagina")],
                "bbox": d.get("bbox"),
                "zona": d.get("zona_vertical"),
                "classe_nome": d.get("classe_nome"),
                "motivo": "Assinatura vinculada pela pagina do colaborador.",
            })
            continue

        if len(candidatas) > 1 and imagens:
            melhor = None
            melhor_dist = 1e9
            for p in paginas_nome:
                if p <= 0 or p > len(imagens):
                    continue
                caixas_nome = detectar_nomes_com_ocr_data(imagens[p - 1], [nome]).get(nome, [])
                for d in deteccoes_por_pagina.get(p, []):
                    if caixas_nome:
                        dist = min(calcular_distancia_boxes(caixa, d.get("bbox")) for caixa in caixas_nome)
                    else:
                        dist = 1e9
                    if dist < melhor_dist:
                        melhor_dist = dist
                        melhor = d

            if melhor is not None and melhor_dist < 1e9:
                resultado[nome].update({
                    "assinatura": True,
                    "confianca": melhor.get("confianca", 0),
                    "paginas": [melhor.get("pagina")],
                    "bbox": melhor.get("bbox"),
                    "zona": melhor.get("zona_vertical"),
                    "classe_nome": melhor.get("classe_nome"),
                    "motivo": "Assinatura vinculada por proximidade OCR do nome.",
                })
                continue

        if not candidatas and paginas_nome:
            # fallback: pagina +1 quando folha continua na pagina seguinte
            extendidas = set(paginas_nome)
            extendidas.update({p + 1 for p in paginas_nome})
            fallback = [d for d in deteccoes if d.get("pagina") in extendidas]
            if fallback:
                d = max(fallback, key=lambda x: x.get("confianca", 0))
                resultado[nome].update({
                    "assinatura": True,
                    "confianca": d.get("confianca", 0),
                    "paginas": [d.get("pagina")],
                    "bbox": d.get("bbox"),
                    "zona": d.get("zona_vertical"),
                    "classe_nome": d.get("classe_nome"),
                    "motivo": "Assinatura vinculada por fallback de pagina.",
                })

    return resultado


def detectar_assinaturas_yolo_por_colaborador(caminho_pdf, nomes, conf=0.25, deteccoes=None):
    deteccoes = deteccoes if deteccoes is not None else detectar_assinaturas_yolo(caminho_pdf, conf=conf)
    vinculado = vincular_deteccoes_a_colaboradores(caminho_pdf, nomes, deteccoes)

    # compatibilidade com estrutura antiga + campos novos
    retorno = {}
    for nome, info in vinculado.items():
        retorno[nome] = {
            "assinatura": bool(info.get("assinatura")),
            "confianca": float(info.get("confianca") or 0),
            "paginas": info.get("paginas") or [],
            "origem": "yolo",
            "bbox": info.get("bbox"),
            "zona": info.get("zona"),
            "classe_nome": info.get("classe_nome"),
            "motivo": info.get("motivo"),
        }
    return retorno
