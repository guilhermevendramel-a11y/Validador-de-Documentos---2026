import os
import re
import unicodedata
from difflib import SequenceMatcher
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError

import cv2
import numpy as np
import fitz
from dotenv import load_dotenv, dotenv_values

from services.cartao_ponto_layout_parser import (
    agrupar_paginas_cartao_ponto,
    gerar_recortes_cartao_ponto,
    preparar_imagem_cartao_manual,
    processar_paginas_cartao_ponto_layout,
    recortar_area_documento_cartao,
    renderizar_pagina_pdf,
    tem_marcacao_manual_na_regiao,
)
from services.document_learning import aprender_documento
from services.cartao_ponto_modelo_ordem import eh_modelo_ordem, extrair_campos_modelo_ordem
from utils.digital_signature_detection import detectar_autenticacao_digital
from utils.gemini.cartao_ponto import extrair_cartao_ponto_pdf
from utils.openai.cartao_ponto import extrair_cartao_ponto_openai_pdf
from utils.openai.cartao_ponto import analisar_pagina_cartao_ponto_openai_vision
from utils.ocr import extrair_documento_inteligente
from utils.signature_detection import detectar_rubrica_global_evidencias
from utils.tesseract_config import pytesseract
from utils.yolo_signature_detection import caminhos_modelos_yolo, yolo_disponivel
from validators.cartao_ponto.rules import validar_cartao_ponto

load_dotenv(override=True)


def _log_openai_key_context():
    try:
        env_file = dotenv_values(".env")
        key_file = str(env_file.get("OPENAI_API_KEY") or "").strip()
    except Exception:
        key_file = ""
    key_runtime = str(os.getenv("OPENAI_API_KEY") or "").strip()
    same = bool(key_file and key_runtime and key_file == key_runtime)
    pref = (key_runtime[:12] + "...") if len(key_runtime) >= 12 else key_runtime
    print(
        f"[OPENAI KEY] runtime_set={bool(key_runtime)} len={len(key_runtime)} "
        f"prefix={pref} file_match={same}"
    )


def _corrigir_texto_quebrado(valor):
    if not isinstance(valor, str):
        return valor
    txt = valor
    # Corrige mojibake comum: UTF-8 lido como latin-1/cp1252 (ex.: "nÃ£o", "pÃ¡gina").
    if ("Ã" in txt) or ("Â" in txt) or ("\ufffd" in txt):
        try:
            reparado = txt.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
            if reparado:
                txt = reparado
        except Exception:
            pass
    # Correcoes explicitas para casos frequentes observados no retorno.
    mapa = {
        "nÃ£o": "não",
        "NÃ£o": "Não",
        "pÃ¡gina": "página",
        "PÃ¡gina": "Página",
        "vÃ¡lido": "válido",
        "VÃ¡lido": "Válido",
        "confiÃ¡vel": "confiável",
        "competÃªncia": "competência",
        "marcaÃ§Ãµes": "marcações",
        "possÃ­vel": "possível",
        "referÃªncia": "referência",
        "versÃ£o": "versão",
        "cartÃ£o": "cartão",
        "razÃ£o": "razão",
        "Ã­mpar": "ímpar",
        "parÃ¢metro": "parâmetro",
    }
    for origem, destino in mapa.items():
        if origem in txt:
            txt = txt.replace(origem, destino)
    return txt


def _corrigir_payload_texto(obj):
    if isinstance(obj, dict):
        return {k: _corrigir_payload_texto(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_corrigir_payload_texto(x) for x in obj]
    if isinstance(obj, str):
        return _corrigir_texto_quebrado(obj)
    return obj


def extrair_cartao_ponto_pdf_com_timeout(caminho_arquivo, timeout_segundos=15):
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            futuro = executor.submit(extrair_cartao_ponto_pdf, caminho_arquivo)
            return futuro.result(timeout=timeout_segundos) or {"colaboradores": []}
    except TimeoutError:
        print(f"[PONTO] Timeout Gemini apos {timeout_segundos}s.")
        return {"colaboradores": []}
    except Exception as exc:
        print(f"[PONTO] Falha Gemini: {exc}")
        return {"colaboradores": []}


def _api_key_disponivel(nome_variavel):
    return bool(os.getenv(nome_variavel, "").strip())


_OPENAI_CARTAO_NOMES_CACHE = {}


def _nomes_esperados_env():
    bruto = (os.getenv("CARTAO_PONTO_NOMES_ESPERADOS") or "").strip()
    if not bruto:
        return []
    itens = [normalizar_nome_colaborador(x) for x in re.split(r"[;\n,|]+", bruto) if str(x or "").strip()]
    return [n for n in itens if eh_nome_colaborador_valido(n)]


def _nomes_candidatos_documento(resultados_paginas, paginas_layout, limite=20):
    candidatos = []
    fontes = []
    for rp in (resultados_paginas or []):
        fontes.append(rp.get("nome_bruto") or "")
        fontes.append(rp.get("nome") or "")
        fontes.append(rp.get("texto_topo") or "")
    for p in (paginas_layout or []):
        fontes.append(p.get("nome_colaborador") or "")
        fontes.append(p.get("texto_topo") or "")
    bloqueios = {"EMPREGADOR", "RAZAO", "SOCIAL", "CNPJ", "CPF", "CTPS", "QUINZENA", "ASSINATURA", "HORARIO", "JORNADA"}
    for src in fontes:
        txt = normalizar_nome_colaborador(src)
        if not txt:
            continue
        # tenta quebrar linhas longas e coletar trechos com cara de nome.
        for parte in re.split(r"[;|:/\n\r\t]", txt):
            cand = normalizar_nome_colaborador(parte)
            if not cand:
                continue
            up = cand.upper()
            if any(b in up for b in bloqueios):
                continue
            if len(cand.split()) < 2 or len(cand.split()) > 6:
                continue
            if re.search(r"\d", cand):
                continue
            if cand not in candidatos:
                candidatos.append(cand)
            if len(candidatos) >= limite:
                return candidatos
    return candidatos


def _escolher_nome_por_similaridade(texto, nomes_referencia, limiar=0.62):
    t = _nome_norm(texto)
    if not t or not nomes_referencia:
        return "", 0.0
    melhor_nome = ""
    melhor = 0.0
    for nome in nomes_referencia:
        n = _nome_norm(nome)
        if not n:
            continue
        sim_global = SequenceMatcher(None, n, t).ratio()
        tokens = [tok for tok in n.split() if len(tok) >= 4]
        hit = 0.0
        if tokens:
            hit = sum(1.0 for tok in tokens if tok in t) / float(len(tokens))
        score = max(sim_global, hit)
        if score > melhor:
            melhor = score
            melhor_nome = nome
    if melhor >= limiar:
        return normalizar_nome_colaborador(melhor_nome), float(melhor)
    return "", float(melhor)


def montar_resumo_assinaturas(colaboradores):
    total = len(colaboradores)
    digitais = sum(
        1
        for col in colaboradores
        if "digital" in str(col.get("assinatura_tipo") or "").strip().lower()
    )
    manuais = sum(
        1
        for col in colaboradores
        if any(
            k in str(col.get("assinatura_tipo") or "").strip().lower()
            for k in ["manual", "rubrica"]
        )
    )
    ausentes = sum(1 for col in colaboradores if not col.get("assinatura"))
    tipo_predominante = "Manual/Rubrica" if manuais >= digitais and manuais > 0 else ("Assinatura digital" if digitais > 0 else "Nao identificada")
    return {
        "total_colaboradores": total,
        "assinatura_digital": digitais,
        "assinatura_manual_rubrica": manuais,
        "assinatura_ausente": ausentes,
        "tipo_predominante": tipo_predominante,
    }


def avaliar_status(colaboradores):
    if not colaboradores:
        return "Reprovado"
    ok = sum(1 for c in colaboradores if c.get("status") == "OK")
    inconc = sum(1 for c in colaboradores if c.get("status") == "INCONCLUSIVO")
    if ok == len(colaboradores):
        return "Aprovado"
    if ok > 0 or inconc > 0:
        return "Parcial"
    return "Reprovado"


def _nome_key(nome):
    return (nome or "").strip().lower()


def _nome_norm(nome):
    txt = unicodedata.normalize("NFKD", str(nome or ""))
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"\s+", " ", txt).strip().lower()
    return txt


def _nome_tem_evidencia_no_texto(nome: str, texto: str) -> bool:
    n = _nome_norm(nome)
    t = _nome_norm(texto)
    if not n or not t:
        return False
    tokens = [w for w in n.split() if len(w) >= 4]
    if not tokens:
        return False
    # Exige ao menos um token "forte" do nome presente no texto OCR do documento.
    return any(tok in t for tok in tokens)


def _nome_tem_evidencia_em_paginas(nome: str, paginas_texto, min_paginas=2) -> bool:
    n = _nome_norm(nome)
    if not n:
        return False
    tokens = [w for w in n.split() if len(w) >= 4]
    if not tokens:
        return False
    hit_paginas = 0
    for p in paginas_texto or []:
        t = _nome_norm((p or {}).get("texto") or "")
        if not t:
            continue
        if any(tok in t for tok in tokens):
            hit_paginas += 1
            if hit_paginas >= int(min_paginas):
                return True
    return False


