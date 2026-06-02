#!/usr/bin/env bash
# =============================================================================
# Deploy do Validador (validador.portalmse.com.br) + YOLO (validador2.portalmse.com.br)
# Executado pelo GitHub Actions via SSH, depois que o codigo e enviado por rsync.
# Rebuilda a imagem e reinicia os dois containers. So mantem o ar se o build der certo.
# =============================================================================
set -euo pipefail

APP_DIR="/var/www/validador_docs_github"
COMPOSE=(-f docker-compose.yml -f docker-compose.yolo.yml)

cd "$APP_DIR"
log() { echo -e "\n==> $*"; }

log "Rebuild + restart dos servicos (validador + yolo)"
docker compose "${COMPOSE[@]}" up -d --build --remove-orphans

log "Removendo imagens orfas"
docker image prune -f

log "Status dos containers"
docker compose "${COMPOSE[@]}" ps

log "Healthcheck local"
for url in http://127.0.0.1:8000/ http://127.0.0.1:8010/; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "$url" || true)"
  echo "    $url -> HTTP $code"
done

log "Deploy concluido."
