import fitz
from collections import Counter
from services.cartao_ponto_layout_parser import classificar_layout_cartao_ponto
p=r"c:\\Users\\Notebook\\Desktop\\Cartão Ponto - TESTE\\CARTÃO PONTO_merged.pdf"
d=fitz.open(p)
layouts=[]
for i,pg in enumerate(d, start=1):
    t=pg.get_text('text') or ''
    l=classificar_layout_cartao_ponto(t)
    layouts.append((i,l,len(' '.join(t.split()))))
print(Counter([x[1] for x in layouts]))
print('samples:')
for i,l,n in layouts[:50]:
    print(i,l,n)
