import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

LAYOUT_DIR = Path("data") / "layouts" / "cartao_ponto"

ANCORAS_BASE = [
    "CARTAO DE PONTO", "ESPELHO DE PONTO", "FUNCIONARIO", "FUNCIONÁRIO",
    "COLABORADOR", "EMPREGADO", "NOME", "COMPETENCIA", "COMPETÊNCIA",
    "PERIODO", "PERÍODO", "DATA", "ENTRADA", "SAIDA", "SAÍDA",
    "INTERVALO", "HORAS", "ASSINATURA", "RUBRICA",
]

STOPWORDS_NOME = {
    "CARTAO", "PONTO", "FUNCIONARIO", "FUNCIONARIO", "COLABORADOR", "EMPREGADO", "NOME",
    "COMPETENCIA", "PERIODO", "DATA", "ENTRADA", "SAIDA", "INTERVALO", "HORAS", "ASSINATURA", "RUBRICA",
    "EMPRESA", "CNPJ", "CPF", "CARGO", "SETOR", "MATRICULA", "MATRÍCULA",
    "ORDEM", "EMPREGADOR", "RAZAO", "RAZÃO", "SOCIAL", "CLIENTE",
}
TERMOS_EMPRESA = {"LTDA", "EIRELI", "S/A", "CNPJ", "ME", "EPP"}


def _norm(texto):
    txt = unicodedata.normalize("NFKD", str(texto or ""))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = re.sub(r"\s+", " ", txt.upper())
    return txt.strip()


def _to_mm_aaaa(mes, ano):
    mes = str(mes).zfill(2)
    if len(str(ano)) == 2:
        ano = f"20{ano}"
    return f"{mes}/{ano}"


def _parse_competencia(texto):
    t = _norm(texto)

    m = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\s*(?:A|ATE|ATÉ)\s*(\d{2})/(\d{2})/(\d{4})\b", t)
    if m:
        return _to_mm_aaaa(m.group(2), m.group(3))

    m = re.search(r"\b(0[1-9]|1[0-2])[/-](\d{4})\b", t)
    if m:
        return _to_mm_aaaa(m.group(1), m.group(2))

    m = re.search(r"\b(0[1-9]|1[0-2])[/-](\d{2})\b", t)
    if m:
        return _to_mm_aaaa(m.group(1), m.group(2))

    meses = {
        "JANEIRO": "01", "FEVEREIRO": "02", "MARCO": "03", "MARÇO": "03", "ABRIL": "04", "MAIO": "05", "JUNHO": "06",
        "JULHO": "07", "AGOSTO": "08", "SETEMBRO": "09", "OUTUBRO": "10", "NOVEMBRO": "11", "DEZEMBRO": "12",
    }
    for nome_mes, num in meses.items():
        m = re.search(rf"\b{nome_mes}\s*(?:/|\s)\s*(\d{{4}})\b", t)
        if m:
            return _to_mm_aaaa(num, m.group(1))

    return ""


