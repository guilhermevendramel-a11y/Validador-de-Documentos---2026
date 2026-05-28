import fitz, re
p=r"c:\\Users\\Notebook\\Desktop\\Cartão Ponto - TESTE\\CARTÃO PONTO_merged.pdf"
d=fitz.open(p)
print('pages', len(d))
for i,pg in enumerate(d, start=1):
    t=pg.get_text('text') or ''
    tn=' '.join(t.split())
    print(f'P{i}: text_len={len(tn)}')
