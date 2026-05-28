from services.cartao_ponto_service import processar_cartao_ponto
p=r"c:\\Users\\Notebook\\Downloads\\Teste Morais 26-05.pdf"
r=processar_cartao_ponto(p, competencia_esperada=None)
print('status', r.get('status'))
cols=r.get('colaboradores') or []
print('qtd', len(cols))
for c in cols:
    print('COL', c.get('nome'), 'paginas', c.get('paginas'), 'ass', c.get('assinatura'), c.get('assinatura_tipo'), 'marc', c.get('marcacoes_encontradas'), 'qtdh', c.get('qtd_horarios'))
print('--- paginas ---')
for p in r.get('resultados_paginas') or []:
    print(p.get('pagina'), p.get('layout'), p.get('tipo_pagina'), p.get('nome'), p.get('assinatura'), p.get('assinatura_tipo'), p.get('qtd_horarios'))
print('--- avisos ---')
for a in r.get('avisos_globais') or []:
    print(a)
