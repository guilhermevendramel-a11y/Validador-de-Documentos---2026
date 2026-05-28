from services.cartao_ponto_service import processar_cartao_ponto
p=r"c:\\Users\\Notebook\\Desktop\\CARTAO PONTO.pdf"
r=processar_cartao_ponto(p,None)
print('status',r.get('status'),'qtd',len(r.get('colaboradores') or []))
for p in r.get('resultados_paginas') or []:
    print(p.get('pagina'),p.get('tipo_pagina'),p.get('nome'),p.get('assinatura'),p.get('qtd_horarios'))
print('avisos',len(r.get('avisos_globais') or []))
