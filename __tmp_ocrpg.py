from utils.ocr import extrair_documento_inteligente
p=r"c:\\Users\\Notebook\\Downloads\\Teste Morais 26-05.pdf"
r=extrair_documento_inteligente(p)
for pg in r.get('paginas',[]):
    n=pg.get('pagina')
    if n in [5,7,9]:
        t=pg.get('texto','')
        print('\n=== PAG',n,'===')
        for ln in t.splitlines()[:80]:
            if ln.strip():
                print(ln)
