from pathlib import Path
p=Path(r"services/cartao_ponto_service.py")
s=p.read_text(encoding='utf-8')
if 'def _extrair_nome_em_pagina_isolada(' not in s:
    ins='''\n\ndef _extrair_nome_em_pagina_isolada(caminho_arquivo: str, pagina: int) -> str:\n    try:\n        img = renderizar_pagina_pdf(caminho_arquivo, max(0, int(pagina) - 1), dpi=360)\n        rec = recortar_area_documento_cartao(img)\n        base = rec.get("imagem_recortada")\n        if base is None:\n            return ""\n        recortes = gerar_recortes_cartao_ponto(base)\n        topo = recortes.get("topo")\n        if topo is None:\n            return ""\n        arr = np.array(topo)\n        if arr.ndim == 3:\n            gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)\n        else:\n            gray = arr\n        txts = []\n        for block_size, c_val in [(31, 8), (41, 10), (51, 12)]:\n            th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c_val)\n            txts.append(pytesseract.image_to_string(th, lang='por', config='--oem 1 --psm 6 -c preserve_interword_spaces=1'))\n        txts.append(pytesseract.image_to_string(gray, lang='por', config='--oem 1 --psm 6 -c preserve_interword_spaces=1'))\n        for tx in txts:\n            cand = _extrair_nome_relaxado_emergencial(tx)\n            if cand and eh_nome_colaborador_valido(cand):\n                return normalizar_nome_colaborador(cand)\n    except Exception as exc:\n        print(f"[PONTO] Falha extracao isolada pagina {pagina}: {exc}")\n    return ""\n\n'''
    s=s.replace('def consolidar_colaboradores_cartao_ponto(resultados_paginas, competencia_esperada=None):', ins+'def consolidar_colaboradores_cartao_ponto(resultados_paginas, competencia_esperada=None):')
old='''            nome_relaxado = _extrair_nome_relaxado_emergencial(
                f"{fonte.get('texto_topo') or ''}\n{fonte.get('texto_pagina') or ''}"
            )
            nome_agressivo = _extrair_nome_empregado_imagem_agressivo(caminho_arquivo, pg)
            nome_candidato = nome_bruto_retry if eh_nome_colaborador_valido(nome_bruto_retry) else (nome_relaxado or nome_agressivo)
'''
new='''            nome_relaxado = _extrair_nome_relaxado_emergencial(
                f"{fonte.get('texto_topo') or ''}\n{fonte.get('texto_pagina') or ''}"
            )
            nome_agressivo = _extrair_nome_empregado_imagem_agressivo(caminho_arquivo, pg)
            nome_isolado = _extrair_nome_em_pagina_isolada(caminho_arquivo, pg)
            nome_candidato = nome_bruto_retry if eh_nome_colaborador_valido(nome_bruto_retry) else (nome_isolado or nome_relaxado or nome_agressivo)
'''
if old in s:
    s=s.replace(old,new)
p.write_text(s,encoding='utf-8')
