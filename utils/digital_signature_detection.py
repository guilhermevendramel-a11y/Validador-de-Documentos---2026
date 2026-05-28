import re
import unicodedata


def _norm(texto):
    txt = unicodedata.normalize("NFKD", str(texto or ""))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return txt.upper()


def detectar_autenticacao_digital(texto):
    t = _norm(texto)

    zapsign_tokens = [
        "ZAPSIGN",
        "RELATORIO DE ASSINATURAS",
        "ASSINADO DIGITALMENTE",
        "DOCUMENTO ASSINADO ELETRONICAMENTE",
        "TOKEN:",
    ]
    gov_tokens = [
        "GOV.BR",
        "ASSINADOR GOV",
        "ASSINADO VIA GOV",
        "ASSINATURA ELETRONICA GOV",
        "PORTAL GOV",
    ]

    is_zapsign = any(k in t for k in zapsign_tokens)
    is_gov = any(k in t for k in gov_tokens)
    has_digital = is_zapsign or is_gov or "ASSINATURA DIGITAL" in t or "CERTIFICADO DIGITAL" in t

    foto_colaborador = bool(
        re.search(r"\b(FOTO|IMAGEM|SELFIE)\b", t)
        and re.search(r"\b(COLABORADOR|ASSINANTE|SIGNATARIO)\b", t)
    )

    if is_gov:
        tipo = "gov"
        detalhe = "Assinatura digital identificada e assinada pelo Gov."
    elif is_zapsign:
        tipo = "zapsign"
        detalhe = (
            "Assinatura digital via ZapSign com foto do colaborador."
            if foto_colaborador
            else "Assinatura digital via ZapSign identificada."
        )
    elif has_digital:
        tipo = "digital"
        detalhe = "Assinatura digital identificada no documento."
    else:
        tipo = "nenhuma"
        detalhe = "Nao foi identificada autenticacao digital."

    return {
        "assinatura_digital": bool(has_digital),
        "provedor": tipo,
        "foto_colaborador": bool(foto_colaborador),
        "detalhe": detalhe,
        "pagina_autenticacao": bool("RELATORIO DE ASSINATURAS" in t or "ASSINADO DIGITALMENTE" in t or "GOV.BR" in t),
    }
