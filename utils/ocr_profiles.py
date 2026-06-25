import json
import re
from pathlib import Path


PROFILE_ROOT = Path("data") / "layouts"


def _norm_texto(valor):
    return str(valor or "").strip().upper()


def carregar_perfis(tipo_documento):
    pasta = PROFILE_ROOT / str(tipo_documento or "").strip()
    if not pasta.exists():
        return []

    perfis = []
    for arquivo in sorted(pasta.glob("*.json")):
        try:
            perfil = json.loads(arquivo.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(perfil, dict):
            perfil["_arquivo"] = str(arquivo)
            perfis.append(perfil)
    return perfis


def _normalizar_texto(valor):
    return re.sub(r"\s+", " ", str(valor or "").strip().upper())


def _ancoras_perfil(perfil):
    ancoras = []

    descricao = perfil.get("descricao")
    if descricao:
        ancoras.extend(re.split(r"[;,\n/|]+", str(descricao)))

    for campo, definicao in (perfil.get("campos") or {}).items():
        if not isinstance(definicao, dict):
            continue
        label = definicao.get("label")
        if label:
            ancoras.append(label)
        ancoras.append(str(campo).replace("_", " "))

    match = perfil.get("match") or {}
    for item in match.get("filename_contains") or []:
        if item:
            ancoras.append(item)

    return [a for a in (_normalizar_texto(x) for x in ancoras) if a]


def encontrar_perfil_documento(tipo_documento, caminho_arquivo=None, arquivo_hash=None):
    nome_arquivo = _norm_texto(Path(caminho_arquivo).name if caminho_arquivo else "")
    caminho_completo = _norm_texto(caminho_arquivo)

    for perfil in carregar_perfis(tipo_documento):
        match = perfil.get("match") or {}
        hash_esperado = _norm_texto(match.get("file_hash_sha256"))
        if hash_esperado and arquivo_hash and hash_esperado == _norm_texto(arquivo_hash):
            return perfil

        nomes = [_norm_texto(item) for item in (match.get("filename_contains") or []) if item]
        if nomes and any(item in nome_arquivo or item in caminho_completo for item in nomes):
            return perfil

    return None


def encontrar_perfil_por_texto(tipo_documento, texto, limite=0.25):
    texto_norm = _normalizar_texto(texto)
    if not texto_norm:
        return None, 0.0

    melhor = None
    melhor_score = 0.0

    for perfil in carregar_perfis(tipo_documento):
        ancoras = _ancoras_perfil(perfil)
        if not ancoras:
            continue

        hits = 0
        relevantes = 0
        for ancora in ancoras:
            if len(ancora) < 4:
                continue
            relevantes += 1
            if ancora in texto_norm:
                hits += 1

        if not relevantes:
            continue

        score = hits / relevantes
        if "NOME DO FUNCIONARIO" in texto_norm or "NOME DO FUNCIONÁRIO" in texto_norm:
            if any("NOME DO FUNCIONARIO" in a or "NOME DO FUNCIONÁRIO" in a for a in ancoras):
                score += 0.10
        if any(item in texto_norm for item in ("VALOR LIQUIDO", "VALOR LQUIDO", "LIQUIDO A RECEBER", "LIQUIDOARECEBER", "TOTAL LIQUIDO", "TOTAL LQUIDO")):
            if any(
                termo in a
                for a in ancoras
                for termo in ("VALOR LIQUIDO", "VALOR LQUIDO", "LIQUIDO A RECEBER", "TOTAL LIQUIDO", "VALOR A RECEBER")
            ):
                score += 0.10

        score = min(1.0, round(score, 4))
        if score > melhor_score:
            melhor = perfil
            melhor_score = score

    if melhor and melhor_score >= limite:
        return melhor, melhor_score
    return None, 0.0
