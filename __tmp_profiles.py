from services.cartao_ponto_service import processar_paginas_cartao_ponto_layout_rapido
from utils.ocr import extrair_documento_inteligente
from collections import Counter
p=r"c:\\Users\\Notebook\\Desktop\\Cartão Ponto - TESTE\\CARTÃO PONTO_merged.pdf"
ocr=extrair_documento_inteligente(p)
pls=processar_paginas_cartao_ponto_layout_rapido(p, ocr)
print('pages',len(pls))
print('layouts',Counter([x.get('layout') or 'na' for x in pls]))
print('assinadas',sum(1 for x in pls if x.get('assinatura')))
print('com_nome',sum(1 for x in pls if (x.get('nome_colaborador') or '').strip()))
for x in pls[:20]:
    print(x.get('pagina'), x.get('layout'), (x.get('nome_colaborador') or '')[:40], x.get('assinatura'), x.get('qtd_horarios'))
