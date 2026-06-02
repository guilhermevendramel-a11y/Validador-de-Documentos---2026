from services.cartao_ponto_service import processar_cartao_ponto
p=r"c:\\Users\\Notebook\\Desktop\\Cartão Ponto - TESTE\\CARTÃO PONTO_merged.pdf"
r=processar_cartao_ponto(p, competencia_esperada=None)
print('status', r.get('status'))
print('qtd', len(r.get('colaboradores') or []))
for c in (r.get('colaboradores') or [])[:20]:
    print(c.get('nome'), c.get('paginas'), c.get('assinatura'), c.get('assinatura_tipo'), c.get('marcacoes_encontradas'))
print('avisos', len(r.get('avisos_globais') or []))
