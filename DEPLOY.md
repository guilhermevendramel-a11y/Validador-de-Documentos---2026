# Deploy / Pipeline

CI/CD: **push na `main`** -> GitHub Actions envia o codigo por **rsync** para o
servidor e roda o **`deploy.sh`**, que rebuilda a imagem e reinicia os dois
containers. O **nginx** (com HTTPS via Certbot) ja faz o proxy dos subdominios.

```
push main ─> GitHub Actions ─ rsync ─> /var/www/validador_docs_github (servidor)
                              └ ssh ─> ./deploy.sh (docker compose build + up)

nginx 443 ── validador.portalmse.com.br  ─> 127.0.0.1:8000  (Next.js)  -> validador-mse
        └─ validador2.portalmse.com.br    ─> 127.0.0.1:8010  (YOLO/Flask) -> validador-yolo-mse
```

## Servico / arquivos

| Subdominio                    | Porta | Container            | Compose                    |
|-------------------------------|-------|----------------------|----------------------------|
| validador.portalmse.com.br    | 8000  | `validador-mse`      | `docker-compose.yml`       |
| validador2.portalmse.com.br   | 8010  | `validador-yolo-mse` | `docker-compose.yolo.yml`  |

- `Dockerfile` — imagem base do validador (Python + Node/Next + OCR), enxuta (`requirements-server.txt`).
- `Dockerfile.yolo` — imagem do YOLO: estende a base e adiciona o stack de ML (`requirements-yolo.txt`: torch CPU + ultralytics) para o `/api/train` do validador2.
- `.dockerignore` — mantem o contexto de build enxuto.
- `deploy.sh` — sobe os dois servicos: `docker compose -f docker-compose.yml -f docker-compose.yolo.yml up -d --build`.
- `.github/workflows/deploy.yml` — o pipeline (rsync + ssh).
- `deploy/nginx/*.conf` — copia de referencia dos virtual hosts ja ativos.
- `.env.example` — variaveis do `.env` (que vive no servidor; o rsync nao o sobrescreve).

## Servidor (ja provisionado)

- Host: `35.168.67.97` (AWS, Ubuntu 26.04), usuario `ubuntu` (no grupo `docker`, sudo sem senha).
- Docker + Compose, nginx 1.28, Certbot (cert SAN cobrindo os dois subdominios).
- Projeto em `/var/www/validador_docs_github` (dono `ubuntu`), com `.env` real e `models/`/`datasets/` persistidos.
- Chave de deploy `~/.ssh/gha_deploy` ja autorizada para o GitHub Actions.

## Secrets no GitHub (Settings -> Secrets and variables -> Actions)

| Secret        | Valor                                                        |
|---------------|--------------------------------------------------------------|
| `SSH_HOST`    | `35.168.67.97`                                               |
| `SSH_USER`    | `ubuntu`                                                     |
| `SSH_KEY`     | conteudo da chave PRIVADA `~/.ssh/gha_deploy` do servidor    |
| `SSH_PORT`    | (opcional) `22`                                              |
| `DEPLOY_PATH` | (opcional) `/var/www/validador_docs_github`                  |

> Para obter a chave privada: `ssh ubuntu@35.168.67.97 'cat ~/.ssh/gha_deploy'`
> e cole o conteudo inteiro (com as linhas BEGIN/END) no secret `SSH_KEY`.

## Disparar o deploy

Push na `main` (ou **Actions -> Deploy (validador + yolo) -> Run workflow**).

## Operacao manual no servidor

```bash
ssh ubuntu@35.168.67.97
cd /var/www/validador_docs_github
./deploy.sh                  # rebuild + restart dos 2 servicos
docker compose -f docker-compose.yml -f docker-compose.yolo.yml ps
docker compose -f docker-compose.yml -f docker-compose.yolo.yml logs -f --tail=100
```

## Observacoes

- O `.env`, `models/` e `datasets/` ficam **so no servidor** e sao preservados
  pelo rsync (estao na lista de `--exclude`). Ajuste de variavel/modelo e feito
  diretamente no servidor.
- O build roda no servidor a cada deploy; com cache do Docker, mudancas que nao
  alterem `requirements.txt`/`package.json` reconstroem rapido.
