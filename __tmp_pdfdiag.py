import fitz,re
p=r"c:\\Users\\Notebook\\Downloads\\Teste Morais 26-05.pdf"
d=fitz.open(p)
print('pages', len(d))
for i,pg in enumerate(d, start=1):
    t=pg.get_text('text')
    tn=' '.join(t.split())
    anchors=re.findall(r'(?:FUNCION\\.?|NOME(?: DO COLABORADOR)?|EMPREGADO)\\s*[:\\-]?\\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{6,80})', tn, flags=re.I)
    print('P',i,'len',len(tn),'anchor',anchors[:1])
