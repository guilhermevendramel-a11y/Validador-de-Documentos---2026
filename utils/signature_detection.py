import re
import unicodedata

import cv2
import fitz
import numpy as np
from rapidfuzz import fuzz


def normalizar_nome(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Z0-9 ]+", " ", texto.upper())
    return re.sub(r"\s+", " ", texto).strip()


def renderizar_pagina(pagina, zoom=2.5):
    pix = pagina.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    imagem = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 3:
        return cv2.cvtColor(imagem, cv2.COLOR_RGB2GRAY)
    return cv2.cvtColor(imagem, cv2.COLOR_RGBA2GRAY)


def remover_linhas_tabela(binaria):
    largura_kernel = max(20, binaria.shape[1] // 35)
    altura_kernel = max(20, binaria.shape[0] // 45)

    horizontal = cv2.morphologyEx(
        binaria,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (largura_kernel, 1)),
        iterations=1,
    )
    vertical = cv2.morphologyEx(
        binaria,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, altura_kernel)),
        iterations=1,
    )

    sem_linhas = cv2.subtract(binaria, horizontal)
    sem_linhas = cv2.subtract(sem_linhas, vertical)
    return sem_linhas


def regioes_candidatas(gray):
    altura, largura = gray.shape
    return [
        gray[int(altura * 0.58):altura, :],
        gray[int(altura * 0.42):altura, int(largura * 0.35):largura],
    ]


def pontuar_rubrica(gray):
    melhor_score = 0

    for regiao in regioes_candidatas(gray):
        blur = cv2.GaussianBlur(regiao, (3, 3), 0)
        _, binaria = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        binaria = remover_linhas_tabela(binaria)
        binaria = cv2.morphologyEx(
            binaria,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
            iterations=1,
        )

        contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidatos = []

        for cnt in contornos:
            area = cv2.contourArea(cnt)
            if area < 45 or area > 18000:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            if w < 12 or h < 6:
                continue

            aspect = w / max(h, 1)
            if aspect > 28 or aspect < 0.15:
                continue

            roi = binaria[y:y + h, x:x + w]
            densidade = cv2.countNonZero(roi) / float(w * h)
            if densidade < 0.015 or densidade > 0.65:
                continue

            candidatos.append((area, w, h, densidade))

        area_total = sum(c[0] for c in candidatos)
        largos = sum(1 for _area, w, h, _dens in candidatos if w >= 25 and h >= 8)
        pequenos = len(candidatos)

        # Tabelas de ponto geram dezenas/centenas de contornos pequenos.
        # Rubricas reais tendem a aparecer como poucos agrupamentos manuscritos.
        if pequenos > 45:
            score = min(45, int(largos * 4 + area_total / 900))
            melhor_score = max(melhor_score, score)
            continue

        score = min(100, int((area_total / 120) + largos * 18 + pequenos * 3))
        melhor_score = max(melhor_score, score)

    return melhor_score


def texto_pagina_normalizado(pagina):
    return normalizar_nome(pagina.get_text() or "")


def pagina_pertence_ao_colaborador(texto_pagina, nome_normalizado):
    if not nome_normalizado:
        return False

    if nome_normalizado in texto_pagina:
        return True

    tokens_nome = [t for t in nome_normalizado.split() if len(t) >= 3]
    if not tokens_nome:
        return False

    cobertura = sum(1 for token in tokens_nome if token in texto_pagina) / len(tokens_nome)
    return cobertura >= 0.65 or fuzz.partial_ratio(nome_normalizado, texto_pagina) >= 82


def detectar_rubricas_por_colaborador(caminho_pdf, nomes):
    nomes_norm = {nome: normalizar_nome(nome) for nome in nomes if nome}
    resultado = {
        nome: {"assinatura": False, "confianca": 0, "paginas": []}
        for nome in nomes_norm
    }

    if not nomes_norm:
        return resultado

    try:
        with fitz.open(caminho_pdf) as doc:
            textos = [texto_pagina_normalizado(pagina) for pagina in doc]
            paginas_por_nome = {nome: set() for nome in nomes_norm}

            for nome, nome_norm in nomes_norm.items():
                for idx, texto in enumerate(textos):
                    if pagina_pertence_ao_colaborador(texto, nome_norm):
                        paginas_por_nome[nome].add(idx)
                        if idx + 1 < len(textos):
                            paginas_por_nome[nome].add(idx + 1)

            for idx, pagina in enumerate(doc):
                gray = renderizar_pagina(pagina)
                score = pontuar_rubrica(gray)
                if score < 55:
                    continue

                for nome, paginas in paginas_por_nome.items():
                    if idx in paginas:
                        resultado[nome]["assinatura"] = True
                        resultado[nome]["confianca"] = max(resultado[nome]["confianca"], score)
                        resultado[nome]["paginas"].append(idx + 1)

    except Exception as exc:
        print(f"Erro ao detectar rubricas: {exc}")

    return resultado


def detectar_rubrica_global(caminho_pdf):
    try:
        with fitz.open(caminho_pdf) as doc:
            return any(pontuar_rubrica(renderizar_pagina(pagina)) >= 55 for pagina in doc)
    except Exception as exc:
        print(f"Erro ao detectar rubrica global: {exc}")
        return False
