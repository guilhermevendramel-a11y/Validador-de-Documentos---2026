import fitz
p=r"c:\\Users\\Notebook\\Downloads\\CARTAO PONTO.pdf"
d=fitz.open(p)
print('pages',len(d))
for i,pg in enumerate(d, start=1):
    t=pg.get_text('text') or ''
    print('\n=== P',i,'len',len(' '.join(t.split())),'===')
    for ln in t.splitlines()[:60]:
        if ln.strip():
            print(ln)
