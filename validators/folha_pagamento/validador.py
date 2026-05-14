from .regras import extrair_empresa, extrair_competencia_folha, extrair_colaboradores

def validar_folha_pagamento(texto, competencia_esperada):
    # 1. Extração de dados via regras.py
    empresa = extrair_empresa(texto)
    competencia_doc = extrair_competencia_folha(texto)
    lista_nomes = extrair_colaboradores(texto)

    # 2. Critérios de Validação
    empresa_ok = empresa is not None
    comp_ok = (competencia_doc == competencia_esperada)
    colaboradores_ok = len(lista_nomes) > 0

    # 3. Definição do Status Final
    status = "Aprovado" if (empresa_ok and comp_ok and colaboradores_ok) else "Reprovado"
    
    # Mensagem personalizada
    if status == "Aprovado":
        mensagem = "Folha de Pagamento validada com sucesso."
    else:
        erros = []
        if not empresa_ok: erros.append("Empresa não identificada")
        if not comp_ok: erros.append(f"Competência divergente (Doc: {competencia_doc or 'N/A'})")
        if not colaboradores_ok: erros.append("Nenhum colaborador encontrado")
        mensagem = "Pendências encontradas: " + ", ".join(erros)

    # 4. Estrutura de Retorno (Tabela de Verificação)
    linhas = [
        {"item": "Identificação da Empresa", "ok": empresa_ok},
        {"item": "Conferência de Competência", "ok": comp_ok},
        {"item": "Presença de Colaboradores", "ok": colaboradores_ok}
    ]

    return {
        "status": status,
        "mensagem": mensagem,
        "empresa": empresa or "Não identificada",
        "competencia": competencia_esperada,
        "linhas": linhas,
        "colaboradores": lista_nomes # Lista de dicts: [{"nome": "...", "status": "✔ OK"}]
    }