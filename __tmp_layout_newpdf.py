from services.cartao_ponto_layout_parser import processar_paginas_cartao_ponto_layout
from utils.ocr import extrair_documento_inteligente
p=r"c:\\Users\\Notebook\\Downloads\\CARTAO PONTO.pdf"
ocr=extrair_documento_inteligente(p)
paginas=[{'pagina':x.get('pagina'),'texto':x.get('texto','')} for x in (ocr.get('paginas') or [])]
res=processar_paginas_cartao_ponto_layout(p,deteccoes_yolo=[],paginas_texto=paginas,render_imagem=False,paginas_assinatura_alvo={2,4,6,8,10})
for it in res:
    print('\nP',it.get('pagina'),'layout',it.get('layout'),'nome_colab',it.get('nome_colaborador'),'ass',it.get('assinatura'),'qtdh',it.get('qtd_horarios'))
    tx=(it.get('texto_pagina') or '')
    for ln in tx.splitlines()[:35]:
        if ln.strip():
            print(ln)
