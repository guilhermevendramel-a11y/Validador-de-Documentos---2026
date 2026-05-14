import re
from holerite.engine_parser import engine_extracao

def extrair_pagamentos(texto):
    pagamentos = []
    if not texto:
        return pagamentos

    # Divide o texto por comprovantes usando âncoras de autenticação
    # Isso evita que dados de rodapé de um comprovante 'vazem' para a extração do valor
    blocos = re.split(r"(?=COMPROVANTE|AUTENTICA[ÇC][ÃA]O|TED|PIX)", texto.upper())
    
    for bloco in blocos:
        if len(bloco.strip()) < 40: continue
        
        try:
            dados = engine_extracao(bloco)
            # No comprovante bancário, favorecido e valor são obrigatórios
            if dados.get("nome") and dados.get("valor"):
                pagamentos.append({
                    "nome": dados["nome"],
                    "valor_pago": dados["valor"],
                    "data_pagamento": dados.get("data"),
                    "confianca": dados["confianca"]
                })
        except Exception as e:
            print(f"Erro no comprovante: {e}")
            
    return pagamentos