def nome_valido_openai_cartao(nome, confianca=0.0):
    nome = normalizar_nome_colaborador(nome)
    if not eh_nome_colaborador_valido(nome):
        return False
    bloqueios = [
        "EMPREGADOR", "RAZAO", "RAZÃƒO", "SOCIAL", "LOCAL", "TRABALHO", "ATIVIDADE", "ECONOMICA", "ECONÃ”MICA",
        "FUNCAO", "FUNÃ‡ÃƒO", "ASSINATURA", "RECEBI", "SALDO", "QUINZENA", "ENTRADA", "SAIDA", "SAÃDA",
        "HORARIO", "HORÃRIO", "JORNADA", "CNPJ", "CPF", "CTPS", "LTDA", "EIRELI", "EPP", "ME", "S/A",
    ]
    up = (nome or "").upper()
    if any(b in up for b in bloqueios):
        return False
    # Em fallback visual, exige confianca minima para reduzir nomes "inventados"/ruidosos.
    try:
        if float(confianca or 0.0) < 0.78:
            return False
    except Exception:
        return False
    if len(nome.split()) < 2 or len(nome.split()) > 6:
        return False
    if re.search(r"\d", nome):
        return False
    tokens = [t for t in nome.split() if t.strip()]
    tokens_longos = [t for t in tokens if len(t) >= 3]
    if len(tokens_longos) < 2:
        return False
    # Bloqueia padrao comum de ruido OCR (muitas palavras curtas/sem sobrenome claro).
    curtas = sum(1 for t in tokens if len(t) <= 2)
    if curtas >= max(2, len(tokens) // 2):
        return False
    # Evita nomes com cara de sopa de letrinhas em caixa alta.
    if nome.isupper():
        vogais = sum(1 for ch in nome if ch in "AEIOUÁÉÍÓÚÂÊÔÃÕ")
        letras = sum(1 for ch in nome if ch.isalpha())
        if letras > 0 and (vogais / letras) < 0.28:
            return False
    simbolos = sum(1 for ch in nome if not (ch.isalpha() or ch.isspace() or ch in "-'"))
    if simbolos > 2:
        return False
    return True


def _nome_parece_ruido_ocr(nome):
    n = normalizar_nome_colaborador(nome or "")
    if not n:
        return True
    up = n.upper()
    bloqueios = [
        "EMPREGADOR", "RAZAO", "SOCIAL", "ASSINATURA", "QUINZENA", "HORARIO",
        "JORNADA", "CNPJ", "CPF", "CTPS", "LTDA", "EIRELI", "EPP", "S/A",
    ]
    if any(b in up for b in bloqueios):
        return True
    parts = [p for p in n.split() if p]
    if len(parts) < 2 or len(parts) > 6:
        return True
    if re.search(r"\d", n):
        return True
    # nomes muito "quebrados" no OCR: excesso de tokens curtos.
    curtas = sum(1 for p in parts if len(p) <= 2)
    if curtas >= max(2, len(parts) // 2):
        return True
    # baixa taxa de vogais sugere sopa de letras.
    letras = [c for c in up if c.isalpha()]
    if letras:
        vogais = sum(1 for c in letras if c in "AEIOUÁÉÍÓÚÂÊÔÃÕ")
        if (vogais / float(len(letras))) < 0.27:
            return True
    return False


def _colaboradores_suspeitos_ou_poucos(colaboradores, resultados_paginas):
    cols = list(colaboradores or [])
    total_paginas = len(resultados_paginas or [])
    if not cols:
        return True
    suspeitos = 0
    for c in cols:
        nome_c = c.get("nome", "")
        if _nome_parece_ruido_ocr(nome_c):
            suspeitos += 1
            continue
        # Para resultado local, não usar "assinatura_confianca" como confiança de nome.
        conf_nome = float(c.get("nome_confianca") or c.get("score") or 0.0)
        if not nome_valido_openai_cartao(nome_c, conf_nome if conf_nome <= 1.0 else 1.0):
            suspeitos += 1
    if suspeitos > 0:
        print(f"[OPENAI VISION] nomes suspeitos detectados no OCR local: {suspeitos}/{len(cols)}")
        return True
    esperado_min = max(1, total_paginas // 2)
    return len(cols) < esperado_min


def _tem_nome_suspeito_local(colaboradores):
    for c in (colaboradores or []):
        if _nome_parece_ruido_ocr(c.get("nome", "")):
            return True
    return False


def processar_cartao_manual_escaneado_openai_vision(caminho_arquivo, competencia_esperada=None, nomes_esperados=None):
    colaboradores = []
    avisos = ["Fallback OpenAI Vision com pÃ¡gina inteira aplicado."]
    nomes_referencia = [normalizar_nome_colaborador(n) for n in (nomes_esperados or []) if eh_nome_colaborador_valido(n)]
    pendentes = []
    try:
        with fitz.open(caminho_arquivo) as doc:
            total = len(doc)
            for pg in range(1, total + 1, 2):
                idx_frente = pg - 1
                img_frente = renderizar_pagina_pdf(caminho_arquivo, idx_frente, dpi=280)
                print(f"[OPENAI VISION][P{pg}] enviando pÃ¡gina inteira")
                print(f"[OPENAI VISION][P{pg}] tipo=frente")
                r_frente = analisar_pagina_cartao_ponto_openai_vision(
                    img_frente, pg, layout_detectado="manual_frente", tipo_pagina="frente", competencia_esperada=competencia_esperada, nomes_esperados=nomes_esperados
                )
                nome_raw = r_frente.get("nome") or ""
                conf_frente = float(r_frente.get("confianca") or 0.0)
                nome_ok = nome_valido_openai_cartao(nome_raw, conf_frente)
                print(f"[OPENAI VISION][P{pg}] nome retornado={nome_raw}")
                print(f"[OPENAI VISION][P{pg}] nome aceito={nome_ok}")
                if not nome_ok:
                    if nomes_referencia:
                        try:
                            texto_img = pytesseract.image_to_string(img_frente, lang="por", config="--oem 1 --psm 6")
                        except Exception:
                            texto_img = ""
                        nome_sim, score_sim = _escolher_nome_por_similaridade(texto_img, nomes_referencia, limiar=0.60)
                        if nome_sim:
                            nome_raw = nome_sim
                            nome_ok = True
                            print(f"[OPENAI VISION][P{pg}] nome recuperado por similaridade={nome_raw} score={score_sim:.2f}")
                    if not nome_ok:
                        pendentes.append({"pagina": pg, "img_frente": img_frente, "r_frente": r_frente})
                        avisos.append(f"Página {pg} ignorada: nome visual ausente/suspeito.")
                        continue
                nome = normalizar_nome_colaborador(nome_raw)
                if nome and nome not in nomes_referencia:
                    nomes_referencia.append(nome)

                pg_verso = pg + 1 if pg + 1 <= total else None
                r_verso = {
                    "pagina": pg_verso or 0,
                    "tipo_pagina": "verso",
                    "nome": "",
                    "nome_encontrado": False,
                    "competencia": "",
                    "marcacoes_encontradas": False,
                    "assinatura": False,
                    "assinatura_tipo": "ausente",
                    "confianca": 0.0,
                    "motivo": "",
                    "avisos": [],
                }
                if pg_verso:
                    img_verso = renderizar_pagina_pdf(caminho_arquivo, pg_verso - 1, dpi=280)
                    print(f"[OPENAI VISION][P{pg_verso}] enviando pÃ¡gina inteira")
                    print(f"[OPENAI VISION][P{pg_verso}] tipo=verso")
                    r_verso = analisar_pagina_cartao_ponto_openai_vision(
                        img_verso, pg_verso, layout_detectado="manual_verso", tipo_pagina="verso", competencia_esperada=competencia_esperada, nomes_esperados=None
                    )
                    print(f"[OPENAI VISION][P{pg_verso}] assinatura={bool(r_verso.get('assinatura'))}")
                    avisos.append(f"PÃ¡gina {pg_verso} vinculada como verso da pÃ¡gina {pg}.")

                comp = (r_frente.get("competencia") or "").strip()
                if not comp and competencia_esperada:
                    comp = competencia_esperada
                    avisos.append("CompetÃªncia assumida pela competÃªncia informada no formulÃ¡rio.")
                comp_ok = bool(comp and (not competencia_esperada or comp == competencia_esperada))
                marc = bool(r_frente.get("marcacoes_encontradas") or r_verso.get("marcacoes_encontradas"))
                ass = bool(r_verso.get("assinatura") or r_frente.get("assinatura"))
                ass_pg = pg_verso if bool(r_verso.get("assinatura")) else (pg if bool(r_frente.get("assinatura")) else None)
                score, status = _score_status_colaborador(True, comp_ok, marc, ass)
                motivos = []
                if not comp_ok:
                    motivos.append(f"CompetÃªncia divergente/ausente (lida: {comp or '-'} | esperada: {competencia_esperada or '-'})")
                if not marc:
                    motivos.append("MarcaÃ§Ãµes insuficientes")
                if not ass:
                    motivos.append("Assinatura/rubrica ausente")
                paginas = [pg] + ([pg_verso] if pg_verso else [])
                print(f"[OPENAI VISION] grupo pÃ¡ginas {pg}{'+'+str(pg_verso) if pg_verso else ''} criado para colaborador {nome}")
                colaboradores.append({
                    "nome": nome,
                    "colaborador": nome,
                    "paginas": paginas,
                    "layout_origem": "manual_frente_verso",
                    "nome_origem": "openai_vision_pagina_inteira",
                    "competencia": comp or "-",
                    "competencia_ok": comp_ok,
                    "marcacoes": marc,
                    "marcacoes_encontradas": marc,
                    "qtd_horarios": 0,
                    "assinatura": ass,
                    "assinatura_tipo": "assinatura_manual" if ass else "ausente",
                    "assinatura_origem": "openai_vision_pagina_inteira",
                    "assinatura_confianca": max(float(r_frente.get("confianca") or 0.0), float(r_verso.get("confianca") or 0.0)),
                    "assinatura_pagina": ass_pg,
                    "assinatura_zona": "rodape" if ass_pg == pg_verso else "desconhecida",
                    "status": status,
                    "score": score,
                    "motivos": motivos,
                    "avisos": list(r_frente.get("avisos") or []) + list(r_verso.get("avisos") or []),
                    "datado": True,
                })

            # Segunda passagem: tenta recuperar páginas ímpares rejeitadas usando nomes de referência.
            if pendentes and nomes_referencia:
                avisos.append("Segunda tentativa OpenAI Vision aplicada com nomes de referência.")
                for item in pendentes:
                    pg = int(item.get("pagina") or 0)
                    if any(pg in (c.get("paginas") or []) for c in colaboradores):
                        continue
                    print(f"[OPENAI VISION][P{pg}] segunda tentativa com nomes_esperados={len(nomes_referencia)}")
                    r_frente = analisar_pagina_cartao_ponto_openai_vision(
                        item.get("img_frente"),
                        pg,
                        layout_detectado="manual_frente",
                        tipo_pagina="frente",
                        competencia_esperada=competencia_esperada,
                        nomes_esperados=nomes_referencia,
                    )
                    nome_raw = r_frente.get("nome") or ""
                    conf_frente = float(r_frente.get("confianca") or 0.0)
                    nome_ok = nome_valido_openai_cartao(nome_raw, conf_frente)
                    print(f"[OPENAI VISION][P{pg}] segunda tentativa nome={nome_raw} aceito={nome_ok}")
                    if not nome_ok:
                        continue
                    nome = normalizar_nome_colaborador(nome_raw)
                    pg_verso = pg + 1 if pg + 1 <= total else None
                    r_verso = {
                        "pagina": pg_verso or 0,
                        "tipo_pagina": "verso",
                        "nome": "",
                        "nome_encontrado": False,
                        "competencia": "",
                        "marcacoes_encontradas": False,
                        "assinatura": False,
                        "assinatura_tipo": "ausente",
                        "confianca": 0.0,
                        "motivo": "",
                        "avisos": [],
                    }
                    if pg_verso:
                        img_verso = renderizar_pagina_pdf(caminho_arquivo, pg_verso - 1, dpi=280)
                        r_verso = analisar_pagina_cartao_ponto_openai_vision(
                            img_verso, pg_verso, layout_detectado="manual_verso", tipo_pagina="verso", competencia_esperada=competencia_esperada, nomes_esperados=None
                        )
                        avisos.append(f"PÃ¡gina {pg_verso} vinculada como verso da pÃ¡gina {pg}.")
                    comp = (r_frente.get("competencia") or "").strip()
                    if not comp and competencia_esperada:
                        comp = competencia_esperada
                        avisos.append("CompetÃªncia assumida pela competÃªncia informada no formulÃ¡rio.")
                    comp_ok = bool(comp and (not competencia_esperada or comp == competencia_esperada))
                    marc = bool(r_frente.get("marcacoes_encontradas") or r_verso.get("marcacoes_encontradas"))
                    ass = bool(r_verso.get("assinatura") or r_frente.get("assinatura"))
                    ass_pg = pg_verso if bool(r_verso.get("assinatura")) else (pg if bool(r_frente.get("assinatura")) else None)
                    score, status = _score_status_colaborador(True, comp_ok, marc, ass)
                    motivos = []
                    if not comp_ok:
                        motivos.append(f"CompetÃªncia divergente/ausente (lida: {comp or '-'} | esperada: {competencia_esperada or '-'})")
                    if not marc:
                        motivos.append("MarcaÃ§Ãµes insuficientes")
                    if not ass:
                        motivos.append("Assinatura/rubrica ausente")
                    paginas = [pg] + ([pg_verso] if pg_verso else [])
                    colaboradores.append({
                        "nome": nome,
                        "colaborador": nome,
                        "paginas": paginas,
                        "layout_origem": "manual_frente_verso",
                        "nome_origem": "openai_vision_pagina_inteira",
                        "competencia": comp or "-",
                        "competencia_ok": comp_ok,
                        "marcacoes": marc,
                        "marcacoes_encontradas": marc,
                        "qtd_horarios": 0,
                        "assinatura": ass,
                        "assinatura_tipo": "assinatura_manual" if ass else "ausente",
                        "assinatura_origem": "openai_vision_pagina_inteira",
                        "assinatura_confianca": max(float(r_frente.get("confianca") or 0.0), float(r_verso.get("confianca") or 0.0)),
                        "assinatura_pagina": ass_pg,
                        "assinatura_zona": "rodape" if ass_pg == pg_verso else "desconhecida",
                        "status": status,
                        "score": score,
                        "motivos": motivos,
                        "avisos": list(r_frente.get("avisos") or []) + list(r_verso.get("avisos") or []),
                        "datado": True,
                    })
    except Exception as exc:
        avisos.append(f"Falha fallback OpenAI Vision: {exc}")
    return colaboradores, avisos


def detectar_cartao_manual_escaneado(resultados_paginas, ocr_doc):
    paginas = list(resultados_paginas or [])
    if len(paginas) <= 2:
        return False
    metodo = str((ocr_doc or {}).get("metodo") or "").lower()
    qualidade = float((ocr_doc or {}).get("qualidade") or 0.0)
    if metodo == "texto_nativo" and qualidade >= 0.70:
        return False
    layouts_ok = {"desconhecido", "imagem_escaneada_generica", "manual_frente", "manual_verso"}
    hits_layout = sum(1 for p in paginas if str(p.get("layout") or "").strip().lower() in layouts_ok)
    if hits_layout < max(2, int(len(paginas) * 0.6)):
        return False
    texto = _nome_norm("\n".join([str(p.get("texto_pagina") or "") for p in paginas]))
    indicios = ["1 QUINZENA", "2 QUINZENA", "EMPREGADO", "MES", "ANO", "ASSINATURA", "RECEBI O SALDO"]
    return any(tok in texto.upper() for tok in indicios)


def agrupar_manual_frente_verso(resultados_paginas):
    itens = sorted((resultados_paginas or []), key=lambda x: int(x.get("pagina") or 0))
    by = {int(p.get("pagina") or 0): p for p in itens}
    grupos = []
    max_pg = max(by.keys()) if by else 0
    for pg in range(1, max_pg + 1, 2):
        frente = by.get(pg)
        if not frente:
            continue
        verso = by.get(pg + 1)
        grupos.append({"frente": frente, "verso": verso, "paginas": [pg] + ([pg + 1] if verso else [])})
    return grupos


def _extrair_competencia_manual_texto(texto, competencia_esperada=None):
    t = _nome_norm(texto or "")
    m = re.search(r"\b(0?[1-9]|1[0-2])[/-](20\d{2})\b", t)
    if m:
        return f"{int(m.group(1)):02d}/{m.group(2)}", False
    meses = {
        "JANEIRO": "01", "FEVEREIRO": "02", "MARCO": "03", "MARÃ‡O": "03", "ABRIL": "04",
        "MAIO": "05", "JUNHO": "06", "JULHO": "07", "AGOSTO": "08", "SETEMBRO": "09",
        "OUTUBRO": "10", "NOVEMBRO": "11", "DEZEMBRO": "12",
    }
    for mes, num in meses.items():
        if mes in t:
            ay = re.search(r"\b(20\d{2})\b", t)
            if ay:
                return f"{num}/{ay.group(1)}", False
    if competencia_esperada:
        return competencia_esperada, True
    return "", False


def extrair_nome_manual_visual(caminho_pdf, pagina, nomes_esperados=None):
    rec = preparar_imagem_cartao_manual(caminho_pdf, pagina, dpi=350)
    faixa = rec.get("faixa_empregado")
    cab = rec.get("cabecalho")
    avisos = []
    texto_local = ""
    if faixa is not None and getattr(faixa, "size", 0) > 0:
        texto_local = pytesseract.image_to_string(faixa, lang="por", config="--oem 1 --psm 6") or ""
    if (not texto_local.strip()) and cab is not None and getattr(cab, "size", 0) > 0:
        texto_local = pytesseract.image_to_string(cab, lang="por", config="--oem 1 --psm 11") or ""
    nome_info = extrair_nome_colaborador_cartao(texto_local, linhas_ocr=[texto_local], nomes_esperados=(nomes_esperados or []), modo_estrito=False)
    nome = normalizar_nome_colaborador(nome_info.get("nome") or "")
    if eh_nome_colaborador_valido(nome) and (not _nome_parece_artefato_template(nome)):
        return {"nome": nome, "confianca": float(nome_info.get("confianca") or 0.82), "origem": "ocr_local", "avisos": avisos}

    # Fallback IA somente ChatGPT/OpenAI (sem Gemini no mÃ³dulo de cartÃ£o ponto).
    candidatos = _nomes_openai_cartao(caminho_pdf, competencia_esperada=None)
    nome_ia = ""
    if nomes_esperados:
        melhor = ""
        melhor_sim = 0.0
        for cand in candidatos:
            for n in nomes_esperados:
                sim = _similaridade_nome(n, cand)
                if sim > melhor_sim:
                    melhor_sim = sim
                    melhor = n
        if melhor and melhor_sim >= 0.55:
            nome_ia = normalizar_nome_colaborador(melhor)
    elif candidatos:
        nome_ia = normalizar_nome_colaborador(candidatos[0])
    if eh_nome_colaborador_valido(nome_ia) and (not _nome_parece_artefato_template(nome_ia)):
        avisos.append("Nome extraÃ­do por IA visual no cabeÃ§alho.")
        return {"nome": nome_ia, "confianca": 0.75, "origem": "ia_visual", "avisos": avisos}
    return {"nome": "", "confianca": 0.0, "origem": "nao_encontrado", "avisos": avisos}


def _evidencia_visual_marcacoes(img_tabela):
    if img_tabela is None or getattr(img_tabela, "size", 0) == 0:
        return False
    gray = cv2.cvtColor(img_tabela, cv2.COLOR_BGR2GRAY) if len(img_tabela.shape) == 3 else img_tabela
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10)
    dens = float(np.count_nonzero(th)) / float(max(1, th.size))
    return dens >= 0.06


def _assinatura_rodape_verso_manual(recortes):
    rodape = recortes.get("rodape")
    if rodape is None or getattr(rodape, "size", 0) == 0:
        return False, 0.0
    ok_manual, score_manual = tem_marcacao_manual_na_regiao(rodape)
    if ok_manual and score_manual >= 0.22:
        return True, float(score_manual)
    score_cv = pontuar_rubrica(cv2.cvtColor(rodape, cv2.COLOR_BGR2GRAY) if len(rodape.shape) == 3 else rodape)
    if score_cv >= 50:
        return True, min(0.95, score_cv / 100.0)
    return False, 0.0


def _nomes_openai_cartao(caminho_arquivo, competencia_esperada=None):
    try:
        st = os.stat(caminho_arquivo)
        key = f"{os.path.abspath(caminho_arquivo)}|{st.st_mtime_ns}|{st.st_size}|{competencia_esperada or ''}"
        if key in _OPENAI_CARTAO_NOMES_CACHE:
            return _OPENAI_CARTAO_NOMES_CACHE[key]
        resp = extrair_cartao_ponto_openai_pdf(caminho_arquivo, competencia_esperada=competencia_esperada, perfil_leitura="auto")
        nomes = [normalizar_nome_colaborador(c.get("nome") or "") for c in (resp.get("colaboradores") or [])]
        nomes = [n for n in nomes if eh_nome_colaborador_valido(n) and (not _nome_parece_artefato_template(n))]
        _OPENAI_CARTAO_NOMES_CACHE[key] = nomes
        return nomes
    except Exception:
        return []


def _nome_colaborador_valido(nome):
    nome = re.sub(r"\s+", " ", str(nome or "")).strip()
    if not nome:
        return False
    if nome.lower() == "colaborador sem nome":
        return False
    if len(nome.split()) < 2:
        return False
    if re.search(r"^\d+\b", nome):
        return False
    if re.search(r"[\[\]{}=;\\/*|<>]", nome):
        return False
    norm = _nome_norm(nome)
    bloqueios = [
        "folha de ponto",
        "folhaponto",
        "folha ponto",
        "folha de pagamento",
        "folha pagamento",
        "pagamento",
        "ponto",
        "registro de ocorr",
        "assinatura",
        "empresa",
        "cliente",
        "periodo",
        "perÃ­odo",
        "competencia",
        "competÃªncia",
        "jornada",
        "horario",
        "horÃ¡rio",
        "horas extras",
        "hora extra",
        "total de horas",
        "banco de horas",
        "saldo de horas",
        "construcao",
        "construÃ§Ãµes",
        "construcoes",
        "contrucoes",
        "contruÃ§Ãµes",
        "engenharia",
        "prev social",
        "previdencia social",
        "previdÃªncia social",
        "imp renda",
        "imposto renda",
        "irrf",
        "ir ",
        "sabado",
        "sÃ¡bado",
        "domingo",
        "camscanner",
        "digitalizado com",
        "local de trabalho",
        "fonte deduc",
        "saldo lancado motivo",
        "saldo lanÃ§ado motivo",
        "quadro de horario",
        "quadro de horÃ¡rio",
        "atividade economica",
        "atividade econÃ´mica",
        "admissao",
        "admissÃ£o",
        "manha tarde extra",
        "manha tarde",
    ]
    if any(b in norm for b in bloqueios):
        return False
    juridicos = [
        r"\bltda\b",
        r"\beireli\b",
        r"\bs\/a\b",
        r"\bsa\b",
        r"\bmei\b",
        r"\bcnpj\b",
    ]
    if any(re.search(p, norm) for p in juridicos):
        return False
    if re.search(r"\bhoras?ex\b", norm):
        return False
    # Bloqueia variacoes OCR de razao social (construcao/construcoes/contrucoes etc.)
    if re.search(r"\bconstr\w*\b", norm) or re.search(r"\bcontru\w*\b", norm):
        return False
    if re.search(r"\bengenhari\w*\b", norm):
        return False
    if re.search(r"\d{3,}", nome):
        return False
    if re.search(r"[:;=|]", nome):
        return False
    if re.search(r"\d", nome):
        return False
    palavras = re.findall(r"[A-Za-zÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡Ã¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§]+", nome)
    if len([p for p in palavras if len(p) >= 3]) < 2:
        return False
    # Evita ruÃ­do OCR com excesso de pontuaÃ§Ã£o/sÃ­mbolos.
    clean_ratio = sum(ch.isalpha() or ch.isspace() or ch in "-'" for ch in nome) / max(1, len(nome))
    if clean_ratio < 0.92:
        return False
    alpha_ratio = sum(ch.isalpha() or ch.isspace() for ch in nome) / max(1, len(nome))
    if alpha_ratio < 0.78:
        return False
    if sum(ch.isalpha() for ch in nome) < 5:
        return False
    return True


def eh_nome_colaborador_valido(nome: str) -> bool:
    nome = normalizar_nome_colaborador(nome)
    if not nome:
        return False
    if _parece_linha_periodo_ou_escala(nome):
        return False
    if nome.lower() == "colaborador sem nome":
        return False
    if len(nome.split()) < 2:
        return False
    if len(nome.split()) > 6:
        return False
    if len(nome) < 8:
        return False
    if nome.isdigit():
        return False
    proibidas = [
        "EMPRESA", "EMPREGADOR", "RAZAO SOCIAL", "RAZÃƒO SOCIAL", "CNPJ", "CPF", "CTPS",
        "FUNCAO", "FUNÃ‡ÃƒO", "CARGO", "PERIODO", "PERÃODO", "JORNADA", "HORARIO", "HORÃRIO",
        "ENTRADA", "SAIDA", "SAÃDA", "ASSINATURA", "REGISTRO", "OCORRENCIAS", "OCORRÃŠNCIAS",
        "TOTAL", "HORAS", "NORMAIS", "EXTRAS", "SALARIO", "SALÃRIO", "RECEBER", "DESCONTO",
        "DESC", "REMUN", "DESC REMUN", "SALDO", "RECEBO", "RECONHECO", "RECONHEÃ‡O", "EXATIDAO", "EXATIDÃƒO", "ATESTACOES", "ATESTAÃ‡Ã•ES",
        "COLABORADOR EMPREGADOR", "DADOS DO COLABORADOR", "DADOS DO EMPREGADOR",
        "COLABORADOR", "EMPREGADO", "FUNCIONARIO", "FUNCIONÃRIO", "NOME", "ASSINATURA DO EMPREGADO",
    ]
    nup = nome.upper()
    if any(p in nup for p in proibidas):
        return False
    if re.search(r"\d{1,2}\s*(SABADO|SÃBADO|DOMINGO|SEGUNDA|TERCA|TERÃ‡A|QUARTA|QUINTA|SEXTA)\b", nup):
        return False
    return _nome_colaborador_valido(nome)


def normalizar_nome_colaborador(nome: str) -> str:
    txt = str(nome or "").replace("\n", " ").replace("\r", " ")
    # Remove artefatos comuns de OCR antes das regras de limpeza.
    txt = re.sub(r"[|_]+", " ", txt)
    txt = re.sub(r"\s*[-â€“â€”]{2,}\s*", " ", txt)
    txt = re.sub(r"^\s*[-â€“â€”]+\s*", "", txt)
    txt = re.sub(r"\s*[-â€“â€”]+\s*$", "", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    txt = re.sub(r"^\d{2,}\s*[-.:]\s*", "", txt)
    txt = re.sub(
        r"\b(CPF|FUNCAO|FUNÃ‡ÃƒO|CARGO|PERIODO|PERÃODO|JORNADA|HORARIO|HORÃRIO|CNPJ|RAZAO SOCIAL|RAZÃƒO SOCIAL|N[ÂºO]\s*REGISTRO)\b.*$",
        "",
        txt,
        flags=re.IGNORECASE,
    )
    txt = re.sub(r"^(FUNCION\.?|FUNCIONARIO|FUNCIONÃRIO|EMPREGADO|NOME|COLABORADOR)\s*[:\-]?\s*", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\b(INSTALADOR(?:A)?|AUXILIAR|AJUDANTE|ENCARREGADO|SUPERVISOR|PEDREIRO|GESSEIRO|SERVENTE)\b.*$", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s+[A-Za-z]$", "", txt).strip()
    return re.sub(r"\s+", " ", txt).strip()


def _parece_linha_periodo_ou_escala(txt: str) -> bool:
    t = _nome_norm(txt)
    if not t:
        return True
    # exemplos recorrentes de falso positivo: "17 SABADO", "2Âª QUINZENA"
    if re.search(r"^\d{1,2}\s*[ÂºÂ°Âª]?\s*(quinzena|sabado|sÃ¡bado|domingo|segunda|terca|terÃ§a|quarta|quinta|sexta)\b", t):
        return True
    if re.search(r"\b(quinzena|sabado|sÃ¡bado|domingo|segunda|terca|terÃ§a|quarta|quinta|sexta)\b", t) and re.search(r"\d{1,2}", t):
        return True
    if re.search(r"\b(entrada|saida|saÃ­da|horario|horÃ¡rio|jornada|intervalo)\b", t):
        return True
    return False


def _similaridade_nome(a: str, b: str) -> float:
    a_n = _nome_norm(a)
    b_n = _nome_norm(b)
    if not a_n or not b_n:
        return 0.0
    wa = set(a_n.split())
    wb = set(b_n.split())
    inter = len(wa.intersection(wb))
    uni = max(1, len(wa.union(wb)))
    return inter / uni


def extrair_nome_colaborador_cartao(texto, linhas_ocr=None, nomes_esperados=None, modo_estrito=False):
    txt = str(texto or "")
    norm = _nome_norm(txt)
    nomes_esperados = nomes_esperados or []
    linhas_ocr = [str(x or "") for x in (linhas_ocr or []) if str(x or "").strip()]

    for nome in nomes_esperados:
        sim = _similaridade_nome(nome, txt)
        if sim >= 0.80 and eh_nome_colaborador_valido(nome):
            nome_limpo = normalizar_nome_colaborador(nome)
            return {"nome": nome_limpo, "nome_encontrado": True, "confianca": round(sim, 3), "origem": "nomes_esperados", "ancora": "similaridade"}

    stop = r"(FUNÃ‡ÃƒO|FUNCAO|PER[IÃ]ODO|JORNADA|HOR[ÃA]RIO|CNPJ|CPF|RAZ[ÃƒA]O SOCIAL|CARGO|EQUIPE|ENDERE[Ã‡C]O|RG|CTPS)"
    padroes = [
        (r"FUNCION\.?\s*[:.]?\s*([A-ZÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡ ]{6,80})", "funcion", "FUNCION"),
        (r"\bEMPREGADO\b\s*[:\-]?\s*([A-ZÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡ ]{6,80})", "empregado", "EMPREGADO"),
        (r"\bEMPREGADO\b\s*[|:/\-]?\s*([A-ZÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡A-Za-zÃ¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§ ]{6,100})", "empregado_pipe", "EMPREGADO"),
        (r"\bEMPREGADO\b[^\nA-Za-zÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡0-9]{0,6}([A-ZÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡][A-Za-zÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡Ã¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§ ]{6,120})", "empregado_livre", "EMPREGADO"),
        (r"NOME(?: DO COLABORADOR)?\s*[:\-]?\s*([A-ZÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡][A-Za-zÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡Ã¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§ ]{6,80})", "nome_digital", "NOME"),
        (r"ASSINATURA DE:\s*([A-ZÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡A-Za-zÃ¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§ ]{6,80})", "assinatura_digital", "ASSINATURA DE"),
    ]
    def _score_nome_candidato(cand: str) -> float:
        c = normalizar_nome_colaborador(cand)
        if not c:
            return 0.0
        palavras = [w for w in re.findall(r"[A-Za-zÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡Ã¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§]+", c) if len(w) >= 2]
        if len(palavras) < 2:
            return 0.0
        letras = sum(ch.isalpha() for ch in c)
        ratio_alpha = letras / max(1, len(c))
        palavras_longas = sum(1 for w in palavras if len(w) >= 3)
        penalidade = 0.0
        if "DIGITALIZADO COM" in c.upper() or "CAMSCANNER" in c.upper():
            penalidade += 1.0
        if re.search(r"\b(EMPREGADOR|RAZAO|SOCIAL|HORARIO|FUNCAO)\b", c.upper()):
            penalidade += 0.7
        return (min(6, palavras_longas) * 0.35) + (ratio_alpha * 0.6) - penalidade

    melhor = None
    for pat, origem, ancora in padroes:
        for m in re.finditer(pat, txt, flags=re.IGNORECASE):
            bruto = re.split(stop, m.group(1), flags=re.IGNORECASE)[0]
            bruto = re.sub(r"^[^A-Za-zÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡Ã¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§]+", "", bruto)
            bruto = re.sub(r"\s*\|.*$", "", bruto)
            bruto = re.sub(r"^\s*(RIO|RIO\.|ÃRIO|ARIO)\s+", "", bruto, flags=re.IGNORECASE)
            bruto = re.split(r"\b(CIDADE|FUNCAO|FUNÃ‡ÃƒO|ADMISSAO|ADMISSÃƒO|CNPJ|CPF|N[ÂºÂ°]\s*ORDEM)\b", bruto, flags=re.IGNORECASE)[0]
            nome_cand = normalizar_nome_colaborador(bruto)
            if _parece_linha_periodo_ou_escala(nome_cand):
                continue
            if not eh_nome_colaborador_valido(nome_cand):
                continue
            score = _score_nome_candidato(nome_cand)
            if (melhor is None) or (score > melhor["score"]):
                melhor = {
                    "nome": nome_cand,
                    "nome_encontrado": True,
                    "confianca": 0.9 if origem != "assinatura_digital" else 0.95,
                    "origem": origem,
                    "ancora": ancora,
                    "score": score,
                }
    if melhor:
        melhor.pop("score", None)
        return melhor

    # Em modo estrito (templates escaneados), nÃ£o usa fallback livre de linhas.
    if modo_estrito:
        return {"nome": "", "nome_encontrado": False, "confianca": 0.0, "origem": "nao_encontrado_estrito", "ancora": ""}

    # Fallback 1: ancora em uma linha e nome na prÃ³xima linha
    linhas = []
    for bloco in [txt, *linhas_ocr]:
        for ln in str(bloco).splitlines():
            ln = re.sub(r"\s+", " ", ln).strip()
            if ln:
                linhas.append(ln)
    anchors = ["FUNCION.", "FUNCIONARIO", "FUNCIONÃRIO", "EMPREGADO", "NOME", "COLABORADOR", "DADOS DO COLABORADOR"]
    for i, ln in enumerate(linhas):
        ln_up = ln.upper()
        if any(a in ln_up for a in anchors):
            # tenta nome na prÃ³pria linha apÃ³s ":"
            parte = re.split(r"[:\-|]", ln, maxsplit=1)
            if len(parte) > 1:
                cand = normalizar_nome_colaborador(parte[1])
                cand = re.split(stop, cand, flags=re.IGNORECASE)[0].strip()
                if _parece_linha_periodo_ou_escala(cand):
                    continue
                if eh_nome_colaborador_valido(cand):
                    return {"nome": cand, "nome_encontrado": True, "confianca": 0.86, "origem": "ocr_linha", "ancora": "linha_ancora"}
            # tenta prÃ³xima linha Ãºtil
            for j in range(i + 1, min(i + 4, len(linhas))):
                prox = normalizar_nome_colaborador(linhas[j])
                prox = re.split(stop, prox, flags=re.IGNORECASE)[0].strip()
                if _parece_linha_periodo_ou_escala(prox):
                    continue
                if eh_nome_colaborador_valido(prox):
                    return {"nome": prox, "nome_encontrado": True, "confianca": 0.84, "origem": "ocr_linha", "ancora": "proxima_linha"}

    # Fallback 2: varredura de linhas com padrÃ£o de nome humano
    for ln in linhas:
        nome_cand = normalizar_nome_colaborador(str(ln or ""))
        if _parece_linha_periodo_ou_escala(nome_cand):
            continue
        if eh_nome_colaborador_valido(nome_cand):
            return {"nome": nome_cand, "nome_encontrado": True, "confianca": 0.75, "origem": "ocr_linha", "ancora": "linha"}
    return {"nome": "", "nome_encontrado": False, "confianca": 0.0, "origem": "nao_encontrado", "ancora": ""}


def classificar_layout_cartao_ponto(texto_ocr, pagina_numero=None):
    t = _nome_norm(texto_ocr or "").upper()
    if all(k in t for k in ["DADOS DO COLABORADOR", "DADOS DO EMPREGADOR", "FOLHA DE PONTO"]) and ("NOME" in t or "REGISTROS" in t):
        return "espelho_digital_colaborador"
    if any(k in t for k in ["ASSINATURA DE:", "LOG DE ASSINATURA", "ASSINADO EM:", "FOTO ASSINATURA"]):
        return "assinatura_digital_log"
    if any(k in t for k in ["FUNCION.:", "FUNCIONÁRIO:", "FUNCIONARIO:", "FUNÇÃO.:", "PERIODO.:", "JORNADA.:"]):
        return "folha_funcion"
    if any(k in t for k in ["2 QUINZENA", "2ª QUINZENA", "2° QUINZENA", "RECEBI O SALDO", "ASSINATURA DO EMPREGADO", "REGISTRO DE OCORRENCIAS", "REGISTRO DE OCORRÊNCIAS"]):
        return "manual_verso"
    if all(k in t for k in ["EMPREGADO", "ENTRADA"]) and any(k in t for k in ["1 QUINZENA", "1ª QUINZENA", "MES", "MÊS", "ANO", "INTERVALO PARA REFEIÇÃO"]):
        return "manual_frente"
    if all(k in t for k in ["NOME", "ENTRADA"]) and any(k in t for k in ["EMPRESA", "DEPARTAMENTO", "FUNCAO", "FUNÇÃO", "DATA", "SAIDA", "SAÍDA"]):
        return "digital_tabela_nome"
    return "desconhecido"


def extrair_nome_por_ancoras_generico(texto_ocr, layout):
    txt = str(texto_ocr or "")
    if not txt:
        return {"nome": "", "nome_encontrado": False, "confianca": 0.0, "origem": "ancora_generica"}
    if layout == "manual_verso":
        return {"nome": "", "nome_encontrado": False, "confianca": 0.0, "origem": "manual_verso_sem_nome"}
    pads = []
    if layout == "espelho_digital_colaborador":
        pads = [
            r"Nome\s+(.+?)\s+Raz[aã]o\s+Social",
            r"Dados do Colaborador.*?Nome\s+(.+?)\s+CPF",
        ]
    elif layout == "assinatura_digital_log":
        pads = [r"Assinatura de:\s*([A-Za-zÀ-ÿ\s]+)"]
    elif layout == "folha_funcion":
        pads = [r"FUNCION\.?:\s*(.+?)(?:FUNÇÃO|FUNCAO|PERIODO|JORNADA|HORÁRIO|HORARIO)"]
    elif layout == "digital_tabela_nome":
        pads = [
            r"NOME\s+(.+?)\s+(?:ADMISSÃO|ADMISSAO|CPF|CTPS|Nº FOLHA|INSCRIÇÃO|INSCRICAO)",
            r"NOME\s*[:\-]?\s*([^\n]{6,120})",
        ]
    else:
        pads = [
            r"EMPREGADO\s*[:\-]?\s*([^\n]{6,120})",
            r"NOME\s*[:\-]?\s*([^\n]{6,120})",
            r"COLABORADOR\s*[:\-]?\s*([^\n]{6,120})",
            r"FUNCION(?:ÁRIO|ARIO|\.?)\s*[:\-]?\s*([^\n]{6,120})",
        ]
    for pat in pads:
        m = re.search(pat, txt, flags=re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        nome = normalizar_nome_colaborador(m.group(1))
        if nome:
            return {"nome": nome, "nome_encontrado": True, "confianca": 0.82, "origem": "ancora_generica"}
    return {"nome": "", "nome_encontrado": False, "confianca": 0.0, "origem": "ancora_generica"}


def nome_colaborador_valido_generico(nome, origem=None, layout=None):
    nome = normalizar_nome_colaborador(nome)
    if not nome:
        return False
    if len(nome.split()) < 2 or len(nome.split()) > 8:
        return False
    if re.search(r"\d", nome):
        return False
    up = nome.upper()
    bloqueios = [
        "EMPREGADOR", "RAZAO", "RAZÃO", "SOCIAL", "LOCAL", "TRABALHO", "ATIVIDADE", "ECONOMICA", "ECONÔMICA",
        "FUNCAO", "FUNÇÃO", "ASSINATURA", "RECEBI", "SALDO", "QUINZENA", "ENTRADA", "SAIDA", "SAÍDA",
        "HORARIO", "HORÁRIO", "JORNADA", "PERIODO", "PERÍODO", "CNPJ", "CPF", "CTPS", "LTDA", "EIRELI", "EPP", "ME", "S/A",
        "DATA", "REGISTROS", "TOTAL", "HORAS", "NORMAIS", "EXTRAS",
    ]
    if any(b in up for b in bloqueios):
        return False
    # Origem visual não depende de evidência no OCR local.
    if str(origem or "").strip().lower() == "openai_vision_pagina_inteira":
        return True
    return eh_nome_colaborador_valido(nome)


def classificar_pagina_cartao_ponto(texto, resultado_nome, resultado_assinatura, layout=None):
    t = (texto or "").upper()
    layout_n = str(layout or "").strip().lower()
    if bool(resultado_nome.get("nome_encontrado")):
        if layout_n in {"manual_verso", "manual_assinatura_diaria"}:
            return "verso_continuacao"
        return "pagina_com_nome"
    if all(k in t for k in ["ASSINATURA DE:", "LOG DE ASSINATURA", "ASSINADO EM:"]):
        return "log_assinatura_digital"
    if any(k in t for k in ["2Âª QUINZENA", "2Â° QUINZENA", "2 QUINZENA", "RECEBI O SALDO", "ASSINATURA DO EMPREGADO", "REGISTRO DE OCORRÃŠNCIAS", "REGISTRO DE OCORRENCIAS"]):
        return "verso_continuacao"
    if bool(resultado_assinatura.get("assinatura")):
        return "pagina_assinatura_sem_nome"
    return "pagina_sem_nome_ignorar"


def _perfil_layout_cartao(layout: str) -> str:
    l = str(layout or "").strip().lower()
    if l == "log_assinatura_digital":
        return "digital_log"
    if l == "cartao_digital_texto_nativo":
        return "digital_nativo"
    if l in {"manual_frente", "manual_verso", "manual_assinatura_diaria"}:
        return "manual_frente_verso"
    if l in {"desconhecido", "imagem_escaneada_generica"}:
        return "escaneado_generico"
    return "generico"


def _eh_verso_por_perfil(pagina_item, atual, perfil_forcado="auto"):
    pagina = int(pagina_item.get("pagina") or 0)
    if not atual:
        return False
    perfil_forcado = str(perfil_forcado or "auto").strip().lower()
    if perfil_forcado == "pagina_unica":
        return False
    perfil = _perfil_layout_cartao(pagina_item.get("layout"))
    layout = str(pagina_item.get("layout") or "").strip().lower()
    tem_ass = bool(pagina_item.get("assinatura"))
    qtd_h = int(pagina_item.get("qtd_horarios") or 0)
    consecutiva = pagina == (max(atual.get("paginas", [0])) + 1)

    # Perfil manual frente/verso: verso esperado na pagina par subsequente com assinatura.
    if perfil_forcado == "duas_paginas":
        return bool(consecutiva and (pagina % 2 == 0) and tem_ass)

    if perfil == "manual_frente_verso":
        if not consecutiva:
            return False
        if layout in {"manual_verso", "manual_assinatura_diaria"}:
            return pagina % 2 == 0
        return (pagina % 2 == 0) and tem_ass and qtd_h <= 4

    # Perfil escaneado generico: conservador para evitar colapsar nomes.
    if perfil == "escaneado_generico":
        if not consecutiva:
            return False
        if pagina % 2 != 0 or (not tem_ass):
            return False
        return bool(qtd_h <= 4)

    return False


def _nome_parece_artefato_template(nome: str) -> bool:
    t = _nome_norm(nome)
    if not t:
        return True
    bloqueios = [
        "local do trabalho",
        "fonte",
        "deducoes",
        "deducoes ii",
        "quinzena",
        "recebi",
        "mencionado",
        "acima",
        "pago",
        "pagamento",
        "saida",
        "entrada",
        "intervalo",
        "repouso",
        "descontos",
        "salario familia",
        "saldo",
        "saldo a receber",
        "total dos descontos",
        "n ordem",
        "empregador",
        "razao social",
        "atividade economica",
    ]
    if any(b in t for b in bloqueios):
        return True
    # Muito ruÃ­do/sÃ­mbolos e poucas palavras reais.
    palavras = re.findall(r"[a-zÃ¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§]+", t)
    if len(palavras) < 2:
        return True
    if sum(ch.isalpha() for ch in str(nome or "")) < 8:
        return True
    return False


def _nome_confiavel_para_template_ruidoso(nome: str) -> bool:
    """
    Regra conservadora para PDF muito ruidoso:
    sÃ³ aceita nome com padrÃ£o humano claro.
    """
    n = normalizar_nome_colaborador(nome)
    if not eh_nome_colaborador_valido(n):
        return False
    if _nome_parece_artefato_template(n):
        return False
    palavras = [p for p in re.findall(r"[A-Za-zÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡Ã¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§]+", n) if p]
    if len(palavras) < 2 or len(palavras) > 5:
        return False
    if len([p for p in palavras if len(p) >= 3]) < 2:
        return False
    if len(palavras[0]) <= 3 and palavras[0].upper() not in {"DA", "DE", "DO", "DAS", "DOS"}:
        return False
    # Evita tokens tÃ­picos de ruÃ­do OCR.
    suspeitos = {
        "rude", "zhufna", "lboleala", "elbam", "qeirat", "aouinzenao", "case", "also",
        "amelo", "zarho", "dsi", "nuts", "rana", "cones",
    }
    if any(_nome_norm(p) in suspeitos for p in palavras):
        return False
    return True


def _inferir_modo_leitura(resultados_paginas):
    """
    InferÃªncia estÃ¡vel por documento:
    - `duas_paginas`: frente em Ã­mpar (nome) e verso em par (assinatura)
    - `pagina_unica`: nome+assinatura na mesma pÃ¡gina
    """
    itens = sorted(resultados_paginas, key=lambda x: int(x.get("pagina") or 0))
    if not itens:
        return "pagina_unica"

    odd_nome = 0
    odd_total = 0
    even_ass_sem_nome = 0
    even_total = 0
    pares_validos = 0

    by_page = {int(p.get("pagina") or 0): p for p in itens}
    max_pg = max(by_page.keys()) if by_page else 0

    for pg, p in by_page.items():
        nome_ok = bool((p.get("nome") or "").strip())
        ass_ok = bool(p.get("assinatura"))
        if pg % 2 == 1:
            odd_total += 1
            if nome_ok:
                odd_nome += 1
            prox = by_page.get(pg + 1)
            if prox:
                prox_nome = bool((prox.get("nome") or "").strip())
                prox_ass = bool(prox.get("assinatura"))
                if nome_ok and (not prox_nome) and prox_ass:
                    pares_validos += 1
        else:
            even_total += 1
            if ass_ok and (not nome_ok):
                even_ass_sem_nome += 1

    if max_pg >= 4 and pares_validos >= 1:
        odd_ratio = (odd_nome / odd_total) if odd_total else 0.0
        even_ratio = (even_ass_sem_nome / even_total) if even_total else 0.0
        if odd_ratio >= 0.6 and even_ratio >= 0.4:
            return "duas_paginas"
    # Fallback simples por volume/paridade para PDFs escaneados frente/verso.
    if max_pg >= 4 and (max_pg % 2 == 0):
        return "duas_paginas"
    return "pagina_unica"


def _fallback_duplas_frente_verso(caminho_arquivo, resultados_paginas, competencia_esperada=None):
    """
    Fallback final para PDF ruim:
    agrupa em duplas fixas [1,2], [3,4], ... e tenta nome agressivo na Ã­mpar.
    """
    itens = sorted(resultados_paginas, key=lambda x: int(x.get("pagina") or 0))
    by_page = {int(p.get("pagina") or 0): p for p in itens}
    colaboradores = []
    avisos = []
    max_pg = max(by_page.keys()) if by_page else 0

    for pg in range(1, max_pg + 1, 2):
        frente = by_page.get(pg)
        verso = by_page.get(pg + 1)
        if not frente:
            continue
        nome = normalizar_nome_colaborador(frente.get("nome") or "")
        if not eh_nome_colaborador_valido(nome):
            # OCR agressivo de nome focado na faixa superior da pÃ¡gina Ã­mpar (frente).
            nome_agressivo = _extrair_nome_empregado_faixa(caminho_arquivo, pg)
            nome = normalizar_nome_colaborador(nome_agressivo or frente.get("nome_bruto") or nome)
        if not eh_nome_colaborador_valido(nome):
            avisos.append(f"Dupla [{pg},{pg+1}] ignorada: nome nÃ£o encontrado na pÃ¡gina Ã­mpar.")
            continue

        comp = (frente.get("competencia") or "").strip()
        if not comp and verso:
            comp = (verso.get("competencia") or "").strip()
        comp_herdada = False
        if not comp and competencia_esperada:
            comp = competencia_esperada
            comp_herdada = True

        qtd = int(frente.get("qtd_horarios") or 0) + int((verso or {}).get("qtd_horarios") or 0)
        marc = bool(frente.get("marcacoes_encontradas") or (verso or {}).get("marcacoes_encontradas") or qtd >= 8)
        ass = bool((verso or {}).get("assinatura") or frente.get("assinatura"))
        ass_tipo = (verso or {}).get("assinatura_tipo") or frente.get("assinatura_tipo") or ("ausente" if not ass else "inconclusiva")
        ass_origem = (verso or {}).get("assinatura_origem") or frente.get("assinatura_origem") or "nao_identificada"
        ass_conf = max(float(frente.get("assinatura_confianca") or 0.0), float((verso or {}).get("assinatura_confianca") or 0.0))
        ass_pg = (verso or {}).get("assinatura_pagina") or (pg + 1 if verso else frente.get("assinatura_pagina"))
        ass_zona = (verso or {}).get("assinatura_zona") or frente.get("assinatura_zona") or "desconhecida"

        comp_ok = bool(comp and (not competencia_esperada or comp == competencia_esperada))
        score, status = _score_status_colaborador(True, comp_ok, marc, ass)
        motivos = []
        avisos_col = []
        if comp_herdada:
            avisos_col.append("CompetÃªncia herdada do formulÃ¡rio por ausÃªncia no documento.")
        if not ass:
            motivos.append("Assinatura/rubrica ausente")
        if not marc:
            motivos.append("MarcaÃ§Ãµes insuficientes")
        if not comp_ok:
            motivos.append(f"CompetÃªncia divergente/ausente (lida: {comp or '-'} | esperada: {competencia_esperada or '-'})")

        colaboradores.append({
            "nome": nome,
            "colaborador": nome,
            "paginas": [pg] + ([pg + 1] if verso else []),
            "layout": frente.get("layout") or "generico",
            "perfil_layout": _perfil_layout_cartao(frente.get("layout")),
            "competencia": comp or "-",
            "periodo_inicio": frente.get("periodo_inicio", ""),
            "periodo_fim": frente.get("periodo_fim", ""),
            "competencia_ok": comp_ok,
            "marcacoes": marc,
            "marcacoes_encontradas": marc,
            "qtd_horarios": qtd,
            "assinatura": ass,
            "assinatura_tipo": ass_tipo,
            "assinatura_origem": ass_origem,
            "assinatura_confianca": ass_conf,
            "assinatura_bbox": (verso or {}).get("assinatura_bbox") or frente.get("assinatura_bbox"),
            "assinatura_pagina": ass_pg,
            "assinatura_zona": ass_zona,
            "assinatura_motivo": (verso or {}).get("assinatura_motivo") or frente.get("assinatura_motivo") or "",
            "motivos": motivos,
            "avisos": avisos_col,
            "datado": True,
            "status": status,
            "score": score,
        })
    return colaboradores, avisos


def _nome_arquivo_eh_template_fixo(caminho_arquivo: str) -> bool:
    base = os.path.basename(str(caminho_arquivo or ""))
    up = unicodedata.normalize("NFKD", base).encode("ASCII", "ignore").decode("ASCII").upper()
    return ("CARTAO PONTO" in up) and up.endswith(".PDF")


def _nome_forte_para_perfil(nome: str, perfil: str, origem: str, confianca: float) -> bool:
    nome = str(nome or "").strip()
    origem = str(origem or "").strip().lower()
    conf = float(confianca or 0.0)
    if not nome:
        return False
    if "ï¿½" in nome:
        return False
    nome_n = _nome_norm(nome)
    if any(k in nome_n for k in [
        "prev social", "imposto renda", "imp renda", "local de trabalho",
        "depart", "quadro de horario", "saldo lancado motivo", "atividade economica"
    ]):
        return False
    palavras = [w for w in re.findall(r"[A-Za-zÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡Ã¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§]+", nome) if len(w) >= 3]
    if perfil != "escaneado_generico":
        return True
    # Em escaneado genÃ©rico, evita criar colaborador com OCR fraco.
    origem_forte = origem in {
        "funcion",
        "empregado",
        "empregado_pipe",
        "nome_digital",
        "nomes_esperados",
        "ocr_linha",
    }
    if len(palavras) >= 3 and conf >= 0.84:
        return True
    if len(palavras) >= 2 and conf >= 0.92 and origem_forte:
        return True
    return False


def _extrair_nome_relaxado_emergencial(texto: str) -> str:
    t = str(texto or "")
    # 1) Prioriza campo "EMPREGADO ..."
    m = re.search(
        r"\bEMPREGADO\b\s*[:|.\-]*\s*([A-ZÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡a-zÃ¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§ ]{6,120})",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        cand = normalizar_nome_colaborador(m.group(1))
        cand = re.split(r"\b(CIDADE|FUNCAO|FUNÃ‡ÃƒO|CNPJ|CPF|LOCAL|ADMISSAO|ADMISSÃƒO)\b", cand, flags=re.IGNORECASE)[0].strip()
        if len(cand.split()) >= 2 and sum(ch.isalpha() for ch in cand) >= 8:
            return cand

    # 2) Procura linha imediatamente apÃ³s "EMPREGADO"
    linhas = [re.sub(r"\s+", " ", ln).strip() for ln in t.splitlines() if ln and ln.strip()]
    for i, ln in enumerate(linhas):
        if "EMPREGADO" in ln.upper():
            for j in range(i, min(i + 3, len(linhas))):
                trecho = linhas[j]
                if j == i:
                    partes = re.split(r"EMPREGADO\s*[:|.\-]*", trecho, flags=re.IGNORECASE)
                    trecho = partes[-1] if len(partes) > 1 else ""
                cand = normalizar_nome_colaborador(trecho)
                cand = re.split(r"\b(CIDADE|FUNCAO|FUNÃ‡ÃƒO|CNPJ|CPF|LOCAL|ADMISSAO|ADMISSÃƒO)\b", cand, flags=re.IGNORECASE)[0].strip()
                if len(cand.split()) >= 2 and sum(ch.isalpha() for ch in cand) >= 8:
                    return cand
    return ""




def _extrair_nome_empregado_imagem_agressivo(caminho_arquivo: str, pagina: int) -> str:
    try:
        img = renderizar_pagina_pdf(caminho_arquivo, max(0, int(pagina) - 1), dpi=420)
        if img is None:
            return ""
        arr = np.array(img)
        if arr.ndim == 3:
            gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        else:
            gray = arr
        h, w = gray.shape[:2]
        y1, y2 = int(h * 0.10), int(h * 0.42)
        crop = gray[y1:y2, 0:w]
        if crop.size == 0:
            return ""

        candidatos = []
        for block_size, c_val in [(31, 8), (41, 10), (51, 12)]:
            th = cv2.adaptiveThreshold(crop, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c_val)
            txt = pytesseract.image_to_string(th, lang='por', config='--oem 1 --psm 6 -c preserve_interword_spaces=1')
            cand = _extrair_nome_relaxado_emergencial(txt)
            if cand:
                candidatos.append(cand)

        if candidatos:
            candidatos.sort(key=lambda x: (len(x.split()), len(x)), reverse=True)
            return candidatos[0]
    except Exception as exc:
        print(f"[PONTO] Falha OCR agressivo nome pagina {pagina}: {exc}")
    return ""



def _extrair_nome_em_pagina_isolada(caminho_arquivo: str, pagina: int) -> str:
    try:
        img = renderizar_pagina_pdf(caminho_arquivo, max(0, int(pagina) - 1), dpi=360)
        rec = recortar_area_documento_cartao(img)
        base = rec.get("imagem_recortada")
        if base is None:
            return ""
        recortes = gerar_recortes_cartao_ponto(base)
        topo = recortes.get("topo")
        if topo is None:
            return ""
        arr = np.array(topo)
        if arr.ndim == 3:
            gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        else:
            gray = arr
        txts = []
        for block_size, c_val in [(31, 8), (41, 10), (51, 12)]:
            th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c_val)
            txts.append(pytesseract.image_to_string(th, lang='por', config='--oem 1 --psm 6 -c preserve_interword_spaces=1'))
        txts.append(pytesseract.image_to_string(gray, lang='por', config='--oem 1 --psm 6 -c preserve_interword_spaces=1'))
        for tx in txts:
            cand = _extrair_nome_relaxado_emergencial(tx)
            if cand and eh_nome_colaborador_valido(cand):
                return normalizar_nome_colaborador(cand)
    except Exception as exc:
        print(f"[PONTO] Falha extracao isolada pagina {pagina}: {exc}")
    return ""


def _extrair_nome_empregado_faixa(caminho_arquivo: str, pagina: int) -> str:
    """
    Pipeline dedicado para cartÃ£o escaneado ruidoso:
    recorta a faixa superior onde normalmente estÃ¡ "EMPREGADO" e extrai sÃ³ nome.
    """
    try:
        img = renderizar_pagina_pdf(caminho_arquivo, max(0, int(pagina) - 1), dpi=420)
        if img is None:
            return ""
        arr = np.array(img)
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY) if arr.ndim == 3 else arr
        h, w = gray.shape[:2]
        # Faixa onde costuma ficar a linha do empregado nesse template.
        y1, y2 = int(h * 0.18), int(h * 0.42)
        x1, x2 = int(w * 0.02), int(w * 0.98)
        faixa = gray[y1:y2, x1:x2]
        if faixa.size == 0:
            return ""

        candidatos = []
        for block_size, c_val in [(31, 8), (41, 10), (51, 12)]:
            th = cv2.adaptiveThreshold(
                faixa,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                block_size,
                c_val,
            )
            txt = pytesseract.image_to_string(
                th,
                lang="por",
                config="--oem 1 --psm 6 -c preserve_interword_spaces=1",
            )
            m = re.search(
                r"\bEMPREGADO\b\s*[:\-|.]?\s*([A-ZÃÃ‰ÃÃ“ÃšÃ‚ÃŠÃ”ÃƒÃ•Ã‡a-zÃ¡Ã©Ã­Ã³ÃºÃ¢ÃªÃ´Ã£ÃµÃ§ ]{6,120})",
                txt,
                flags=re.IGNORECASE,
            )
            cand = m.group(1) if m else _extrair_nome_relaxado_emergencial(txt)
            cand = normalizar_nome_colaborador(cand)
            cand = re.split(
                r"\b(CIDADE|FUNCAO|FUNÃ‡ÃƒO|ADMISSAO|ADMISSÃƒO|CNPJ|CPF|N[ÂºÂ°]\s*ORDEM)\b",
                cand,
                flags=re.IGNORECASE,
            )[0].strip()
            if eh_nome_colaborador_valido(cand) and (not _nome_parece_artefato_template(cand)):
                candidatos.append(cand)
        if candidatos:
            candidatos.sort(key=lambda x: (len(x.split()), len(x)), reverse=True)
            return candidatos[0]
    except Exception as exc:
        print(f"[PONTO] Falha faixa EMPREGADO p{pagina}: {exc}")
    return ""

def _criar_item_colaborador_de_pagina(p, nome, competencia_esperada=None):
    comp_lida = (p.get("competencia") or "").strip()
    comp_herdada = ""
    avisos_item = list(p.get("avisos", []))
    if (not comp_lida) and competencia_esperada:
        comp_herdada = competencia_esperada
        avisos_item.append("CompetÃªncia herdada do formulÃ¡rio por ausÃªncia no documento.")
    return {
        "nome": nome,
        "colaborador": nome,
        "paginas": [int(p.get("pagina") or 0)],
        "layout": p.get("layout") or "generico",
        "perfil_layout": _perfil_layout_cartao(p.get("layout")),
        "competencia": comp_lida or comp_herdada or "-",
        "periodo_inicio": p.get("periodo_inicio", ""),
        "periodo_fim": p.get("periodo_fim", ""),
        "competencia_ok": bool((comp_lida or comp_herdada) and (not competencia_esperada or (comp_lida or comp_herdada) == competencia_esperada)),
        "marcacoes": bool(p.get("marcacoes_encontradas")),
        "marcacoes_encontradas": bool(p.get("marcacoes_encontradas")),
        "qtd_horarios": int(p.get("qtd_horarios") or 0),
        "indicio_rasura_horario_britanico": bool(p.get("indicio_rasura_horario_britanico")),
        "rasura_motivo": p.get("rasura_motivo") or "",
        "assinatura": bool(p.get("assinatura")),
        "assinatura_tipo": p.get("assinatura_tipo") or "ausente",
        "assinatura_origem": p.get("assinatura_origem") or "nao_identificada",
        "assinatura_confianca": float(p.get("assinatura_confianca") or 0.0),
        "assinatura_bbox": p.get("assinatura_bbox"),
        "assinatura_pagina": p.get("assinatura_pagina"),
        "assinatura_zona": p.get("assinatura_zona", "desconhecida"),
        "assinatura_motivo": p.get("assinatura_motivo") or "",
        "motivos": [],
        "avisos": avisos_item,
        "datado": True,
    }


def consolidar_colaboradores_template_fixo(resultados_paginas, competencia_esperada=None, permitir_nome_fraco=False, template_ruidoso=False):
    paginas = sorted(resultados_paginas, key=lambda x: int(x.get("pagina") or 0))
    colaboradores = []
    avisos_globais = []
    i = 0
    while i < len(paginas):
        p = paginas[i]
        pagina_num = int(p.get("pagina") or 0)
        nome = normalizar_nome_colaborador(p.get("nome") or "")
        if not eh_nome_colaborador_valido(nome):
            nome_relaxado = _extrair_nome_relaxado_emergencial(
                f"{p.get('texto_topo') or ''}\n{p.get('texto_pagina') or ''}\n{p.get('nome_bruto') or ''}"
            )
            if eh_nome_colaborador_valido(nome_relaxado):
                nome = normalizar_nome_colaborador(nome_relaxado)

        if (not eh_nome_colaborador_valido(nome)) and permitir_nome_fraco:
            nome_bruto = normalizar_nome_colaborador(p.get("nome_bruto") or "")
            if len(nome_bruto.split()) >= 2 and sum(ch.isalpha() for ch in nome_bruto) >= 8:
                nome = nome_bruto

        if not eh_nome_colaborador_valido(nome):
            avisos_globais.append(f"PÃ¡gina {pagina_num} ignorada por nÃ£o possuir nome vÃ¡lido.")
            i += 1
            continue
        if template_ruidoso and (not _nome_confiavel_para_template_ruidoso(nome)):
            avisos_globais.append(f"PÃ¡gina {pagina_num} ignorada por nome nÃ£o confiÃ¡vel no template ruidoso.")
            i += 1
            continue

        item = _criar_item_colaborador_de_pagina(p, nome, competencia_esperada=competencia_esperada)

        # Se houver segunda pÃ¡gina sem nome vÃ¡lido e com assinatura, vincula como verso.
        if i + 1 < len(paginas):
            prox = paginas[i + 1]
            prox_nome = normalizar_nome_colaborador(prox.get("nome") or "")
            prox_nome_valido = eh_nome_colaborador_valido(prox_nome)
            prox_ass = bool(prox.get("assinatura"))
            if (not prox_nome_valido) and prox_ass:
                prox_num = int(prox.get("pagina") or 0)
                item["paginas"] = sorted(set(item["paginas"] + [prox_num]))
                item["qtd_horarios"] = int(item.get("qtd_horarios") or 0) + int(prox.get("qtd_horarios") or 0)
                item["marcacoes_encontradas"] = bool(
                    item["qtd_horarios"] >= 8 or item.get("marcacoes_encontradas") or prox.get("marcacoes_encontradas")
                )
                item["assinatura"] = True
                item["assinatura_tipo"] = prox.get("assinatura_tipo") or item.get("assinatura_tipo")
                item["assinatura_origem"] = prox.get("assinatura_origem") or item.get("assinatura_origem")
                item["assinatura_confianca"] = max(
                    float(item.get("assinatura_confianca") or 0.0),
                    float(prox.get("assinatura_confianca") or 0.0),
                )
                item["assinatura_pagina"] = prox.get("assinatura_pagina") or prox_num
                avisos_globais.append(f"PÃ¡gina {prox_num} vinculada como verso de assinatura da pÃ¡gina {pagina_num}.")
                i += 1

        colaboradores.append(item)
        i += 1

    colaboradores_final = []
    for c in colaboradores:
        nome_ok = eh_nome_colaborador_valido(c.get("nome", ""))
        if not nome_ok:
            continue
        comp_ok = bool((c.get("competencia") or "").strip() and c.get("competencia") != "-" and (not competencia_esperada or c.get("competencia") == competencia_esperada))
        marc_ok = bool(c.get("marcacoes_encontradas") or c.get("marcacoes")) and (not bool(c.get("indicio_rasura_horario_britanico")))
        ass_ok = bool(c.get("assinatura"))
        score, status_item = _score_status_colaborador(nome_ok, comp_ok, marc_ok, ass_ok)
        c["competencia_ok"] = comp_ok
        c["status"] = status_item
        c["score"] = score
        if not comp_ok:
            comp_lida = (c.get("competencia") or "-").strip() or "-"
            comp_ref = (competencia_esperada or "-").strip() or "-"
            c.setdefault("motivos", []).append(f"CompetÃªncia divergente/ausente (lida: {comp_lida} | esperada: {comp_ref})")
        if not marc_ok:
            c.setdefault("motivos", []).append("MarcaÃ§Ãµes insuficientes")
        if c.get("indicio_rasura_horario_britanico"):
            c.setdefault("motivos", []).append(c.get("rasura_motivo") or "IndÃ­cio de rasura por horÃ¡rio rÃ­gido.")
        if not ass_ok:
            c.setdefault("motivos", []).append("Assinatura/rubrica ausente")
        colaboradores_final.append(c)
    return colaboradores_final, avisos_globais

def consolidar_colaboradores_cartao_ponto(resultados_paginas, competencia_esperada=None, perfil_leitura="auto"):
    colaboradores = []
    avisos_globais = []
    atual = None
    perfil_leitura = str(perfil_leitura or "auto").strip().lower()
    regra_paridade_frente_verso = perfil_leitura == "duas_paginas"  # impar=frente(nome), par=verso(assinatura)

    for p in sorted(resultados_paginas, key=lambda x: int(x.get("pagina") or 0)):
        tipo = p.get("tipo_pagina")
        pagina = int(p.get("pagina") or 0)
        if tipo == "pagina_com_nome":
            nome = normalizar_nome_colaborador(p.get("nome", ""))
            perfil = _perfil_layout_cartao(p.get("layout"))
            nome_origem = p.get("nome_origem", "")
            nome_confianca = float(p.get("nome_confianca") or 0.0)
            if not nome_colaborador_valido_generico(nome, origem=nome_origem, layout=p.get("layout")):
                avisos_globais.append(f"Registro descartado porque nÃ£o possui nome vÃ¡lido (pÃ¡gina {pagina}).")
                print(f"[CARTAO] Registro descartado: nome invÃ¡lido (pÃ¡gina {pagina})")
                atual = None
                continue
            if _nome_parece_artefato_template(nome):
                avisos_globais.append(f"Registro descartado por artefato de template (pÃ¡gina {pagina}).")
                atual = None
                continue
            origem_vision = str(nome_origem or "").strip().lower() == "openai_vision_pagina_inteira"
            exigir_nome_forte = (not origem_vision) and (not (regra_paridade_frente_verso and (pagina % 2 == 1)))
            if exigir_nome_forte and not _nome_forte_para_perfil(nome, perfil, nome_origem, nome_confianca):
                avisos_globais.append(
                    f"Registro descartado por baixa confiabilidade do nome no perfil '{perfil}' (pÃ¡gina {pagina})."
                )
                atual = None
                continue
            if _eh_verso_por_perfil(p, atual, perfil_forcado=perfil_leitura):
                atual["paginas"] = sorted(set(atual.get("paginas", []) + [pagina]))
                atual["qtd_horarios"] = int(atual.get("qtd_horarios") or 0) + int(p.get("qtd_horarios") or 0)
                atual["marcacoes_encontradas"] = bool(
                    atual["qtd_horarios"] >= 8
                    or atual.get("marcacoes_encontradas")
                    or p.get("marcacoes_encontradas")
                )
                atual["assinatura"] = True
                atual["assinatura_tipo"] = p.get("assinatura_tipo") or atual.get("assinatura_tipo")
                atual["assinatura_origem"] = p.get("assinatura_origem") or atual.get("assinatura_origem")
                atual["assinatura_confianca"] = max(
                    float(atual.get("assinatura_confianca") or 0),
                    float(p.get("assinatura_confianca") or 0),
                )
                atual["assinatura_pagina"] = p.get("assinatura_pagina") or pagina
                avisos_globais.append(
                    f"PÃ¡gina {pagina} vinculada como verso por perfil '{_perfil_layout_cartao(p.get('layout'))}'."
                )
                print(f"[CARTAO][P{pagina}] agrupada_como_verso=True assinatura_detectada={bool(p.get('assinatura'))}")
                continue
            if regra_paridade_frente_verso and (pagina % 2 == 0) and atual is not None:
                # Em cartÃµes frente/verso parametrizados, pÃ¡gina par nÃ£o abre novo colaborador.
                # Ela deve atuar como verso da pÃ¡gina Ã­mpar anterior.
                atual["paginas"] = sorted(set(atual.get("paginas", []) + [pagina]))
                atual["qtd_horarios"] = int(atual.get("qtd_horarios") or 0) + int(p.get("qtd_horarios") or 0)
                atual["marcacoes_encontradas"] = bool(
                    atual["qtd_horarios"] >= 8
                    or atual.get("marcacoes_encontradas")
                    or p.get("marcacoes_encontradas")
                )
                if p.get("assinatura"):
                    atual["assinatura"] = True
                    atual["assinatura_tipo"] = p.get("assinatura_tipo") or atual.get("assinatura_tipo")
                    atual["assinatura_origem"] = p.get("assinatura_origem") or atual.get("assinatura_origem")
                    atual["assinatura_confianca"] = max(
                        float(atual.get("assinatura_confianca") or 0),
                        float(p.get("assinatura_confianca") or 0),
                    )
                    atual["assinatura_pagina"] = p.get("assinatura_pagina") or pagina
                avisos_globais.append(f"PÃ¡gina {pagina} (par) tratada como verso por parÃ¢metro de paridade.")
                print(f"[CARTAO][P{pagina}] agrupada_como_verso=True assinatura_detectada={bool(p.get('assinatura'))}")
                continue
            # Heuristica frente/verso: alguns versos recebem "nome" falso por OCR.
            if (
                atual is not None
                and str(p.get("layout") or "").strip().lower() in {"manual_verso", "manual_assinatura_diaria"}
                and pagina == (max(atual.get("paginas", [0])) + 1)
                and _similaridade_nome(atual.get("nome", ""), nome) < 0.80
            ):
                atual["paginas"] = sorted(set(atual.get("paginas", []) + [pagina]))
                atual["qtd_horarios"] = int(atual.get("qtd_horarios") or 0) + int(p.get("qtd_horarios") or 0)
                atual["marcacoes_encontradas"] = bool(
                    atual["qtd_horarios"] >= 8
                    or atual.get("marcacoes_encontradas")
                    or p.get("marcacoes_encontradas")
                )
                if p.get("assinatura"):
                    atual["assinatura"] = True
                    atual["assinatura_tipo"] = p.get("assinatura_tipo") or atual.get("assinatura_tipo")
                    atual["assinatura_origem"] = p.get("assinatura_origem") or atual.get("assinatura_origem")
                    atual["assinatura_confianca"] = max(
                        float(atual.get("assinatura_confianca") or 0),
                        float(p.get("assinatura_confianca") or 0),
                    )
                    atual["assinatura_pagina"] = p.get("assinatura_pagina") or pagina
                avisos_globais.append(
                    f"PÃ¡gina {pagina} tratada como verso do colaborador anterior; nome OCR descartado: '{nome}'."
                )
                print(f"[CARTAO][P{pagina}] agrupada_como_verso=True assinatura_detectada={bool(p.get('assinatura'))}")
                continue
            item = {
                # CompetÃªncia: se ausente no documento, herda do formulÃ¡rio e registra aviso.
                "competencia": (p.get("competencia") or "").strip() or (competencia_esperada or "-"),
                "nome": nome,
                "colaborador": nome,
                "paginas": [pagina],
                "layout": p.get("layout") or "generico",
                "layout_origem": p.get("layout") or "generico",
                "nome_origem": nome_origem or "",
                "perfil_layout": perfil,
                "periodo_inicio": p.get("periodo_inicio", ""),
                "periodo_fim": p.get("periodo_fim", ""),
                "competencia_ok": bool((((p.get("competencia") or "").strip() or (competencia_esperada or ""))) and (not competencia_esperada or (((p.get("competencia") or "").strip() or (competencia_esperada or "")) == competencia_esperada))),
                "marcacoes": bool(p.get("marcacoes_encontradas")),
                "marcacoes_encontradas": bool(p.get("marcacoes_encontradas")),
                "qtd_horarios": int(p.get("qtd_horarios") or 0),
                "indicio_rasura_horario_britanico": bool(p.get("indicio_rasura_horario_britanico")),
                "rasura_motivo": p.get("rasura_motivo") or "",
                "assinatura": bool(p.get("assinatura")),
                "assinatura_tipo": p.get("assinatura_tipo") or "ausente",
                "assinatura_origem": p.get("assinatura_origem") or "nao_identificada",
                "assinatura_confianca": float(p.get("assinatura_confianca") or 0.0),
                "assinatura_bbox": p.get("assinatura_bbox"),
                "assinatura_pagina": p.get("assinatura_pagina"),
                "assinatura_zona": p.get("assinatura_zona", "desconhecida"),
                "assinatura_motivo": p.get("assinatura_motivo") or "",
                "motivos": [],
                "avisos": list(p.get("avisos", [])) + (["CompetÃªncia herdada do formulÃ¡rio por ausÃªncia no documento."] if (not (p.get("competencia") or "").strip() and competencia_esperada) else []),
                "datado": True,
            }
            colaboradores.append(item)
            atual = item
            print(f"[CARTAO] Colaborador adicionado ao resultado final: {nome}")
            continue

        if tipo == "verso_continuacao":
            if not _eh_verso_por_perfil(p, atual, perfil_forcado=perfil_leitura):
                avisos_globais.append(
                    f"PÃ¡gina {pagina} marcada como verso, mas rejeitada pela regra do perfil '{_perfil_layout_cartao(p.get('layout'))}'."
                )
                atual = None
                continue
            if atual is None:
                avisos_globais.append(f"PÃ¡gina {pagina} parece verso, mas nÃ£o havia pÃ¡gina anterior com nome.")
                continue
            atual["paginas"] = sorted(set(atual.get("paginas", []) + [pagina]))
            atual["qtd_horarios"] = int(atual.get("qtd_horarios") or 0) + int(p.get("qtd_horarios") or 0)
            atual["marcacoes_encontradas"] = bool(atual["qtd_horarios"] >= 8 or atual.get("marcacoes_encontradas") or p.get("marcacoes_encontradas"))
            if p.get("assinatura"):
                atual["assinatura"] = True
                atual["assinatura_tipo"] = p.get("assinatura_tipo") or atual.get("assinatura_tipo")
                atual["assinatura_origem"] = p.get("assinatura_origem") or atual.get("assinatura_origem")
                atual["assinatura_confianca"] = max(float(atual.get("assinatura_confianca") or 0), float(p.get("assinatura_confianca") or 0))
                atual["assinatura_pagina"] = p.get("assinatura_pagina") or pagina
            avisos_globais.append(f"PÃ¡gina {pagina} vinculada como verso do colaborador anterior.")
            print(f"[CARTAO][P{pagina}] agrupada_como_verso=True assinatura_detectada={bool(p.get('assinatura'))}")
            continue

        if tipo == "log_assinatura_digital":
            nome_log = normalizar_nome_colaborador(p.get("nome") or "")
            alvo = None
            if atual and _similaridade_nome(atual.get("nome"), nome_log) >= 0.80:
                alvo = atual
            if alvo is None and eh_nome_colaborador_valido(nome_log):
                for c in colaboradores:
                    if _similaridade_nome(c.get("nome"), nome_log) >= 0.80:
                        alvo = c
                        break
            if alvo:
                alvo["assinatura"] = True
                alvo["assinatura_tipo"] = "assinatura_digital"
                alvo["assinatura_origem"] = "texto_digital"
                alvo["assinatura_confianca"] = max(float(alvo.get("assinatura_confianca") or 0), 0.95)
                alvo["paginas"] = sorted(set(alvo.get("paginas", []) + [pagina]))
                continue
            if eh_nome_colaborador_valido(nome_log):
                novo = {
                    "nome": nome_log,
                    "colaborador": nome_log,
                    "paginas": [pagina],
                    "layout": "log_assinatura_digital",
                    "competencia": p.get("competencia") or "-",
                    "periodo_inicio": "",
                    "periodo_fim": "",
                    "competencia_ok": bool((p.get("competencia") or "") and (not competencia_esperada or p.get("competencia") == competencia_esperada)),
                    "marcacoes": bool(p.get("marcacoes_encontradas")),
                    "marcacoes_encontradas": bool(p.get("marcacoes_encontradas")),
                    "qtd_horarios": int(p.get("qtd_horarios") or 0),
                    "indicio_rasura_horario_britanico": bool(p.get("indicio_rasura_horario_britanico")),
                    "rasura_motivo": p.get("rasura_motivo") or "",
                    "assinatura": True,
                    "assinatura_tipo": "assinatura_digital",
                    "assinatura_origem": "texto_digital",
                    "assinatura_confianca": 0.95,
                    "assinatura_bbox": [],
                    "assinatura_pagina": pagina,
                    "assinatura_zona": "texto_digital",
                    "assinatura_motivo": "Vinculado por log digital.",
                    "motivos": [],
                    "avisos": ["Criado a partir de log de assinatura digital com nome vÃ¡lido."],
                    "datado": True,
                }
                colaboradores.append(novo)
                atual = novo
                continue
            avisos_globais.append(f"PÃ¡gina {pagina} de log digital ignorada por nÃ£o possuir nome vÃ¡lido.")
            continue

        if tipo == "pagina_assinatura_sem_nome":
            if not _eh_verso_por_perfil(p, atual, perfil_forcado=perfil_leitura):
                avisos_globais.append(
                    f"PÃ¡gina {pagina} com assinatura sem nome rejeitada como verso pelo perfil '{_perfil_layout_cartao(p.get('layout'))}'."
                )
                atual = None
                continue
            if atual is not None:
                atual["paginas"] = sorted(set(atual.get("paginas", []) + [pagina]))
                if p.get("assinatura"):
                    atual["assinatura"] = True
                    atual["assinatura_tipo"] = p.get("assinatura_tipo") or atual.get("assinatura_tipo")
                    atual["assinatura_origem"] = p.get("assinatura_origem") or atual.get("assinatura_origem")
                    atual["assinatura_confianca"] = max(float(atual.get("assinatura_confianca") or 0), float(p.get("assinatura_confianca") or 0))
                avisos_globais.append(f"PÃ¡gina {pagina} vinculada ao colaborador anterior como complemento de assinatura.")
                print(f"[CARTAO][P{pagina}] agrupada_como_verso=True assinatura_detectada={bool(p.get('assinatura'))}")
            else:
                avisos_globais.append(f"PÃ¡gina {pagina} possui marcaÃ§Ãµes/assinatura, mas nÃ£o foi possÃ­vel vincular a um colaborador com nome vÃ¡lido.")
            continue

        avisos_globais.append(f"PÃ¡gina {pagina} ignorada por nÃ£o possuir nome vÃ¡lido.")

    colaboradores_final = []
    for c in colaboradores:
        if not eh_nome_colaborador_valido(c.get("nome", "")):
            avisos_globais.append("Registro descartado porque nÃ£o possui nome vÃ¡lido.")
            print("[CARTAO] Registro descartado: nome invÃ¡lido")
            continue
        nome_ok = True
        comp_ok = bool((c.get("competencia") or "").strip() and c.get("competencia") != "-" and (not competencia_esperada or c.get("competencia") == competencia_esperada))
        marc_ok = bool(c.get("marcacoes_encontradas") or c.get("marcacoes")) and (not bool(c.get("indicio_rasura_horario_britanico")))
        ass_ok = bool(c.get("assinatura"))
        score, status_item = _score_status_colaborador(nome_ok, comp_ok, marc_ok, ass_ok)
        c["competencia_ok"] = comp_ok
        c["status"] = status_item
        c["score"] = score
        if not comp_ok:
            comp_lida = (c.get("competencia") or "-").strip() or "-"
            comp_ref = (competencia_esperada or "-").strip() or "-"
            c.setdefault("motivos", []).append(f"CompetÃªncia divergente/ausente (lida: {comp_lida} | esperada: {comp_ref})")
        if not marc_ok:
            c.setdefault("motivos", []).append("MarcaÃ§Ãµes insuficientes")
        if c.get("indicio_rasura_horario_britanico"):
            c.setdefault("motivos", []).append(c.get("rasura_motivo") or "IndÃ­cio de rasura por horÃ¡rio rÃ­gido.")
        if not ass_ok:
            c.setdefault("motivos", []).append("Assinatura/rubrica ausente")
        colaboradores_final.append(c)
    return colaboradores_final, avisos_globais


def extrair_assinaturas_digitais_por_nome(texto):
    nomes = set()
    for m in re.finditer(r"ASSINATURA\s+DE\s*[:\-]\s*([A-ZÃƒâ‚¬-ÃƒÅ¡][A-ZÃƒâ‚¬-ÃƒÅ¡\s]{4,}?)\s*(?:\||\n|$)", str(texto or ""), flags=re.IGNORECASE):
        nome = re.sub(r"\s+", " ", (m.group(1) or "")).strip()
        if len(nome.split()) >= 2:
            nomes.add(_nome_norm(nome))
    return nomes


def _paginas_candidatas_assinatura(paginas_ocr):
    candidatos = set()
    for p in paginas_ocr:
        idx = int(p.get("pagina") or 0)
        t = (p.get("texto") or "").upper()
        if not idx:
            continue
        if ("ASSINATURA" in t) or ("RUBRICA" in t) or ("LOG DE ASSINATURA" in t) or ("ASSINATURA DE:" in t):
            candidatos.add(idx)
        if ("FUNCION" in t or "EMPREGADO" in t or "COLABORADOR" in t) and idx > 0:
            candidatos.add(idx + 1)
        if "REGISTRO DE OCORREN" in t:
            candidatos.add(idx)
    return {p for p in candidatos if p > 0}


def _score_status_colaborador(nome_ok, competencia_ok, marcacoes_ok, assinatura_ok):
    score = 0
    if nome_ok:
        score += 25
    if competencia_ok:
        score += 25
    if marcacoes_ok:
        score += 25
    if assinatura_ok:
        score += 25
    if score >= 80:
        status = "OK"
    elif score >= 50:
        status = "INCONCLUSIVO"
    else:
        status = "FALTANDO"
    if not nome_ok:
        status = "INCONCLUSIVO"
    if not assinatura_ok and status == "OK":
        status = "INCONCLUSIVO"
    return score, status


def deve_chamar_ia_cartao_ponto(resultado_local):
    colaboradores = list((resultado_local or {}).get("colaboradores") or [])
    if not colaboradores:
        return True, "sem_colaboradores"
    qualidade_ocr = float((resultado_local or {}).get("ocr_qualidade") or 1.0)
    if qualidade_ocr < 0.35:
        return True, "ocr_baixa_qualidade"
    for col in colaboradores:
        nome = (col.get("nome") or "").strip()
        competencia = (col.get("competencia") or "").strip()
        assinatura_tipo = str(col.get("assinatura_tipo") or "").strip().lower()
        assinatura_ok = bool(col.get("assinatura"))
        if (not nome) or (nome.lower() == "colaborador sem nome"):
            return True, "nome_ausente_ou_generico"
        if (not competencia) or (competencia == "-"):
            return True, "competencia_ausente"
        if (not assinatura_ok) and assinatura_tipo == "inconclusiva":
            return True, "assinatura_inconclusiva"
    return False, "resultado_local_ok"


def preparar_recortes_cartao_ponto(caminho_pdf, pagina):
    try:
        idx = max(1, int(pagina)) - 1
        img = renderizar_pagina_pdf(caminho_pdf, idx, dpi=300)
        recorte = recortar_area_documento_cartao(img)
        imagem_recortada = recorte.get("imagem_recortada")
        regioes = gerar_recortes_cartao_ponto(imagem_recortada)
        out = {"total": imagem_recortada}
        out.update(regioes)
        return out
    except Exception as exc:
        print(f"[PONTO] Falha ao preparar recortes da pagina {pagina}: {exc}")
        return {}


def fallback_ia_cartao_ponto_por_regiao(recortes, campos_pendentes):
    # CartÃ£o ponto: fallback regional por Gemini desativado.
    # Mantemos somente fallback OpenAI/ChatGPT em nÃ­vel de PDF completo.
    return {}


def mesclar_resultado_local_com_ia(resultado_local, resultado_ia):
    col = dict(resultado_local or {})
    ia = dict(resultado_ia or {})
    campos_corrigidos = []
    conf_ia = float(ia.get("confianca") or 0.0)

    nome_local = (col.get("nome") or "").strip()
    nome_local_ok = bool(nome_local and nome_local.lower() != "colaborador sem nome")
    nome_ia = (ia.get("nome") or "").strip()
    if (not nome_local_ok) and bool(ia.get("nome_encontrado")) and nome_ia:
        col["nome"] = nome_ia
        col["colaborador"] = nome_ia
        campos_corrigidos.append("nome")

    comp_local = (col.get("competencia") or "").strip()
    comp_ia = (ia.get("competencia") or "").strip()
    if ((not comp_local) or (comp_local == "-")) and comp_ia:
        col["competencia"] = comp_ia
        col["periodo_inicio"] = ia.get("periodo_inicio") or col.get("periodo_inicio", "")
        col["periodo_fim"] = ia.get("periodo_fim") or col.get("periodo_fim", "")
        campos_corrigidos.append("competencia")

    marc_local = bool(col.get("marcacoes_encontradas") or col.get("marcacoes"))
    if (not marc_local) and bool(ia.get("marcacoes_encontradas")):
        col["marcacoes_encontradas"] = True
        col["marcacoes"] = True
        campos_corrigidos.append("marcacoes")

    ass_origem = str(col.get("assinatura_origem") or "").lower()
    ass_local_yolo_cv = ass_origem in {"yolo", "opencv", "opencv_coluna", "opencv_rodape", "heuristica_coluna", "heuristica_rodape", "heuristica_visual"}
    if (not ass_local_yolo_cv) and (not bool(col.get("assinatura"))) and bool(ia.get("assinatura")) and conf_ia >= 0.75:
        col["assinatura"] = True
        col["assinatura_tipo"] = ia.get("assinatura_tipo") or "inconclusiva"
        col["assinatura_origem"] = "ia_fallback"
        col["assinatura_zona"] = ia.get("assinatura_local") or col.get("assinatura_zona", "desconhecida")
        col["assinatura_confianca"] = max(float(col.get("assinatura_confianca") or 0.0), conf_ia)
        campos_corrigidos.append("assinatura")

    nome_ok = bool((col.get("nome") or "").strip() and str(col.get("nome")).strip().lower() != "colaborador sem nome")
    comp_ok = bool((col.get("competencia") or "").strip() and (col.get("competencia") != "-"))
    marc_ok = bool(col.get("marcacoes_encontradas") or col.get("marcacoes"))
    ass_ok = bool(col.get("assinatura"))
    score, status_item = _score_status_colaborador(nome_ok, comp_ok, marc_ok, ass_ok)
    if campos_corrigidos and conf_ia < 0.60:
        status_item = "INCONCLUSIVO"
    col["score"] = score
    col["status"] = status_item
    col["fallback_ia"] = {
        "usado": bool(campos_corrigidos),
        "motivo": "OCR local nao encontrou campos obrigatorios",
        "campos_corrigidos": campos_corrigidos,
        "confianca": round(conf_ia, 4),
    }
    return col


def processar_cartao_ponto(caminho_arquivo, competencia_esperada=None, perfil_leitura="auto"):
    print("\n[PONTO] ===== CARTAO PONTO =====")
    _log_openai_key_context()
    perfil_leitura = str(perfil_leitura or "auto").strip().lower()
    if perfil_leitura not in {"auto", "duas_paginas", "pagina_unica", "layout_fixo"}:
        perfil_leitura = "auto"

    ocr_doc = extrair_documento_inteligente(caminho_arquivo, tipo_documento="cartao_ponto", usar_ocr=True)
    print(f"[PONTO] metodo_leitura={ocr_doc.get('metodo')} qualidade={ocr_doc.get('qualidade')}")

    paginas = [{"pagina": p.get("pagina"), "texto": p.get("texto", "")} for p in ocr_doc.get("paginas", [])]
    if not paginas:
        return {
            "status": "Reprovado",
            "mensagem": "Falha no OCR do cartÃƒÂ£o ponto.",
            "sucesso": False,
            "colaboradores": [],
        }

    texto_completo = "\n".join([p.get("texto", "") for p in paginas])

    auth_digital = detectar_autenticacao_digital(texto_completo)
    yolo_ok = yolo_disponivel()
    modelos_yolo = caminhos_modelos_yolo() if yolo_ok else []
    print(f"[PONTO] yolo_disponivel={'sim' if yolo_ok else 'nao'} modelos={[m.name for m in modelos_yolo] if modelos_yolo else '-'}")
    paginas_alvo_yolo = _paginas_candidatas_assinatura(paginas)
    print(f"[PONTO] paginas_alvo_yolo={sorted(paginas_alvo_yolo)[:25]} total={len(paginas_alvo_yolo)}")
    # YOLO agora e executado por regiao dentro do pipeline de pagina para evitar inferencia global cara.
    deteccoes_yolo = []
    assinatura_global = detectar_rubrica_global_evidencias(caminho_arquivo)

    paginas_layout = processar_paginas_cartao_ponto_layout(
        caminho_arquivo,
        deteccoes_yolo=deteccoes_yolo,
        paginas_texto=paginas,
        render_imagem=False,
        paginas_assinatura_alvo=paginas_alvo_yolo,
    )
    usar_template_fixo = _nome_arquivo_eh_template_fixo(caminho_arquivo)

    resultados_paginas = []
    template_ruidoso = (
        len(paginas_layout) >= 6
        and all(str(p.get("layout") or "").strip().lower() in {"desconhecido", "imagem_escaneada_generica"} for p in paginas_layout)
        and float(ocr_doc.get("qualidade") or 0.0) <= 0.82
    )
    modelo_ordem_detectado = any(eh_modelo_ordem(p.get("texto", "")) for p in paginas)
    for p in paginas_layout:
        texto = p.get("texto_pagina", "") or ""
        texto_topo = p.get("texto_topo", "") or ""
        layout_generico = classificar_layout_cartao_ponto(texto or texto_topo, p.get("pagina"))
        if str(p.get("layout") or "").strip().lower() in {"desconhecido", "imagem_escaneada_generica"} and layout_generico != "desconhecido":
            p["layout"] = layout_generico
        nome_bruto = p.get("nome_colaborador") or ""
        layout_pag = str(p.get("layout") or "").strip().lower()
        modo_estrito_nome = (not usar_template_fixo) and layout_pag in {"desconhecido", "imagem_escaneada_generica", "manual_assinatura_diaria", "manual_verso"}
        texto_base_nome = f"{texto_topo}\n{texto}".strip() if modo_estrito_nome and texto_topo else texto
        nome_result = extrair_nome_colaborador_cartao(
            texto=texto_base_nome,
            linhas_ocr=[
                texto_topo,
                texto,
                p.get("nome_colaborador"),
                p.get("competencia"),
                p.get("assinatura_motivo"),
            ],
            # Nomes "esperados" vindos do parser podem vir poluidos; evita retroalimentar falso positivo.
            nomes_esperados=[],
            modo_estrito=modo_estrito_nome,
        )
        nome_generico = extrair_nome_por_ancoras_generico(f"{texto_topo}\n{texto}", layout_pag or layout_generico)
        if (not nome_result.get("nome")) and nome_generico.get("nome"):
            nome_result = {
                "nome": nome_generico.get("nome"),
                "nome_encontrado": True,
                "confianca": float(nome_generico.get("confianca") or 0.80),
                "origem": nome_generico.get("origem") or "ancora_generica",
                "ancora": "generico",
            }
        # Em modo estrito, nÃ£o usa fallback de nome bruto para evitar "Empregador/RazÃ£o Social".
        if modo_estrito_nome:
            nome_norm = normalizar_nome_colaborador(nome_result.get("nome") or "")
        else:
            nome_norm = normalizar_nome_colaborador(nome_result.get("nome") or nome_bruto)
        nome_valido = nome_colaborador_valido_generico(nome_norm, origem=nome_result.get("origem"), layout=layout_pag) and (not _nome_parece_artefato_template(nome_norm))
        # Pipeline dedicado para template escaneado ruidoso:
        # quando "nome" parece cabeÃ§alho/rodapÃ©, tenta extraÃ§Ã£o agressiva sÃ³ no bloco do empregado.
        if (not nome_valido) or _nome_parece_artefato_template(nome_norm):
            nome_retry = _extrair_nome_empregado_faixa(caminho_arquivo, int(p.get("pagina") or 0))
            nome_retry = normalizar_nome_colaborador(nome_retry)
            if eh_nome_colaborador_valido(nome_retry) and (not _nome_parece_artefato_template(nome_retry)):
                nome_norm = nome_retry
                nome_valido = True
                nome_result["origem"] = "pipeline_template_faixa_empregado"
                nome_result["confianca"] = max(float(nome_result.get("confianca") or 0.0), 0.90)
            else:
                nome_retry = ""
        if (not nome_valido) or _nome_parece_artefato_template(nome_norm):
            nome_retry = _extrair_nome_em_pagina_isolada(caminho_arquivo, int(p.get("pagina") or 0))
            if not eh_nome_colaborador_valido(nome_retry):
                nome_retry = _extrair_nome_empregado_imagem_agressivo(caminho_arquivo, int(p.get("pagina") or 0))
                nome_retry = normalizar_nome_colaborador(nome_retry)
            if eh_nome_colaborador_valido(nome_retry) and (not _nome_parece_artefato_template(nome_retry)):
                nome_norm = nome_retry
                nome_valido = True
                nome_result["origem"] = "pipeline_template_empregado"
                nome_result["confianca"] = max(float(nome_result.get("confianca") or 0.0), 0.86)
        if (not nome_valido) and modelo_ordem_detectado:
            esp = extrair_campos_modelo_ordem(
                caminho_arquivo,
                int(p.get("pagina") or 0),
                competencia_esperada=competencia_esperada or "",
            )
            nome_esp = normalizar_nome_colaborador(esp.get("nome") or "")
            if eh_nome_colaborador_valido(nome_esp) and (not _nome_parece_artefato_template(nome_esp)):
                nome_norm = nome_esp
                nome_valido = True
                nome_result["origem"] = "modelo_ordem"
                nome_result["confianca"] = max(float(nome_result.get("confianca") or 0.0), float(esp.get("confianca") or 0.0))
                if not (p.get("competencia") or "").strip() and (esp.get("competencia") or "").strip():
                    p["competencia"] = esp.get("competencia")
        assinatura_result = {
            "assinatura": bool(p.get("assinatura")),
            "assinatura_tipo": p.get("assinatura_tipo") or "ausente",
            "assinatura_origem": p.get("assinatura_origem") or "nao_identificada",
        }
        tipo_pagina = classificar_pagina_cartao_ponto(texto, nome_result, assinatura_result, layout=p.get("layout"))
        pagina_num = int(p.get("pagina") or 0)
        if template_ruidoso and (not _nome_confiavel_para_template_ruidoso(nome_norm)):
            nome_valido = False
            nome_norm = ""
        if template_ruidoso and nome_valido:
            origem_nome = str(nome_result.get("origem") or "").strip().lower()
            confianca_nome = float(nome_result.get("confianca") or 0.0)
            origens_fortes = {
                "pipeline_template_faixa_empregado",
                "pipeline_template_empregado",
                "funcion",
                "empregado",
                "empregado_pipe",
                "nome_digital",
                "ocr_linha",
            }
            # Antes descartava qualquer origem fora do pipeline dedicado, causando falso negativo.
            # Agora: aceita origem forte ou confianÃ§a alta em nome validado.
            if (origem_nome not in origens_fortes) and (confianca_nome < 0.88):
                nome_retry = _extrair_nome_empregado_faixa(caminho_arquivo, int(p.get("pagina") or 0))
                nome_retry = normalizar_nome_colaborador(nome_retry)
                if eh_nome_colaborador_valido(nome_retry) and (not _nome_parece_artefato_template(nome_retry)):
                    nome_norm = nome_retry
                    nome_valido = True
                    nome_result["origem"] = "pipeline_template_faixa_empregado_retry"
                    nome_result["confianca"] = max(confianca_nome, 0.90)
                else:
                    nome_valido = False
                    nome_norm = ""

        # Fallback visual por página para layouts genéricos quando OCR local falhar.
        chamar_vision_pagina = (
            _api_key_disponivel("OPENAI_API_KEY")
            and (not nome_valido)
            and (layout_pag in {"manual_frente", "desconhecido", "digital_tabela_nome", "folha_funcion", "espelho_digital_colaborador"} or layout_generico in {"manual_frente", "desconhecido", "digital_tabela_nome", "folha_funcion", "espelho_digital_colaborador"})
        )
        if chamar_vision_pagina:
            img_pg = renderizar_pagina_pdf(caminho_arquivo, max(0, int(p.get("pagina") or 1) - 1), dpi=280)
            vres = analisar_pagina_cartao_ponto_openai_vision(
                img_pg,
                int(p.get("pagina") or 0),
                layout_detectado=(layout_pag or layout_generico),
                competencia_esperada=competencia_esperada,
                nomes_esperados=None,
            )
            nome_v = normalizar_nome_colaborador(vres.get("nome") or "")
            if nome_colaborador_valido_generico(nome_v, origem="openai_vision_pagina_inteira", layout=layout_pag):
                nome_norm = nome_v
                nome_valido = True
                nome_result["origem"] = "openai_vision_pagina_inteira"
                nome_result["confianca"] = max(float(nome_result.get("confianca") or 0.0), float(vres.get("confianca") or 0.0), 0.80)
                if (not (p.get("competencia") or "").strip()) and (vres.get("competencia") or "").strip():
                    p["competencia"] = str(vres.get("competencia") or "").strip()
                if bool(vres.get("assinatura")):
                    p["assinatura"] = True
                    p["assinatura_tipo"] = vres.get("assinatura_tipo") or p.get("assinatura_tipo") or "assinatura_manual"
                    p["assinatura_origem"] = "openai_vision_pagina_inteira"
                    p["assinatura_confianca"] = max(float(p.get("assinatura_confianca") or 0.0), float(vres.get("confianca") or 0.0))
                if bool(vres.get("marcacoes_encontradas")):
                    p["marcacoes_encontradas"] = True
        print(f"[CARTAO][P{p.get('pagina')}] Nome extraÃ­do bruto: {nome_bruto}")
        print(f"[CARTAO][P{p.get('pagina')}] Nome normalizado: {nome_norm}")
        print(f"[CARTAO][P{p.get('pagina')}] Nome vÃ¡lido: {nome_valido}")
        print(f"[CARTAO][P{p.get('pagina')}] Tipo pÃ¡gina: {tipo_pagina}")
        print(f"[CARTAO][P{p.get('pagina')}] assinatura_detectada={bool(p.get('assinatura'))} agrupada_como_verso=False")
        resultados_paginas.append({
            "pagina": p.get("pagina"),
            "tipo_pagina": tipo_pagina,
            "layout": p.get("layout"),
            "nome": nome_norm if nome_valido else "",
            "nome_bruto": nome_bruto,
            "nome_encontrado": bool(nome_valido),
            "nome_origem": nome_result.get("origem"),
            "nome_confianca": float(nome_result.get("confianca") or 0.0),
            "competencia": p.get("competencia") or "",
            "periodo_inicio": p.get("periodo_inicio", ""),
            "periodo_fim": p.get("periodo_fim", ""),
            "marcacoes_encontradas": bool(p.get("marcacoes_encontradas")),
            "qtd_horarios": int(p.get("qtd_horarios") or 0),
            "indicio_rasura_horario_britanico": bool((p.get("marcacoes_info") or {}).get("indicio_rasura_horario_britanico")),
            "rasura_motivo": str((p.get("marcacoes_info") or {}).get("rasura_motivo") or ""),
            "assinatura": bool(p.get("assinatura")),
            "assinatura_tipo": p.get("assinatura_tipo") or "ausente",
            "assinatura_origem": p.get("assinatura_origem") or "nao_identificada",
            "assinatura_confianca": float(p.get("assinatura_confianca") or 0.0),
            "assinatura_bbox": p.get("assinatura_bbox"),
            "assinatura_pagina": p.get("assinatura_pagina"),
            "assinatura_zona": p.get("assinatura_zona", "desconhecida"),
            "assinatura_motivo": p.get("assinatura_motivo") or "",
            "texto_topo": p.get("texto_topo") or "",
            "texto_pagina": texto,
            "texto_chave": [],
            "avisos": list(p.get("avisos", [])),
            "motivos": list(p.get("motivos", [])),
        })

    modo_aplicado = perfil_leitura if perfil_leitura != "auto" else _inferir_modo_leitura(resultados_paginas)
    print(f"[PONTO] perfil_leitura_solicitado={perfil_leitura} modo_aplicado={modo_aplicado}")

    for rp in resultados_paginas:
        pagina_num = int(rp.get("pagina") or 0)
        nome_valido = bool((rp.get("nome") or "").strip())
        tipo_pagina = rp.get("tipo_pagina")
        if modo_aplicado == "pagina_unica":
            if tipo_pagina in {"verso_continuacao", "pagina_assinatura_sem_nome"}:
                rp["tipo_pagina"] = "pagina_com_nome" if nome_valido else "pagina_sem_nome_ignorar"
        elif modo_aplicado == "duas_paginas":
            if pagina_num % 2 == 1 and tipo_pagina in {"verso_continuacao", "pagina_assinatura_sem_nome"}:
                rp["tipo_pagina"] = "pagina_com_nome" if nome_valido else "pagina_sem_nome_ignorar"
            if pagina_num % 2 == 0 and tipo_pagina == "pagina_com_nome":
                rp["tipo_pagina"] = "verso_continuacao" if bool(rp.get("assinatura")) else "pagina_assinatura_sem_nome"

    # Fallback de recuperaÃ§Ã£o:
    # quando nenhum nome vÃ¡lido foi obtido no modo estrito, refaz somente pÃ¡ginas Ã­mpares
    # aceitando o nome bruto extraÃ­do pelo parser de layout (caso comum em PDF escaneado
    # onde pÃ¡gina Ãºnica funciona melhor que lote completo).
    if (not template_ruidoso) and (not any(bool((rp.get("nome") or "").strip()) for rp in resultados_paginas)):
        for rp in resultados_paginas:
            pg = int(rp.get("pagina") or 0)
            if modo_aplicado == "duas_paginas" and pg % 2 == 0:
                continue
            fonte = next((x for x in paginas_layout if int(x.get("pagina") or 0) == pg), None)
            if not fonte:
                continue
            nome_bruto_retry = normalizar_nome_colaborador(fonte.get("nome_colaborador") or "")
            nome_relaxado = _extrair_nome_relaxado_emergencial(
                f"{fonte.get('texto_topo') or ''}\n{fonte.get('texto_pagina') or ''}"
            )
            nome_candidato = nome_bruto_retry if eh_nome_colaborador_valido(nome_bruto_retry) else nome_relaxado
            if nome_candidato and _nome_parece_artefato_template(nome_candidato):
                nome_candidato = ""
            if template_ruidoso and nome_candidato and (not _nome_confiavel_para_template_ruidoso(nome_candidato)):
                nome_candidato = ""
            if nome_candidato and len(nome_candidato.split()) >= 2:
                rp["nome"] = nome_bruto_retry
                rp["nome_encontrado"] = True
                rp["nome"] = normalizar_nome_colaborador(nome_candidato)
                rp["nome_origem"] = "fallback_nome_emergencial_pagina_impar"
                rp["nome_confianca"] = max(float(rp.get("nome_confianca") or 0.0), 0.72)
                if rp.get("tipo_pagina") in {"pagina_sem_nome_ignorar", "pagina_assinatura_sem_nome", "verso_continuacao"}:
                    rp["tipo_pagina"] = "pagina_com_nome"

    if usar_template_fixo:
        colaboradores, avisos_globais = consolidar_colaboradores_template_fixo(
            resultados_paginas,
            competencia_esperada=competencia_esperada,
            permitir_nome_fraco=not template_ruidoso,
            template_ruidoso=template_ruidoso,
        )
    else:
        colaboradores, avisos_globais = consolidar_colaboradores_cartao_ponto(
            resultados_paginas,
            competencia_esperada=competencia_esperada,
            perfil_leitura=modo_aplicado,
        )
    # Modo alternativo para cartão manual escaneado com OpenAI Vision (página inteira).
    manual_detectado = detectar_cartao_manual_escaneado(resultados_paginas, ocr_doc)
    sem_nomes_validos = not any(eh_nome_colaborador_valido((c or {}).get("nome", "")) for c in (colaboradores or []))
    nomes_suspeitos_local = _tem_nome_suspeito_local(colaboradores)
    forcar_vision_por_falha = (sem_nomes_validos or nomes_suspeitos_local) and len(resultados_paginas or []) >= 4
    openai_ok = _api_key_disponivel("OPENAI_API_KEY")
    print(
        f"[OPENAI VISION] manual_detectado={manual_detectado} forcar={forcar_vision_por_falha} "
        f"nomes_suspeitos_local={nomes_suspeitos_local} openai_key={openai_ok}"
    )
    if (manual_detectado or forcar_vision_por_falha) and openai_ok:
        if forcar_vision_por_falha and (not manual_detectado):
            print("[OPENAI VISION] fallback forçado: sem nomes válidos em PDF multipágina.")
        precisa_vision = (not colaboradores) or _colaboradores_suspeitos_ou_poucos(colaboradores, resultados_paginas) or forcar_vision_por_falha
        print(f"[OPENAI VISION] precisa_vision={precisa_vision} colaboradores_local={len(colaboradores or [])}")
        if precisa_vision:
            # 1) Primeira tentativa igual ao teste isolado: Vision "puro" (sem nomes_esperados).
            cols_visuais, avisos_vis = processar_cartao_manual_escaneado_openai_vision(
                caminho_arquivo,
                competencia_esperada=competencia_esperada,
                nomes_esperados=None,
            )
            # 2) Segunda tentativa opcional guiada por nomes de referencia apenas se vier vazio.
            if not cols_visuais:
                nomes_ref = _nomes_esperados_env()
                nomes_auto = _nomes_candidatos_documento(resultados_paginas, paginas_layout)
                for n in nomes_auto:
                    if n not in nomes_ref:
                        nomes_ref.append(n)
                if nomes_ref:
                    print(f"[OPENAI VISION] nomes_referencia={len(nomes_ref)} (segunda tentativa)")
                    cols_visuais, avisos_vis_2 = processar_cartao_manual_escaneado_openai_vision(
                        caminho_arquivo,
                        competencia_esperada=competencia_esperada,
                        nomes_esperados=nomes_ref,
                    )
                    avisos_vis.extend(avisos_vis_2)
            if cols_visuais:
                # Se OCR local trouxe nome suspeito, prioriza resultado Vision.
                if nomes_suspeitos_local or sem_nomes_validos or (len(cols_visuais) >= len(colaboradores or [])):
                    colaboradores = cols_visuais
                avisos_globais.extend(avisos_vis)

    # Fallback final para escaneado ruim:
    # se falhou tudo localmente, forÃ§a agrupamento frente/verso em duplas Ã­mpar/par.
    if not colaboradores and len(resultados_paginas) >= 2:
        cols_fb, avisos_fb = _fallback_duplas_frente_verso(
            caminho_arquivo,
            resultados_paginas,
            competencia_esperada=competencia_esperada,
        )
        if cols_fb:
            colaboradores = cols_fb
            avisos_globais.extend(avisos_fb)
            print(f"[PONTO] fallback_duplas_frente_verso aplicado: {len(cols_fb)} colaborador(es)")

    layout_stats = Counter([(p.get("layout") or "generico") for p in paginas_layout])
    layout_info = {
        "layout_id": "layout_parser_v2",
        "layout_conhecido": any(l != "generico" for l in layout_stats.keys()),
        "score": 1.0 if any(l != "generico" for l in layout_stats.keys()) else 0.0,
        "ancoras_encontradas": sorted(layout_stats.keys()),
        "layouts_contagem": dict(layout_stats),
    }

    resultado_local = {
        "layout_conhecido": layout_info.get("layout_conhecido"),
        "layout_id": layout_info.get("layout_id"),
        "colaboradores": colaboradores,
        "ocr_qualidade": float(ocr_doc.get("qualidade") or 0.0),
    }

    # Fallback IA condicionado Ã s chaves disponÃ­veis.
    chamar_ia, _motivo_ia_local = deve_chamar_ia_cartao_ponto(resultado_local)
    gemini_disponivel = False
    openai_disponivel = _api_key_disponivel("OPENAI_API_KEY")
    ia_disponivel = openai_disponivel
    chamar_ia = bool(chamar_ia and ia_disponivel)
    if not ia_disponivel:
        motivo_ia = "fallback_ia_sem_api_key"
    elif chamar_ia:
        motivo_ia = "fallback_ia_habilitado"
    else:
        motivo_ia = "fallback_ia_nao_necessario"

    print(f"[PONTO] fallback_ia={'sim' if chamar_ia else 'nao'} motivo={motivo_ia}")

    tentou_openai_precoce = False
    if chamar_ia:
        # Se o OCR local jÃ¡ nÃ£o encontrou colaboradores, tenta OpenAI primeiro
        # para evitar espera longa no fallback completo do Gemini.
        if not colaboradores and openai_disponivel:
            tentou_openai_precoce = True
            resp_openai_early = extrair_cartao_ponto_openai_pdf(
                caminho_arquivo,
                competencia_esperada=competencia_esperada,
                perfil_leitura=perfil_leitura,
            )
            cols_openai_early = list(resp_openai_early.get("colaboradores") or [])
            cols_openai_early = [
                c for c in cols_openai_early
                if eh_nome_colaborador_valido(c.get("nome", "")) and _nome_tem_evidencia_no_texto(c.get("nome", ""), texto_completo)
            ]
            if template_ruidoso:
                cols_openai_early = [
                    c for c in cols_openai_early
                    if _nome_tem_evidencia_em_paginas(c.get("nome", ""), paginas, min_paginas=2)
                ]
            if cols_openai_early:
                colaboradores = cols_openai_early
                motivo_ia = f"openai_fallback_precoce:{resp_openai_early.get('motivo')}"

        # Fallback inteligente por regiÃƒÂ£o: tenta corrigir somente campos pendentes.
        colaboradores_corrigidos = []
        for col in colaboradores:
            campos_pendentes = []
            nome_atual = (col.get("nome") or "").strip().lower()
            if (not nome_atual) or (nome_atual == "colaborador sem nome"):
                campos_pendentes.append("nome")
            if not (col.get("competencia") or "").strip() or (col.get("competencia") == "-"):
                campos_pendentes.append("competencia")
            if not bool(col.get("marcacoes_encontradas") or col.get("marcacoes")):
                campos_pendentes.append("marcacoes")
            if (not bool(col.get("assinatura"))) or (str(col.get("assinatura_tipo") or "").lower() == "inconclusiva"):
                campos_pendentes.append("assinatura")

            if not campos_pendentes:
                colaboradores_corrigidos.append(col)
                continue

            paginas_col = col.get("paginas") or [1]
            pagina_base = int(paginas_col[0]) if paginas_col else 1
            pagina_ass = int(col.get("assinatura_pagina") or paginas_col[-1] or pagina_base)
            recortes_base = preparar_recortes_cartao_ponto(caminho_arquivo, pagina_base)
            recortes_ass = recortes_base if pagina_ass == pagina_base else preparar_recortes_cartao_ponto(caminho_arquivo, pagina_ass)

            ia_base = {}
            ia_ass = {}
            if any(c in campos_pendentes for c in ["nome", "competencia", "marcacoes"]):
                campos_base = [c for c in campos_pendentes if c in {"nome", "competencia", "marcacoes"}]
                ia_base = fallback_ia_cartao_ponto_por_regiao(recortes_base, campos_base)
            if "assinatura" in campos_pendentes:
                ia_ass = fallback_ia_cartao_ponto_por_regiao(recortes_ass, ["assinatura"])

            col_merged = mesclar_resultado_local_com_ia(col, ia_base or {})
            col_merged = mesclar_resultado_local_com_ia(col_merged, ia_ass or {})
            if col_merged.get("fallback_ia", {}).get("usado"):
                col_merged.setdefault("avisos", [])
                col_merged["avisos"].append("Campos ajustados por fallback IA regional.")
            colaboradores_corrigidos.append(col_merged)

        colaboradores = colaboradores_corrigidos

        # MantÃƒÂ©m fallback antigo (PDF inteiro) como ÃƒÂºltima camada de seguranÃƒÂ§a.
        ainda_falho, _motivo_restante = deve_chamar_ia_cartao_ponto({
            "colaboradores": colaboradores,
            "ocr_qualidade": float(ocr_doc.get("qualidade") or 0.0),
        })
        if False and ainda_falho and len(colaboradores) == 0 and gemini_disponivel and (not tentou_openai_precoce):
            timeout_gemini = int(os.getenv("CARTAO_PONTO_IA_TIMEOUT", "15") or "15")
            resposta_gemini = extrair_cartao_ponto_pdf_com_timeout(caminho_arquivo, timeout_segundos=timeout_gemini)
            cols_g = resposta_gemini.get("colaboradores", []) if isinstance(resposta_gemini, dict) else []
            if cols_g:
                motivo_ia = "gemini_fallback:pdf_completo"
                for cg in cols_g:
                    nome = cg.get("nome") or "Colaborador sem nome"
                    comp = cg.get("competencia") or "-"
                    comp_ok = bool(comp and (not competencia_esperada or comp == competencia_esperada))
                    marc = bool(cg.get("marcacoes"))
                    nome_ok = nome != "Colaborador sem nome"
                    score, st = _score_status_colaborador(nome_ok, comp_ok, marc, False)
                    if not nome_ok:
                        st = "INCONCLUSIVO"
                    colaboradores.append({
                        "nome": nome.title(),
                        "competencia": comp,
                        "competencia_ok": comp_ok,
                        "marcacoes": marc,
                        "marcacoes_encontradas": marc,
                        "assinatura": False,
                        "assinatura_tipo": "ausente",
                        "assinatura_origem": "nao_identificada",
                        "assinatura_confianca": 0.0,
                        "assinatura_paginas": [],
                        "assinatura_bbox": None,
                        "assinatura_zona": "",
                        "assinatura_motivo": "Sem evidÃƒÂªncia visual local.",
                        "status": st,
                        "score": score,
                        "motivos": ["Assinatura/rubrica ausente"],
                        "avisos": ["Nome/competÃƒÂªncia obtidos via fallback IA de PDF completo"],
                        "datado": True,
                    })

    # Fallback OpenAI para cartÃ£o ponto:
    # dispara quando OCR/fallback Gemini nÃ£o encontrou colaborador vÃ¡lido.
    if not colaboradores and openai_disponivel:
        resp_openai = extrair_cartao_ponto_openai_pdf(
            caminho_arquivo,
            competencia_esperada=competencia_esperada,
            perfil_leitura=perfil_leitura,
        )
        cols_openai = list(resp_openai.get("colaboradores") or [])
        cols_openai = [
            c for c in cols_openai
            if eh_nome_colaborador_valido(c.get("nome", "")) and _nome_tem_evidencia_no_texto(c.get("nome", ""), texto_completo)
        ]
        if template_ruidoso:
            cols_openai = [
                c for c in cols_openai
                if _nome_tem_evidencia_em_paginas(c.get("nome", ""), paginas, min_paginas=2)
            ]
        if cols_openai:
            colaboradores = cols_openai
            motivo_ia = f"openai_fallback:{resp_openai.get('motivo')}"
        elif motivo_ia in {"fallback_ia_habilitado", "fallback_ia_nao_necessario"}:
            motivo_ia = f"openai_fallback_sem_resultado:{resp_openai.get('motivo')}"

    try:
        aprender_documento(
            "cartao_ponto",
            texto_completo,
            {
                "quantidade_colaboradores": len(colaboradores),
                "nomes": [c.get("nome") for c in colaboradores if c.get("nome")][:20],
                "competencias": sorted({c.get("competencia") for c in colaboradores if c.get("competencia") and c.get("competencia") != "-"})[:10],
                "tem_marcacoes": any(bool(c.get("marcacoes")) for c in colaboradores),
            },
            origem=caminho_arquivo,
        )
    except Exception as exc:
        print(f"[PONTO] aviso aprendizado: {exc}")

    regras = validar_cartao_ponto(colaboradores)
    status_final = avaliar_status(colaboradores)
    if regras.get("status") == "Reprovado":
        status_final = "Reprovado"
    elif regras.get("status") == "Parcial" and status_final == "Aprovado":
        status_final = "Parcial"

    print(f"[CARTAO] Status final: {status_final}")
    avisos_regras = regras.get("avisos", []) or []
    resultado = {
        "arquivo": caminho_arquivo,
        "status": status_final,
        "mensagem": f"{len(colaboradores)} colaborador(es) com nome vÃ¡lido processado(s).",
        "sucesso": True,
        "assinaturas": montar_resumo_assinaturas(colaboradores),
        "colaboradores": colaboradores,
        "resultados_paginas": [
            {
                "pagina": p.get("pagina"),
                "tipo_pagina": p.get("tipo_pagina"),
                "layout": p.get("layout"),
                "nome_colaborador": p.get("nome"),
                "nome_encontrado": p.get("nome_encontrado"),
                "competencia": p.get("competencia"),
                "marcacoes_encontradas": p.get("marcacoes_encontradas"),
                "qtd_horarios": p.get("qtd_horarios"),
                "assinatura": p.get("assinatura"),
                "assinatura_tipo": p.get("assinatura_tipo"),
                "assinatura_origem": p.get("assinatura_origem"),
                "assinatura_confianca": p.get("assinatura_confianca"),
                "motivos": p.get("motivos", []),
                "avisos": p.get("avisos", []),
            }
            for p in resultados_paginas
        ],
        "layout": {
            "layout_id": layout_info.get("layout_id"),
            "layout_conhecido": layout_info.get("layout_conhecido"),
            "score": layout_info.get("score"),
            "ancoras_encontradas": layout_info.get("ancoras_encontradas"),
            "layouts_contagem": layout_info.get("layouts_contagem", {}),
        },
        "ocr": {
            "metodo": ocr_doc.get("metodo"),
            "qualidade": ocr_doc.get("qualidade"),
            "paginas": [{"pagina": p.get("pagina"), "metodo": p.get("metodo"), "qualidade": p.get("qualidade")} for p in ocr_doc.get("paginas", [])],
        },
        "autenticacao_digital": auth_digital,
        "assinatura_global": assinatura_global,
        "ia_fallback": chamar_ia,
        "ia_motivo": motivo_ia,
        "erros": regras.get("erros", []),
        "avisos": avisos_regras,
        "avisos_globais": avisos_globais,
    }
    return _corrigir_payload_texto(resultado)


def processar_pdf_cartao_ponto_parallel(caminho_pdf, max_workers=None):
    """Mantem assinatura publica para execucao paralela controlada por pagina."""
    ocr_doc = extrair_documento_inteligente(caminho_pdf, tipo_documento="cartao_ponto", usar_ocr=True)
    paginas = [{"pagina": p.get("pagina"), "texto": p.get("texto", "")} for p in ocr_doc.get("paginas", [])]
    return processar_paginas_cartao_ponto_layout(
        caminho_pdf,
        deteccoes_yolo=[],
        paginas_texto=paginas,
        render_imagem=False,
        paginas_assinatura_alvo=_paginas_candidatas_assinatura(paginas),
    )


def processar_cartao_ponto_multiplos(caminhos_arquivos, competencia_esperada=None):
    resultados = []
    for caminho in (caminhos_arquivos or []):
        if not caminho:
            continue
        try:
            resultados.append(processar_cartao_ponto(caminho, competencia_esperada=competencia_esperada))
        except Exception as exc:
            resultados.append({"status": "Reprovado", "sucesso": False, "colaboradores": [], "erro": str(exc), "arquivo": caminho})

    todos = []
    for r in resultados:
        for c in r.get("colaboradores", []):
            item = dict(c)
            item["_arquivo_origem"] = r.get("arquivo", "")
            todos.append(item)

    by_nome = {}
    sem_nome = []
    for c in todos:
        nome = c.get("nome") or ""
        if not _nome_colaborador_valido(nome):
            sem_nome.append(c)
            continue
        key = _nome_key(nome)
        if key not in by_nome:
            by_nome[key] = dict(c)
            continue
        base = by_nome[key]
        base["paginas"] = sorted(set((base.get("paginas") or []) + (c.get("paginas") or [])))
        base["qtd_horarios"] = int(base.get("qtd_horarios") or 0) + int(c.get("qtd_horarios") or 0)
        base["marcacoes_encontradas"] = bool(base["qtd_horarios"] >= 8 or base.get("marcacoes_encontradas") or c.get("marcacoes_encontradas"))
        if (not base.get("assinatura")) and c.get("assinatura"):
            base["assinatura"] = True
            base["assinatura_tipo"] = c.get("assinatura_tipo")
            base["assinatura_origem"] = c.get("assinatura_origem")
            base["assinatura_confianca"] = c.get("assinatura_confianca")
            base["assinatura_motivo"] = c.get("assinatura_motivo")
        if (not base.get("competencia")) and c.get("competencia"):
            base["competencia"] = c.get("competencia")

    consolidados = list(by_nome.values())
    return {
        "status": "Aprovado" if consolidados and all(c.get("assinatura") for c in consolidados if c.get("nome") != "Colaborador sem nome") else "Parcial",
        "sucesso": True,
        "mensagem": f"{len(consolidados)} colaborador(es) consolidados em {len(caminhos_arquivos or [])} PDF(s).",
        "colaboradores": consolidados,
        "resultados_arquivos": resultados,
    }