def _extrair_horarios(texto):
    return re.findall(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", texto or "")


def _extrair_datas(texto):
    datas = re.findall(r"\b[0-3]?\d/[01]?\d(?:/\d{2,4})?\b", texto or "")
    return datas


def _nome_por_ancora(texto):
    linhas = [ln.strip() for ln in str(texto or "").splitlines() if ln.strip()]
    anchors = ["FUNCIONARIO", "FUNCIONÁRIO", "COLABORADOR", "EMPREGADO", "NOME"]
    for idx, ln in enumerate(linhas):
        ln_norm = _norm(ln)
        if any(a in ln_norm for a in anchors):
            janela = linhas[idx: min(len(linhas), idx + 3)]
            for cand in janela:
                m = re.search(r":\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]{5,})", cand, flags=re.IGNORECASE)
                if m:
                    nome = re.sub(r"\s+", " ", m.group(1)).strip()
                    tokens = set(_norm(nome).split())
                    if len(nome.split()) >= 2 and not (tokens & TERMOS_EMPRESA):
                        return nome.title()
            if idx + 1 < len(linhas):
                cand = linhas[idx + 1]
                tokens = set(_norm(cand).split())
                if len(cand.split()) >= 2 and not re.search(r"\d", cand) and not (tokens & TERMOS_EMPRESA):
                    return re.sub(r"\s+", " ", cand).strip().title()
    return ""


def extrair_nome_funcion(texto):
    t = str(texto or "")
    m = re.search(r"FUNCION[\w\.º°]*\s*[:\-]\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]{4,}?)(?:\s+FUN[CÇ][AÃ]O|$)", t, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"FUNCIONARIO[\w\.º°]*\s*[:\-]\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]{4,}?)(?:\s+FUN[CÇ][AÃ]O|$)", t, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"ASSINATURA\s+DE\s*[:\-]\s*([A-ZÀ-Ú][A-ZÀ-Ú\s]{4,}?)\s*(?:\||\n|$)", t, flags=re.IGNORECASE)
    if not m:
        return ""
    nome = re.sub(r"\s+", " ", m.group(1)).strip()
    tokens = set(_norm(nome).split())
    if any(tok in TERMOS_EMPRESA or tok in STOPWORDS_NOME for tok in tokens):
        return ""
    if len(nome.split()) < 2:
        return ""
    return nome.title()


def evidencia_assinatura_manual_texto(texto):
    linhas = [ln.strip() for ln in str(texto or "").splitlines() if ln.strip()]
    norm_linhas = [_norm(ln) for ln in linhas]
    anchors = ("ASSINATURA DO EMPREGADO", "ASSINATURA DO FUNCIONARIO", "ASSINATURA")
    bloqueios = {"RECEBI", "SALDO", "PORTARIA", "REGISTRO", "OCORRENCIAS", "OCORRÊNCIAS"}

    for i, ln in enumerate(norm_linhas):
        if not any(a in ln for a in anchors):
            continue
        janela = linhas[max(0, i - 4): i]
        for raw in reversed(janela):
            token = _norm(raw)
            if any(b in token for b in bloqueios):
                continue
            if len(raw) < 4 or len(raw) > 45:
                continue
            if re.search(r"[A-Za-zÀ-Ú]{3,}", raw) and not re.search(r"\d{2}/\d{2}", raw):
                return True, f"Evidencia textual de assinatura proxima ao campo: '{raw[:30]}'"
        return False, "Campo de assinatura encontrado sem evidencia textual forte da rubrica."
    return False, "Campo de assinatura nao encontrado no texto."


def _nome_heuristico(texto):
    candidatos = re.findall(r"\b[A-ZÀ-Ú]{2,}(?:\s+[A-ZÀ-Ú]{2,}){1,5}\b", _norm(texto))
    for c in candidatos:
        tokens = c.split()
        if len(tokens) < 2:
            continue
        if any(tok in STOPWORDS_NOME for tok in tokens):
            continue
        if any(tok in TERMOS_EMPRESA for tok in tokens):
            continue
        if len(" ".join(tokens)) >= 8:
            return c.title()
    return ""


def _detectar_ancoras(texto):
    t = _norm(texto)
    return [a for a in ANCORAS_BASE if _norm(a) in t]


def _layout_files():
    LAYOUT_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(LAYOUT_DIR.glob("*.json"))


def _load_layouts():
    layouts = []
    for f in _layout_files():
        try:
            layouts.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return layouts


def _score_layout(layout, ancoras):
    la = set([_norm(x) for x in layout.get("ancoras_fortes", [])])
    cur = set([_norm(x) for x in ancoras])
    if not la:
        return 0.0
    inter = len(la & cur)
    uniao = max(1, len(la | cur))
    return round(inter / uniao, 4)


def identificar_layout_cartao_ponto(texto, paginas=None):
    ancoras = _detectar_ancoras(texto)
    layouts = _load_layouts()

    melhor = None
    melhor_score = 0.0
    for layout in layouts:
        s = _score_layout(layout, ancoras)
        if s > melhor_score:
            melhor = layout
            melhor_score = s

    if melhor and melhor_score >= float(melhor.get("score_minimo_layout", 0.60)):
        return {
            "layout_id": melhor.get("id"),
            "layout_conhecido": True,
            "score": melhor_score,
            "ancoras_encontradas": ancoras,
            "campos_detectados": ["nome", "competencia", "marcacoes", "assinatura"],
            "estrategia": "layout_reutilizado",
            "layout": melhor,
        }

    return {
        "layout_id": "",
        "layout_conhecido": False,
        "score": melhor_score,
        "ancoras_encontradas": ancoras,
        "campos_detectados": ["nome", "competencia", "marcacoes", "assinatura"],
        "estrategia": "layout_novo_por_ancoras",
        "layout": None,
    }


def salvar_layout_cartao_ponto(ancoras, fornecedor="desconhecido"):
    layouts = _load_layouts()
    novo_id = f"cartao_ponto_modelo_{len(layouts)+1:03d}"
    agora = datetime.now().isoformat(timespec="seconds")
    layout = {
        "id": novo_id,
        "tipo_documento": "cartao_ponto",
        "fornecedor": fornecedor,
        "ancoras_fortes": sorted(set(ancoras)),
        "ancoras_nome": ["FUNCIONARIO", "FUNCIONÁRIO", "COLABORADOR", "EMPREGADO", "NOME"],
        "ancoras_competencia": ["COMPETENCIA", "COMPETÊNCIA", "PERIODO", "PERÍODO"],
        "ancoras_marcacoes": ["DATA", "ENTRADA", "SAIDA", "SAÍDA", "INTERVALO", "HORAS"],
        "ancoras_assinatura": ["ASSINATURA", "RUBRICA"],
        "campos_obrigatorios": ["nome", "competencia", "marcacoes", "assinatura"],
        "zona_assinatura": "rodape",
        "estrategia_nome": "buscar_nome_esperado_ou_ancora",
        "estrategia_competencia": "regex_global_e_ancora",
        "estrategia_marcacoes": "regex_datas_horarios",
        "score_minimo_layout": 0.60,
        "criado_em": agora,
        "atualizado_em": agora,
    }
    path = LAYOUT_DIR / f"{novo_id}.json"
    path.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    return layout


def extrair_campos_cartao_ponto(texto, nomes_esperados=None, competencia_esperada=None, layout=None):
    nomes_esperados = nomes_esperados or []
    t_norm = _norm(texto)

    nome = ""
    for esperado in nomes_esperados:
        if _norm(esperado) and _norm(esperado) in t_norm:
            nome = str(esperado).title()
            break

    if not nome:
        nome = _nome_por_ancora(texto)
    if not nome:
        nome = _nome_heuristico(texto)
    if nome and any(t in _norm(nome).split() for t in ["EMPREGADOR", "RAZAO", "SOCIAL", "CLIENTE", "ORDEM"]):
        nome = ""

    competencia = _parse_competencia(texto)

    datas = _extrair_datas(texto)
    horarios = _extrair_horarios(texto)
    dias_marcados = len(set([d[:5] for d in datas if len(d) >= 5]))
    marcacoes_ok = bool((dias_marcados >= 3 and len(horarios) >= 6) or len(horarios) >= 20)

    avisos = []
    if not nome:
        avisos.append("nome_nao_identificado")
    if not competencia:
        avisos.append("competencia_nao_identificada")
    if not marcacoes_ok:
        avisos.append("marcacoes_insuficientes")
    if competencia_esperada and competencia and competencia != competencia_esperada:
        avisos.append("competencia_divergente")

    pontos = 0
    if nome:
        pontos += 25
    if competencia and (not competencia_esperada or competencia == competencia_esperada):
        pontos += 25
    if marcacoes_ok:
        pontos += 25

    confianca = round(min(1.0, pontos / 100.0), 4)

    return {
        "nome_colaborador": nome,
        "competencia": competencia,
        "marcacoes_encontradas": marcacoes_ok,
        "datas_encontradas": datas,
        "horarios_encontrados": horarios,
        "qtd_dias_marcados": dias_marcados,
        "qtd_horarios": len(horarios),
        "avisos": avisos,
        "confianca": confianca,
    }


def score_e_status_colaborador(nome_ok, competencia_ok, marcacoes_ok, assinatura_ok):
    score = 0
    if nome_ok:
        score += 25
    if competencia_ok:
        score += 25
    if marcacoes_ok:
        score += 25
    if assinatura_ok:
        score += 25

    if not competencia_ok and score >= 80:
        return score, "INCONCLUSIVO"
    if score >= 80:
        return score, "OK"
    if score >= 50:
        return score, "INCONCLUSIVO"
    return score, "FALTANDO"


def deve_chamar_ia_cartao_ponto(resultado_local):
    if not resultado_local:
        return True, "resultado_local_vazio"

    if not resultado_local.get("layout_conhecido"):
        return True, "layout_desconhecido"

    colaboradores = resultado_local.get("colaboradores", [])
    if not colaboradores:
        return True, "sem_colaboradores"

    for c in colaboradores:
        if not c.get("nome"):
            return True, "nome_nao_encontrado"
        if not c.get("competencia"):
            return True, "competencia_nao_encontrada"
        if not c.get("marcacoes"):
            return True, "parser_marcacoes_falhou"
        if c.get("status") == "INCONCLUSIVO":
            return True, "status_inconclusivo"

    return False, "resultado_local_suficiente"
