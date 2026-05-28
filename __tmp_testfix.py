from services.cartao_ponto_service import processar_cartao_ponto
p=r"c:\\Users\\Notebook\\Desktop\\Cartão Ponto - TESTE\\CARTAO PONTO.pdf"
r=processar_cartao_ponto(p,None)
print('status',r.get('status'),'qtd',len(r.get('colaboradores') or []))
for c in r.get('colaboradores') or []:
    print(c.get('nome'), c.get('paginas'), c.get('assinatura'), c.get('assinatura_tipo'))
print('avisos',len(r.get('avisos_globais') or []))
