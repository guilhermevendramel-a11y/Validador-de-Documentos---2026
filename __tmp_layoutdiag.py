from services.cartao_ponto_layout_parser import processar_paginas_cartao_ponto_layout
p=r"c:\\Users\\Notebook\\Downloads\\Teste Morais 26-05.pdf"
res=processar_paginas_cartao_ponto_layout(p, paginas_texto=[], render_imagem=False, paginas_assinatura_alvo={2,4,5,6,7,8,9,10})
for it in res:
    if it.get('pagina') in [5,7,9]:
        print('\n=== P',it.get('pagina'),'===')
        print('layout',it.get('layout'))
        print('nome_colaborador',it.get('nome_colaborador'))
        print('nome_info',it.get('nome_info'))
        print('competencia',it.get('competencia'))
        print('qtd_horarios',it.get('qtd_horarios'))
        t=(it.get('texto_pagina') or '')
        for ln in t.splitlines()[:120]:
            if ln.strip():
                print(ln)
