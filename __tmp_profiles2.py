from services.cartao_ponto_layout_parser import processar_paginas_cartao_ponto_layout
from utils.ocr import extrair_documento_inteligente
from collections import Counter
p=r"c:\\Users\\Notebook\\Desktop\\Cartão Ponto - TESTE\\CARTÃO PONTO_merged.pdf"
ocr=extrair_documento_inteligente(p)
paginas=[{'pagina':x.get('pagina'),'texto':x.get('texto','')} for x in (ocr.get('paginas') or [])]
res=processar_paginas_cartao_ponto_layout(p,deteccoes_yolo=[],paginas_texto=paginas,render_imagem=False,paginas_assinatura_alvo=set())
print('pages',len(res))
print('layouts',Counter([x.get('layout') or 'na' for x in res]))
print('assinadas',sum(1 for x in res if x.get('assinatura')))
print('com_nome',sum(1 for x in res if (x.get('nome_colaborador') or '').strip()))
for x in res[:30]:
    print(x.get('pagina'), x.get('layout'), (x.get('nome_colaborador') or '')[:45], x.get('assinatura'), x.get('qtd_horarios'))
