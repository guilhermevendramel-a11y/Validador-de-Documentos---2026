from services.cartao_ponto_service import processar_cartao_ponto
p=r"c:\\Users\\Notebook\\Downloads\\CARTAO PONTO.pdf"
r=processar_cartao_ponto(p, competencia_esperada=None)
print('status', r.get('status'))
print('qtd', len(r.get('colaboradores') or []))
for p in r.get('resultados_paginas') or []:
    print(p.get('pagina'), p.get('layout'), p.get('tipo_pagina'), p.get('nome'), p.get('nome_origem'), p.get('nome_confianca'), p.get('assinatura'), p.get('assinatura_tipo'), p.get('qtd_horarios'))
print('avisos:')
for a in r.get('avisos_globais') or []:
    print('-',a)
