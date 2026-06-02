import fitz
from services.cartao_ponto_layout_parser import renderizar_pagina_pdf, recortar_area_util_documento, gerar_recortes_cartao_ponto, ocr_cartao_por_regioes
p=r"c:\\Users\\Notebook\\Downloads\\CARTAO PONTO.pdf"
for pg in [1,3,5]:
    img=renderizar_pagina_pdf(p, pg-1, dpi=300)
    rec=recortar_area_util_documento(img)
    regs=gerar_recortes_cartao_ponto(rec['imagem'])
    o=ocr_cartao_por_regioes(regs,'desconhecido')
    print('\n=== PAG',pg,'===')
    print('nome_info',o.get('nome_info'))
    print('texto_topo:\n', (o.get('texto_topo') or '')[:1000])
    print('texto_total head:\n', (o.get('texto_total') or '')[:1200])
