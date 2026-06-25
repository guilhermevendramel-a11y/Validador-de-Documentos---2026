# -*- coding: utf-8 -*-
"""
folha_model_extractor.py

Extrator genérico de FOLHA DE PAGAMENTO para devolver ao Codex e integrar no projeto.

Objetivo:
- Identificar o modelo/layout da folha;
- Extrair razão social da empresa;
- Extrair competência;
- Extrair nomes dos colaboradores.

IMPORTANTE:
- Não usa nomes fixos de colaboradores;
- Não usa valores fixos;
- Não depende de uma única empresa;
- Funciona por âncoras, regex e padrões de layout;
- Mantém fallback genérico quando não reconhece o modelo.

Uso rápido no terminal:
    python folha_model_extractor.py "arquivo.pdf"
    python folha_model_extractor.py "pasta_com_pdfs" --saida resultado.json

Integração no projeto:
    from folha_model_extractor import extrair_folha_pagamento
    resultado = extrair_folha_pagamento("/caminho/folha.pdf")

Retorno principal:
    {
      "modelo": "sci_visual_espelho",
      "confianca_modelo": 0.92,
      "razao_social": "EMPRESA EXEMPLO LTDA",
      "competencia": "04/2026",
      "nomes": ["COLABORADOR UM", "COLABORADOR DOIS"],
      "evidencias": {...},
      "avisos": [...]
    }
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ============================================================
# Normalização básica
# ============================================================

MESES = {
    "JANEIRO": "01",
    "FEVEREIRO": "02",
    "MARCO": "03",
    "MARÇO": "03",
    "ABRIL": "04",
    "MAIO": "05",
    "JUNHO": "06",
    "JULHO": "07",
    "AGOSTO": "08",
    "SETEMBRO": "09",
    "OUTUBRO": "10",
    "NOVEMBRO": "11",
    "DEZEMBRO": "12",
}

SUFIXOS_EMPRESA = (
    "LTDA", "LTDA ME", "ME", "EPP", "EIRELI", "S/A", "SA", "S.A", "S.A.",
    "SOCIEDADE", "INDUSTRIA", "COMERCIO", "SERVICOS", "SERVIÇOS",
    "ENGENHARIA", "CONSTRUCOES", "CONSTRUÇÕES", "EMPREITEIRA",
)

PALAVRAS_INVALIDAS_NOME = {
    "EMPRESA", "CNPJ", "CEI", "CPF", "ENDERECO", "ENDEREÇO", "BAIRRO", "CIDADE", "UF",
    "PAGINA", "PÁGINA", "FOLHA", "PAGAMENTO", "EXTRATO", "MENSAL", "RESUMO",
    "PROVENTOS", "DESCONTOS", "VENCIMENTOS", "LIQUIDO", "LÍQUIDO", "BASE", "FGTS",
    "INSS", "IRRF", "IR", "DEP", "DSR", "D.S.R", "TOTAL", "TOTAIS", "SALARIO", "SALÁRIO", "FUNCAO", "FUNÇÃO",
    "CARGO", "REFERENCIA", "REFERÊNCIA", "VALOR", "QTDE", "DESCRICAO", "DESCRIÇÃO",
    "ADMISSAO", "ADMISSÃO", "SITUACAO", "SITUAÇÃO", "HORAS", "MES", "MÊS",
    "COD", "CODIGO", "CÓDIGO", "RUBRICA", "DATA", "PERIODO", "PERÍODO",
    "PAGTO", "PAGAMENTO", "DESC", "DESCONTO", "ADIANTAMENTO", "NORMAL", "TRANSPORTE",
    "CONTRIBUICAO", "CONTRIBUIÇÃO", "ASSISTENCIAL", "REFLEXO", "PREMIO", "PRÊMIO",
    "USUARIO", "USUÁRIO", "SISTEMA", "LICENCIADO", "CONTABILIDADE", "CONTÁBIL",
    "RAZAO", "RAZÃO", "SOCIAL", "ADIC", "ADICIONAL", "ADIANT", "SALARIAL", "VALE",
    "FALTA", "FALTAS", "GFIP", "REND", "RENDTRIBUT", "TRIBUT", "OBRA", "BAS", "CAL",
    "EMPREG", "EMPR", "VAL", "VENCS", "DESCS", "TOT", "INTEG", "RUBRICA",
    "RESCISAO", "RESCISÃO", "FERIAS", "FÉRIAS", "REEMBOLSO", "RECARGA", "CELULAR",
    "NORMAIS", "AJUDA", "CUSTO", "CESTA", "BASICA", "BÁSICA",
}

# Palavras comuns de função/cargo para separar "nome + função" em alguns modelos.
# Não são nomes fixos; são termos genéricos de cargo.
FUNCAO_KEYWORDS = {
    "AJUDANTE", "AUXILIAR", "ASSISTENTE", "ANALISTA", "ENCARREGADO", "SOLDADOR",
    "ENCANADOR", "MONTADOR", "SERRALHEIRO", "TECNICO", "TÉCNICO", "OPERADOR",
    "MOTORISTA", "VIGIA", "PORTEIRO", "PEDREIRO", "CALCETEIRO", "DIRETOR", "GERENTE",
    "CONTROLADOR", "INSTALADOR", "ADMINISTRATIVO", "ADMINISTRATIVA", "DESENHISTA",
    "PINTOR", "OFICIAL", "POLIVALENTE", "MANUTENCAO", "MANUTENÇÃO", "PLENO",
    "JUNIOR", "JÚNIOR", "SENIOR", "SÊNIOR", "MEIO", "OFICIAL", "PRODUCAO", "PRODUÇÃO",
}

PREPOSICOES_NOME = {"DE", "DA", "DAS", "DO", "DOS", "E", "DI", "DU", "DEL", "DELA", "VAN", "VON"}


def remover_acentos(texto: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", str(texto or ""))
        if unicodedata.category(ch) != "Mn"
    )


def norm(texto: str) -> str:
    """Normaliza para comparação: sem acento, uppercase e espaços simples."""
    texto = remover_acentos(str(texto or ""))
    texto = texto.replace("\u00a0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\s*\n\s*", "\n", texto)
    return texto.upper().strip()


def compactar_linha(texto: str) -> str:
    texto = str(texto or "").replace("\u00a0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    return texto.strip()


def linhas_validas(texto: str) -> List[str]:
    return [compactar_linha(l) for l in str(texto or "").splitlines() if compactar_linha(l)]


def dedup_preservando_ordem(seq: Iterable[str]) -> List[str]:
    vistos = set()
    out = []
    for item in seq:
        chave = norm(item)
        if chave and chave not in vistos:
            vistos.add(chave)
            out.append(item.strip())
    return out


# ============================================================
# Dataclasses de retorno
# ============================================================

@dataclass
class ResultadoFolha:
    modelo: str
    confianca_modelo: float
    razao_social: str
    competencia: str
    nomes: List[str]
    evidencias: Dict[str, object]
    avisos: List[str]


# ============================================================
# Extração de texto de PDF com fallback OCR opcional
# ============================================================

def extrair_texto_pdf(
    pdf_path: str | Path,
    max_paginas: Optional[int] = None,
    usar_ocr_se_necessario: bool = True,
    dpi: int = 220,
) -> Tuple[str, List[str]]:
    """
    Extrai texto do PDF. Primeiro tenta PyMuPDF; se vier pouco texto, tenta OCR.

    Dependências opcionais para OCR:
        pip install pymupdf pillow pytesseract
    E o Tesseract instalado no Windows/Linux.

    Caso o projeto já possua uma função própria de OCR, o Codex pode substituir esta função
    e continuar usando extrair_folha_pagamento_de_texto(texto).
    """
    avisos: List[str] = []
    pdf_path = Path(pdf_path)

    try:
        import fitz  # PyMuPDF
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "PyMuPDF/fitz não está disponível. Instale com: pip install pymupdf "
            "ou passe o texto OCR diretamente para extrair_folha_pagamento_de_texto()."
        ) from exc

    textos_por_pagina: List[str] = []
    doc = fitz.open(str(pdf_path))
    total_paginas = len(doc)
    limite = min(total_paginas, max_paginas) if max_paginas else total_paginas

    paginas_com_pouco_texto = []
    for i in range(limite):
        pagina = doc[i]
        txt = pagina.get_text("text") or ""
        textos_por_pagina.append(txt)
        if len(norm(txt)) < 80:
            paginas_com_pouco_texto.append(i)

    texto = "\n".join(textos_por_pagina)

    # Se o PDF for imagem/escaneado, tenta OCR apenas nas páginas com pouco texto.
    if usar_ocr_se_necessario and paginas_com_pouco_texto:
        try:
            from PIL import Image
            import pytesseract

            avisos.append(
                f"OCR aplicado em {len(paginas_com_pouco_texto)} página(s) com pouco texto extraído."
            )
            matriz = fitz.Matrix(dpi / 72, dpi / 72)
            for i in paginas_com_pouco_texto:
                pagina = doc[i]
                pix = pagina.get_pixmap(matrix=matriz, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr = pytesseract.image_to_string(img, lang="por+eng", config="--psm 6")
                textos_por_pagina[i] = ocr
            texto = "\n".join(textos_por_pagina)
        except Exception as exc:
            avisos.append(
                "Não foi possível aplicar OCR automático. "
                f"Motivo: {type(exc).__name__}: {exc}"
            )

    doc.close()
    return texto, avisos


# ============================================================
# Detecção de modelo/layout
# ============================================================

MODELOS = [
    {
        "id": "sci_visual_espelho",
        "marcadores": [
            "ESPELHO DA FOLHA REFERENTE", "SISTEMA DE FOLHA SCI VISUAL",
            "CNPJ/CEI", "NOME DO FUNCIONARIO", "TOTAL DE PROVENTOS",
        ],
    },
    {
        "id": "extrato_mensal",
        "marcadores": [
            "EXTRATO MENSAL", "EMPR.", "SITUACAO", "VINCULO", "LIQUIDO:",
        ],
    },
    {
        "id": "relacao_calculo_analitico",
        "marcadores": [
            "RELACAO DE CALCULO", "ANALITICO CONTRATOS", "FUNC:", "PROVENTOS:", "LIQUIDO:",
        ],
    },
    {
        "id": "microsiga_top_service",
        "marcadores": [
            "MICROSIGA", "SIGA", "GPER", "RESUMO DE FOLHA", "ROTEIRO: FOL/AUT",
        ],
    },
    {
        "id": "cucafresca_resumo_funcionarios",
        "marcadores": [
            "RESUMO POR FUNCIONARIOS", "SOCIOS E AUTONOMOS DO MES", "CUCAFRESCA",
            "COD. NOME DO FUNCIONARIO", "VALOR LIQUIDO",
        ],
    },
    {
        "id": "folha_empregados_femav",
        "marcadores": [
            "FOLHA DE PAGAMENTO DE EMPREGADOS", "DIVISAO RH", "N.REG", "CPF NOME CBO FUNCAO",
        ],
    },
    {
        "id": "folha_pagamento_analitica",
        "marcadores": [
            "FOLHA DE PAGAMENTO ANALITICA", "CODIGO", "NOME", "SAL. CONTRATUAL", "RECIBO",
        ],
    },
    {
        "id": "delphos_folha_pagamento",
        "marcadores": [
            "DELPHOS", "FOLHA DE PAGAMENTO", "EMPREGADOR", "REGISTRO NOME", "TOTAL LIQUIDO",
        ],
    },
    {
        "id": "folha_analitica_lote",
        "marcadores": [
            "FOLHA ANALITICA DE", "EMP-FIL", "FUNCIONARIO", "LIQUIDO (T O T A L)",
        ],
    },
    {
        "id": "folha_pagamento_cd_nome_funcao",
        "marcadores": [
            "FOLHA DE PAGAMENTO", "COD: NOME: FUNCAO", "PROVENTOS:", "DESCONTOS:", "LIQUIDO:",
        ],
    },
]


def detectar_modelo(texto: str) -> Tuple[str, float, Dict[str, object]]:
    t = norm(texto)
    melhor_id = "generico"
    melhor_score = 0.0
    detalhe = {}

    for modelo in MODELOS:
        marcadores = modelo["marcadores"]
        encontrados = [m for m in marcadores if norm(m) in t]
        score = len(encontrados) / max(1, len(marcadores))
        # Pequeno bônus para marcadores fortes.
        if modelo["id"] == "extrato_mensal" and "EXTRATO MENSAL" in t and "EMPR." in t:
            score += 0.15
        if modelo["id"] == "sci_visual_espelho" and "ESPELHO DA FOLHA" in t:
            score += 0.15
        if modelo["id"] == "delphos_folha_pagamento" and "DELPHOS" in t:
            score += 0.10
        score = min(score, 1.0)
        if score > melhor_score:
            melhor_score = score
            melhor_id = modelo["id"]
            detalhe = {"marcadores_encontrados": encontrados, "marcadores_total": marcadores}

    return melhor_id, round(melhor_score, 3), detalhe


# ============================================================
# Extração de razão social
# ============================================================

def limpar_razao_social(valor: str) -> str:
    v = compactar_linha(valor)
    v = re.sub(r"^(Empresa|Emp\.?-?Fil|Empregador|Raz[aã]o Social)\s*[:\-]?\s*", "", v, flags=re.I)
    v = re.sub(r"^\d{1,6}\s*[-–]\s*", "", v)
    v = re.sub(r"^\d{1,6}\s+(?=[A-ZÁÉÍÓÚÃÕÇ])", "", v)
    v = re.sub(r"\s+CNPJ\b.*$", "", v, flags=re.I)
    v = re.sub(r"\s+CNPJ/CEI\b.*$", "", v, flags=re.I)
    v = re.sub(r"\s+\d{2}\.?\d{3}\.?\d{3}/\d{4}-\d{2}.*$", "", v)
    v = re.sub(r"\s+(0[1-9]|1[0-2])\s*/\s*(20\d{2}).*$", "", v)
    v = re.sub(r"\s+IE\b.*$", "", v, flags=re.I)
    v = re.sub(r"\s+\(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\).*$", "", v)
    v = re.sub(r"\s+\d{2}/\d{2}/\d{4}.*$", "", v)
    v = re.sub(r"\s+P[áa]g(?:ina)?[:\s].*$", "", v, flags=re.I)
    v = re.sub(r"\s+Telefone:.*$", "", v, flags=re.I)
    v = re.sub(r"\s+Inscri[cç][aã]o.*$", "", v, flags=re.I)
    v = re.sub(r"\s+Complemento:.*$", "", v, flags=re.I)
    v = re.sub(r"\s+Endere[cç]o:.*$", "", v, flags=re.I)
    v = re.sub(r"\s+[A-ZÁÉÍÓÚÃÕÇ .]+/[A-Z]{2}\s*[-–]?\s*$", "", v, flags=re.I)
    v = re.sub(r"\s+\([^)]*$", "", v)
    v = compactar_linha(v)
    return v.strip(" -–:")


def parece_razao_social(valor: str) -> bool:
    if not valor:
        return False
    vn = norm(valor)
    if len(vn) < 8:
        return False
    if any(noise in vn for noise in ["FOLHA DE PAGAMENTO", "EXTRATO MENSAL", "PAGINA", "EMISSAO"]):
        return False
    return any(norm(suf) in vn for suf in SUFIXOS_EMPRESA)


def extrair_razao_social(texto: str, modelo: str = "") -> Tuple[str, Dict[str, str]]:
    evidencias: Dict[str, str] = {}
    raw = texto or ""
    t = raw.replace("\u00a0", " ")

    padroes = [
        # Empresa: 0568 - PREMIER ... 24/04/2026 / CNPJ etc.
        ("empresa_codigo_ate_data", r"Empresa\s*:\s*\d{1,6}\s*[-–]\s*(.+?)(?=\s+\d{2}/\d{2}/\d{4}|\s+CNPJ|\s+CNPJ/CEI|\s+Inscri[cç][aã]o|\s+Telefone|\n)"),
        ("empresa_codigo_cnpj", r"Empresa\s*:\s*\d{1,6}\s*[-–]\s*(.+?)\s+CNPJ(?:/CEI)?\s*[:\-]?"),
        # Emp-Fil:001-001 EFETIVA RH - ... (33.069...)
        ("emp_fil_parenteses_cnpj", r"Emp\.?-?Fil\s*:\s*\d+[-–]\d+\s+(.+?)\s*\(\s*\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\s*\)"),
        # EMPREGADOR: 009 DELPHOS ... C.N.P.J.
        ("empregador_linha", r"EMPREGADOR\s*:\s*\d{1,6}\s+(.+?)(?=\s+C\.?N\.?P\.?J|\n)"),
        # Empresa : SOLLO ... (00749) / CNPJ etc.
        ("empresa_dois_pontos", r"Empresa\s*[:：]\s*(.+?)(?=\s*\(\d{3,}\)|\s+CNPJ|\n)"),
        # Topo tipo: AGEPLAN ENGENHARIA - CONSTRUÇÕES LTDA \n ... CNPJ
        ("linha_empresa_com_sufixo", r"(?m)^\s*([A-ZÁÉÍÓÚÃÕÇ0-9 .,&'\-]+(?:LTDA|LTDA ME|EIRELI|EPP|S/A|S\.A\.?|SA))\s*$"),
        # Serviço: 1 - EMPRESA - CNPJ:...
        ("servico_empresa", r"Servi[cç]o\s*:\s*\d+\s*[-–]\s*(.+?)\s*[-–]\s*(?:CNPJ|CNO)\s*[:\-]"),
    ]

    for origem, padrao in padroes:
        for m in re.finditer(padrao, t, flags=re.I | re.S):
            cand = limpar_razao_social(m.group(1))
            # Evita pegar a empresa do escritório contábil no rodapé, mas aceita se for a única.
            if parece_razao_social(cand):
                evidencias["razao_social_origem"] = origem
                evidencias["razao_social_trecho"] = compactar_linha(m.group(0))[:250]
                return cand, evidencias

    # Fallback: procurar linha com sufixo empresarial perto do topo.
    for linha in linhas_validas(t)[:60]:
        cand = limpar_razao_social(linha)
        if parece_razao_social(cand):
            evidencias["razao_social_origem"] = "fallback_linha_topo"
            evidencias["razao_social_trecho"] = linha[:250]
            return cand, evidencias

    return "", evidencias


# ============================================================
# Extração de competência
# ============================================================

def mes_extenso_para_num(mes: str) -> Optional[str]:
    return MESES.get(norm(mes).replace(" ", ""))


def extrair_competencia(texto: str) -> Tuple[str, Dict[str, str]]:
    evidencias: Dict[str, str] = {}
    t = texto or ""
    tn = norm(t)

    padroes = [
        ("competencia_mm_aaaa", r"Compet[eê]ncia\s*[:\-]?\s*(0[1-9]|1[0-2])\s*/\s*(20\d{2})"),
        ("referencia_mm_aaaa", r"Refer[eê]ncia\s*[:\-]?\s*(0[1-9]|1[0-2])\s*/\s*(20\d{2})"),
        ("isolado_topo_mm_aaaa", r"(?m)^\s*(0[1-9]|1[0-2])\s*/\s*(20\d{2})\s*$"),
        ("periodo_datas", r"Per[ií]odo\s*(?:de)?\s*[:\-]?\s*\d{2}\s*/\s*(0[1-9]|1[0-2])\s*/\s*(20\d{2})\s*(?:a|-|à)"),
        ("ref_datas", r"Ref\.?\s*[:\-]?\s*\d{2}\s*/\s*(0[1-9]|1[0-2])\s*/\s*(20\d{2})\s*(?:a|-|à)"),
        ("data_periodo", r"Data do Per[ií]odo\s*[:\-]?\s*\d{2}\s*/\s*(0[1-9]|1[0-2])\s*/\s*(20\d{2})"),
    ]

    for origem, padrao in padroes:
        m = re.search(padrao, t, flags=re.I)
        if m:
            comp = f"{m.group(1)}/{m.group(2)}"
            evidencias["competencia_origem"] = origem
            evidencias["competencia_trecho"] = compactar_linha(m.group(0))[:200]
            return comp, evidencias

    # Abril/2026, Folha Analitica de Abril/2026, mês de ABRIL DE 2026
    padroes_mes_extenso = [
        ("mes_de_ano", r"M[ÊE]S\s+DE\s+([A-ZÁÉÍÓÚÃÕÇ]+)\s+DE\s+(20\d{2})"),
        ("mes_de_mes_barra_ano", r"M[ÊE]S\s+DE\s+([A-ZÁÉÍÓÚÃÕÇ]+)\s*/\s*(20\d{2})"),
        ("folha_analitica_mes", r"Folha\s+Anal[ií]tica\s+de\s+([A-ZÁÉÍÓÚÃÕÇ]+)\s*/\s*(20\d{2})"),
        ("competencia_mes_extenso", r"Compet[eê]ncia\s*[:\-]?\s*([A-ZÁÉÍÓÚÃÕÇ]+)\s*/\s*(20\d{2})"),
    ]
    for origem, padrao in padroes_mes_extenso:
        m = re.search(padrao, t, flags=re.I)
        if m:
            mes = mes_extenso_para_num(m.group(1))
            if mes:
                comp = f"{mes}/{m.group(2)}"
                evidencias["competencia_origem"] = origem
                evidencias["competencia_trecho"] = compactar_linha(m.group(0))[:200]
                return comp, evidencias

    # Periodo: 202604
    m = re.search(r"Per[ií]odo\s*[:\-]?\s*(20\d{2})(0[1-9]|1[0-2])\b", t, flags=re.I)
    if m:
        comp = f"{m.group(2)}/{m.group(1)}"
        evidencias["competencia_origem"] = "periodo_yyyymm"
        evidencias["competencia_trecho"] = compactar_linha(m.group(0))[:200]
        return comp, evidencias

    # Fallback: primeira ocorrência MM/YYYY no topo.
    m = re.search(r"\b(0[1-9]|1[0-2])\s*/\s*(20\d{2})\b", tn[:4000])
    if m:
        comp = f"{m.group(1)}/{m.group(2)}"
        evidencias["competencia_origem"] = "fallback_primeiro_mm_aaaa_topo"
        evidencias["competencia_trecho"] = m.group(0)
        return comp, evidencias

    return "", evidencias


# ============================================================
# Extração de nomes
# ============================================================

def limpar_nome(valor: str) -> str:
    v = compactar_linha(valor)
    v = re.sub(r"^[\d.\-\/]+\s+", "", v)
    v = re.sub(r"\bCPF\b.*$", "", v, flags=re.I)
    v = re.sub(r"\bSitua[cç][aã]o\b.*$", "", v, flags=re.I)
    v = re.sub(r"\bAdmiss[aã]o\b.*$", "", v, flags=re.I)
    v = re.sub(r"\bAdmitido\b.*$", "", v, flags=re.I)
    v = re.sub(r"\bSal[aá]rio\b.*$", "", v, flags=re.I)
    v = re.sub(r"\bC\.B\.O\b.*$", "", v, flags=re.I)
    v = re.sub(r"\bCBO\b.*$", "", v, flags=re.I)
    v = re.sub(r"\s+[-–]\s*$", "", v)
    v = re.sub(r"\s+", " ", v).strip(" -–:.|*")
    return v


def cortar_funcao_do_final(valor: str) -> str:
    """
    Em alguns modelos vem 'COD NOME FUNÇÃO'.
    Cortamos a partir de palavras genéricas de cargo/função.
    """
    tokens = compactar_linha(valor).split()
    if len(tokens) < 3:
        return valor

    for i in range(2, len(tokens)):
        tok = norm(tokens[i]).replace(".", "")
        if tok in {norm(x).replace(".", "") for x in FUNCAO_KEYWORDS}:
            return " ".join(tokens[:i])
    return valor


def nome_valido(nome: str) -> bool:
    nome = limpar_nome(nome)
    if not nome:
        return False
    n = norm(nome)

    if len(n) < 7 or len(n) > 90:
        return False
    if any(ch.isdigit() for ch in n):
        return False
    partes_raw = n.split()
    partes_sem_pontuacao = [re.sub(r"[^A-Z0-9ÁÉÍÓÚÃÕÇ]", "", p) for p in partes_raw]
    invalidas_norm = {norm(p).replace(".", "") for p in PALAVRAS_INVALIDAS_NOME}
    if any(p in invalidas_norm for p in partes_sem_pontuacao if p):
        return False
    if any(inval in n for inval in ["TOTAL", "BASE ", "FOLHA", "PROVENTOS", "DESCONTOS", "LIQUIDO", "CNPJ"]):
        return False

    partes = n.split()

    # Se o candidato começa com palavra típica de cargo/função, normalmente é função, não nome.
    # Ex.: "AUXILIAR ADMINISTRATIVO", "MONTADOR DE ESTRUTURA", "DESC. ADIANTAMENTO".
    primeiro = partes[0].replace(".", "") if partes else ""
    if primeiro in {norm(x).replace(".", "") for x in FUNCAO_KEYWORDS}:
        return False

    partes_nome = [p for p in partes if p not in PREPOSICOES_NOME]
    if len(partes_nome) < 2:
        return False

    # Evita capturar razão social como nome. Atenção: ME/SA precisam ser palavra inteira,
    # não substring dentro de sobrenomes como SCHMOELLER.
    for suf in SUFIXOS_EMPRESA:
        suf_n = norm(suf).replace(".", "")
        n_sem_ponto = n.replace(".", "")
        if re.search(r"(?:^|\s)" + re.escape(suf_n) + r"(?:$|\s)", n_sem_ponto):
            return False

    # Evita linhas muito parecidas com descrições de eventos.
    eventos = {"SALARIO", "HORAS", "EXTRAS", "FALTAS", "ADIANTAMENTO", "VALE", "TRANSPORTE", "CESTA", "BASICA"}
    if len(set(partes) & eventos) >= 2:
        return False

    return True


def adicionar_candidato(candidatos: List[str], valor: str):
    nome = limpar_nome(cortar_funcao_do_final(valor))
    if nome_valido(nome):
        candidatos.append(nome.upper())


def extrair_nomes(texto: str, modelo: str = "") -> Tuple[List[str], Dict[str, object]]:
    t = texto or ""
    candidatos: List[str] = []
    evidencias: Dict[str, object] = {"padroes_usados": []}

    padroes: List[Tuple[str, str]] = [
        # Senior / Relação de Cálculo: Func: 18 NOME Adm...
        ("func_adm", r"\bFunc\s*[:.]\s*\d{1,8}\s+([A-ZÁÉÍÓÚÃÕÇ][A-ZÁÉÍÓÚÃÕÇ' .\-]{5,}?)\s+Adm\b"),
        # Extrato Mensal: Empr.: 171 NOME Situação...
        ("empr_situacao", r"\bEmpr\.?:\s*\d{1,8}\s+([A-ZÁÉÍÓÚÃÕÇ][A-ZÁÉÍÓÚÃÕÇ' .\-]{5,}?)\s+Situa[cç][aã]o\b"),
        # Folha Analítica lote: Funcionario 177821 NOME Salario Mes...
        ("funcionario_salario_mes", r"\bFuncionario\s+\d{1,10}\s+([A-ZÁÉÍÓÚÃÕÇ][A-ZÁÉÍÓÚÃÕÇ' .\-]{5,}?)\s+Sal[aá]rio\s+Mes\b"),
        # SCI Visual: 26 JAIME TROJAN 0 0 Admitido...
        ("sci_codigo_nome_admitido", r"(?m)^\s*\d{1,8}\s+([A-ZÁÉÍÓÚÃÕÇ][A-ZÁÉÍÓÚÃÕÇ' .\-]{5,}?)\s+\d+\s+\d+\s+Admitido\b"),
        # FEMAV: CPF NOME CBO - FUNCAO
        ("cpf_nome_cbo", r"\d{3}\.\d{3}\.\d{3}-\d{2}\s+([A-ZÁÉÍÓÚÃÕÇ][A-ZÁÉÍÓÚÃÕÇ' .\-]{5,}?)\s+\d{4,6}\s*[-–]"),
        # Delphos: 098407-0 ROBERTO RODRIGUES VIGA ...
        ("registro_hifen_nome", r"(?m)^\s*\d{3,8}[-/]\d\s+([A-ZÁÉÍÓÚÃÕÇ][A-ZÁÉÍÓÚÃÕÇ' .\-]{5,}?)(?=\s{2,}|\s+(?:VIGA|VIGIA|OPERADOR|AUXILIAR|AJUDANTE|MONTADOR|ENCARREGADO|SOLDADOR|TECNICO|TÉCNICO|MOTORISTA|PEDREIRO)\b)"),
        # Delphos OCR: código + NOME + CARGO + CPF. A limpeza corta o cargo.
        ("registro_nome_cargo_cpf", r"(?m)^\s*\d{3,8}[-/]\d\s+([A-ZÁÉÍÓÚÃÕÇ][A-ZÁÉÍÓÚÃÕÇ' .\-]{5,}?)\s+\d{3}\.\d{3}\.\d{3}-\d{2}"),
        # Cuca Fresca / resumo por funcionário: 00001 NOME 1.200,00 596,00 ...
        ("codigo_nome_valores", r"(?m)^\s*\d{3,8}\s+([A-ZÁÉÍÓÚÃÕÇ][A-ZÁÉÍÓÚÃÕÇ' .\-]{5,}?)\s+\d{1,3}(?:\.\d{3})*,\d{2}\b"),
        # Folha pagamento analítica: 001013 NOME 1.621,00 Função...
        ("codigo_nome_salario_funcao", r"(?m)^\s*\d{3,8}\s+([A-ZÁÉÍÓÚÃÕÇ][A-ZÁÉÍÓÚÃÕÇ' .\-]{5,}?)\s+\d{1,3}(?:\.\d{3})*,\d{2}\s+Fun[cç][aã]o"),
    ]

    for origem, padrao in padroes:
        encontrados = 0
        for m in re.finditer(padrao, t, flags=re.I):
            adicionar_candidato(candidatos, m.group(1))
            encontrados += 1
        if encontrados:
            evidencias["padroes_usados"].append({"origem": origem, "quantidade_bruta": encontrados})

    # Fallback linha a linha para modelos "Cód: Nome: Função" e variações.
    # Exemplo: 5 ALMIR ARAUJO LUCAS ENCARREGADO
    # Exemplo: 73 ADEMIR DA SILVA TECNICO INSTALADOR
    linhas = linhas_validas(t)
    iniciou_bloco_cd_nome = False
    qtd_fallback = 0

    for idx, linha in enumerate(linhas):
        ln = norm(linha)
        if "COD: NOME" in ln or "COD. NOME" in ln or "COD NOME" in ln or "COD. NOME DO FUNCIONARIO" in ln:
            iniciou_bloco_cd_nome = True
            continue

        # Desliga em blocos de resumo/eventos para evitar capturar rubricas.
        if any(x in ln for x in ["RESUMO GERAL", "RESUMO POR RUBRICAS", "PROVENTOS DESCONTOS", "TOTAL DA FILIAL", "TOTAIS DA DEPTO"]):
            iniciou_bloco_cd_nome = False

        m = re.match(r"^\s*(\d{1,8})\s+(.+)$", linha)
        if not m:
            continue

        codigo = m.group(1)
        resto = compactar_linha(m.group(2))
        resto_norm = norm(resto)

        # Pula códigos de eventos/rubricas quando claramente não são colaboradores.
        if re.match(r"^(SALARIO|HORAS|INSS|I\.?N\.?S\.?S|FGTS|IRRF|DSR|D\.?S\.?R|ADICIONAL|ADIANTAMENTO|VALE|CESTA|FALTAS|TOTAL|PAGTO|PAGAMENTO|DESC|DESCONTO|CONTRIBUICAO|CONTRIBUIÇÃO|REFLEXO|PREMIO|PRÊMIO|ARREDONDAMENTO)\b", resto_norm):
            continue
        if any(x in resto_norm for x in ["TOTAL DE", "BASE ", "LIQUIDO", "PROVENTOS", "DESCONTOS"]):
            continue

        # Heurística: se estamos em bloco Cód/Nome/Função ou a linha contém indício de funcionário.
        contexto = "\n".join(linhas[max(0, idx - 3): idx + 3])
        contexto_n = norm(contexto)
        linha_tem_indicio = any(x in contexto_n for x in ["ADMISSAO", "ADMITIDO", "SITUACAO", "SALARIO BASE", "CPF", "FUNCAO", "CARGO"])
        if not iniciou_bloco_cd_nome and not linha_tem_indicio:
            continue

        # Corta antes de marcadores/status/valores/cpf.
        resto = re.split(r"\b(?:Admiss[aã]o|Admitido|Situa[cç][aã]o|CPF|Sal[aá]rio\s+base|Pr[oó]-?Labore)\b", resto, maxsplit=1, flags=re.I)[0]
        resto = re.split(r"\s+\d{1,3}(?:\.\d{3})*,\d{2}\b", resto, maxsplit=1)[0]
        nome = cortar_funcao_do_final(resto)

        antes = len(candidatos)
        adicionar_candidato(candidatos, nome)
        if len(candidatos) > antes:
            qtd_fallback += 1

    # Fallback para textos extraídos com ordem visual quebrada, comum em EXTRATO MENSAL:
    # linha "171 MARIANA PRAMPOLIM ALVES" aparece antes do label "Empr.:".
    qtd_split_empr = 0
    for idx, linha in enumerate(linhas):
        m = re.match(r"^\s*(\d{1,8})\s+([A-ZÁÉÍÓÚÃÕÇ][A-ZÁÉÍÓÚÃÕÇ' .\-]{5,})\s*$", linha, flags=re.I)
        if not m:
            continue
        contexto_prox = "\n".join(linhas[idx + 1: idx + 8])
        contexto_ant = "\n".join(linhas[max(0, idx - 5): idx])
        contexto_n = norm(contexto_ant + "\n" + contexto_prox)
        if any(x in contexto_n for x in ["EMPR.", "CPF:", "SITUACAO:", "SITUAÇÃO:", "VINCULO:", "VÍNCULO:", "ADM:"]):
            antes = len(candidatos)
            adicionar_candidato(candidatos, m.group(2))
            if len(candidatos) > antes:
                qtd_split_empr += 1

    if qtd_split_empr:
        evidencias["padroes_usados"].append({"origem": "fallback_codigo_nome_label_empr_quebrado", "quantidade_bruta": qtd_split_empr})

    # Fallback para modelo onde labels aparecem separados por linhas:
    # Cód: / Nome: / Função: / Salário: / ... / FUNÇÃO / NOME / CÓDIGO / Admissão.
    qtd_split_cod_nome_funcao = 0
    for idx, linha in enumerate(linhas):
        if not nome_valido(linha):
            continue
        contexto_ant = "\n".join(linhas[max(0, idx - 10): idx])
        contexto_prox = "\n".join(linhas[idx + 1: idx + 6])
        contexto_n = norm(contexto_ant + "\n" + contexto_prox)
        prox_tem_codigo = any(re.match(r"^\s*\d{1,8}\s*$", l) for l in linhas[idx + 1: idx + 4])
        tem_labels = "COD:" in contexto_n and "NOME:" in contexto_n and ("FUNCAO:" in contexto_n or "FUNÇÃO:" in contexto_n)
        tem_admissao = "ADMISSAO" in contexto_n or "ADMISSÃO" in contexto_n
        if tem_labels and (prox_tem_codigo or tem_admissao):
            antes = len(candidatos)
            adicionar_candidato(candidatos, linha)
            if len(candidatos) > antes:
                qtd_split_cod_nome_funcao += 1

    if qtd_split_cod_nome_funcao:
        evidencias["padroes_usados"].append({"origem": "fallback_labels_cod_nome_funcao_quebrados", "quantidade_bruta": qtd_split_cod_nome_funcao})

    if qtd_fallback:
        evidencias["padroes_usados"].append({"origem": "fallback_linha_codigo_nome", "quantidade_bruta": qtd_fallback})

    nomes = dedup_preservando_ordem(candidatos)
    evidencias["total_nomes_extraidos"] = len(nomes)
    return nomes, evidencias


# ============================================================
# Função principal
# ============================================================

def extrair_folha_pagamento_de_texto(texto: str, origem: str = "") -> ResultadoFolha:
    avisos: List[str] = []
    if not texto or len(norm(texto)) < 50:
        avisos.append("Texto OCR/extraído está muito curto; pode ser necessário OCR com imagem em melhor qualidade.")

    modelo, conf, ev_modelo = detectar_modelo(texto)
    razao, ev_razao = extrair_razao_social(texto, modelo)
    competencia, ev_comp = extrair_competencia(texto)
    nomes, ev_nomes = extrair_nomes(texto, modelo)

    if not razao:
        avisos.append("Razão social não encontrada com confiança suficiente.")
    if not competencia:
        avisos.append("Competência não encontrada com confiança suficiente.")
    if not nomes:
        avisos.append("Nenhum nome de colaborador encontrado com confiança suficiente.")

    evidencias = {
        "origem": origem,
        "modelo": ev_modelo,
        "razao_social": ev_razao,
        "competencia": ev_comp,
        "nomes": ev_nomes,
    }

    return ResultadoFolha(
        modelo=modelo,
        confianca_modelo=conf,
        razao_social=razao,
        competencia=competencia,
        nomes=nomes,
        evidencias=evidencias,
        avisos=avisos,
    )


def extrair_folha_pagamento(
    caminho_pdf: str | Path,
    max_paginas: Optional[int] = None,
    usar_ocr_se_necessario: bool = True,
) -> Dict[str, object]:
    texto, avisos_pdf = extrair_texto_pdf(
        caminho_pdf,
        max_paginas=max_paginas,
        usar_ocr_se_necessario=usar_ocr_se_necessario,
    )
    resultado = extrair_folha_pagamento_de_texto(texto, origem=str(caminho_pdf))
    resultado.avisos = avisos_pdf + resultado.avisos
    return asdict(resultado)


# ============================================================
# Execução em lote/CLI para testes
# ============================================================

def processar_caminho(caminho: Path, max_paginas: Optional[int], sem_ocr: bool) -> List[Dict[str, object]]:
    arquivos: List[Path]
    if caminho.is_dir():
        arquivos = sorted([p for p in caminho.rglob("*.pdf")])
    else:
        arquivos = [caminho]

    resultados = []
    for arq in arquivos:
        try:
            res = extrair_folha_pagamento(
                arq,
                max_paginas=max_paginas,
                usar_ocr_se_necessario=not sem_ocr,
            )
            resultados.append(res)
        except Exception as exc:
            resultados.append({
                "origem": str(arq),
                "erro": f"{type(exc).__name__}: {exc}",
            })
    return resultados


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Extrai razão social, competência e nomes de folhas de pagamento.")
    parser.add_argument("caminho", help="Arquivo PDF ou pasta com PDFs")
    parser.add_argument("--saida", default="", help="Arquivo JSON de saída")
    parser.add_argument("--max-paginas", type=int, default=None, help="Limitar quantidade de páginas por PDF para teste")
    parser.add_argument("--sem-ocr", action="store_true", help="Não usar OCR fallback")
    args = parser.parse_args(argv)

    resultados = processar_caminho(Path(args.caminho), args.max_paginas, args.sem_ocr)
    saida_json = json.dumps(resultados if len(resultados) != 1 else resultados[0], ensure_ascii=False, indent=2)

    if args.saida:
        Path(args.saida).write_text(saida_json, encoding="utf-8")
        print(f"Resultado salvo em: {args.saida}")
    else:
        print(saida_json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
