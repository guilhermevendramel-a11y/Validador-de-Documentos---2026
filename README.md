# Validador Gestao Documental - Next.js

Este projeto agora usa Next.js como servidor web local. A logica pesada de OCR e validacao continua em Python e e chamada pelas rotas do Next.js.

## Rodar localmente

1. Instale as dependencias Python:

```powershell
pip install -r requirements.txt
```

2. Instale as dependencias do Next.js:

```powershell
npm install
```

3. Inicie o servidor:

```powershell
npm run dev
```

Abra `http://localhost:8000`.

## Observacoes

- As rotas antigas foram mantidas: `/validar_fgts`, `/validar_inss`, `/validar_holerite`, etc.
- Se o comando Python da maquina nao for `python`, defina `PYTHON_BIN` antes de subir o Next:

```powershell
$env:PYTHON_BIN="py"
npm run dev
```

- O arquivo `app.py` antigo foi preservado como referencia, mas o servidor principal passa a ser o Next.js.
- Neste ambiente, Node.js e Git foram configurados em `tools/` e adicionados ao PATH do usuario.
# Validador-de-Documentos---2026
