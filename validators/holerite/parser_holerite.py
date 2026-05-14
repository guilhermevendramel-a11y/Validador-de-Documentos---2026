import re
from holerite.engine_parser import engine_extracao

def extrair_funcionarios(texto):
    funcionarios = []
    if not texto:
        return funcionarios

    # Divide o documento em holerites individuais para evitar confusão de nomes
    blocos = re.split(r"(?=RECIBO DE PAGAMENTO|DEMONSTRATIVO|MENSAL)", texto.upper())

    for bloco in blocos:
        # Filtra blocos que não contenham a seção de valores líquidos
        if "LÍQUIDO" not in bloco and "VENCIMENTOS" not in bloco:
            continue

        try:
            dados = engine_extracao(bloco)
            if dados.get("nome") and dados.get("valor"):
                funcionarios.append({
                    "nome": dados["nome"],
                    "empresa": dados.get("empresa"),
                    "valor_liquido": dados["valor"],
                    "data_referencia": dados.get("data"),
                    "confianca": dados["confianca"]
                })
        except Exception as e:
            print(f"Erro no holerite: {e}")

    return funcionarios