from pathlib import Path
p = Path(r"services/cartao_ponto_service.py")
s = p.read_text(encoding='utf-8')
if 'import cv2' not in s:
    s = s.replace('from concurrent.futures import ThreadPoolExecutor, TimeoutError\n\n', 'from concurrent.futures import ThreadPoolExecutor, TimeoutError\n\nimport cv2\nimport numpy as np\n\n')
if 'from utils.tesseract_config import pytesseract' not in s:
    s = s.replace('from utils.signature_detection import detectar_rubrica_global_evidencias\n', 'from utils.signature_detection import detectar_rubrica_global_evidencias\nfrom utils.tesseract_config import pytesseract\n')
marker = 'def consolidar_colaboradores_cartao_ponto(resultados_paginas, competencia_esperada=None):\n'
if '_extrair_nome_empregado_imagem_agressivo' not in s:
    helper = '''\n\ndef _extrair_nome_empregado_imagem_agressivo(caminho_arquivo: str, pagina: int) -> str:\n    try:\n        img = renderizar_pagina_pdf(caminho_arquivo, max(0, int(pagina) - 1), dpi=420)\n        if img is None:\n            return ""\n        arr = np.array(img)\n        if arr.ndim == 3:\n            gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)\n        else:\n            gray = arr\n        h, w = gray.shape[:2]\n        y1, y2 = int(h * 0.10), int(h * 0.42)\n        crop = gray[y1:y2, 0:w]\n        if crop.size == 0:\n            return ""\n\n        candidatos = []\n        for block_size, c_val in [(31, 8), (41, 10), (51, 12)]:\n            th = cv2.adaptiveThreshold(crop, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c_val)\n            txt = pytesseract.image_to_string(th, lang='por', config='--oem 1 --psm 6 -c preserve_interword_spaces=1')\n            cand = _extrair_nome_relaxado_emergencial(txt)\n            if cand:\n                candidatos.append(cand)\n\n        if candidatos:\n            candidatos.sort(key=lambda x: (len(x.split()), len(x)), reverse=True)\n            return candidatos[0]\n    except Exception as exc:\n        print(f"[PONTO] Falha OCR agressivo nome pagina {pagina}: {exc}")\n    return ""\n\n'''
    s = s.replace(marker, helper + marker)
old = """            nome_relaxado = _extrair_nome_relaxado_emergencial(
                f"{fonte.get('texto_topo') or ''}\n{fonte.get('texto_pagina') or ''}"
            )
            nome_candidato = nome_bruto_retry if eh_nome_colaborador_valido(nome_bruto_retry) else nome_relaxado
"""
new = """            nome_relaxado = _extrair_nome_relaxado_emergencial(
                f"{fonte.get('texto_topo') or ''}\n{fonte.get('texto_pagina') or ''}"
            )
            nome_agressivo = _extrair_nome_empregado_imagem_agressivo(caminho_arquivo, pg)
            nome_candidato = nome_bruto_retry if eh_nome_colaborador_valido(nome_bruto_retry) else (nome_relaxado or nome_agressivo)
"""
if old in s:
    s = s.replace(old, new)
p.write_text(s, encoding='utf-8')
