from services.cartao_ponto_service import processar_cartao_ponto
p=r"c:\\Users\\Notebook\\Desktop\\CARTAO PONTO.pdf"
r=processar_cartao_ponto(p,None)
print('qtd',len(r.get('colaboradores') or []))
for c in r.get('colaboradores') or []:
 print(c.get('nome'),c.get('paginas'),c.get('assinatura'),c.get('competencia'))
