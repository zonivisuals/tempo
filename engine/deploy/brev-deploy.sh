#!/usr/bin/env bash
# Deploy or update the Tempo engine on the Brev instance (ADR-0008).
#
# Runs where the brev CLI is logged in (on Windows: inside WSL, per the Brev install docs).
# Uses only documented CLI commands (`brev exec "<cmd>"`). The instance itself (L4, name
# $TEMPO_BREV_INSTANCE) is created once in the Brev console.
#
#   TEMPO_REPO_URL=git@github.com:<org>/tempo.git ./engine/deploy/brev-deploy.sh
#
# Idempotent: pulls the ref, keeps deploy/.env, rebuilds, prefetches weights onto the
# persistent volume, verifies the query models on the GPU, prints /v1/health.
set -euo pipefail

INSTANCE="${TEMPO_BREV_INSTANCE:-tempo-l4-instance}"
REPO_URL="${TEMPO_REPO_URL:?set TEMPO_REPO_URL to a git remote the instance can clone}"
REF="${TEMPO_REPO_REF:-main}"
SRC="${TEMPO_REMOTE_SRC:-/home/ubuntu/workspace/tempo-src}"
DEPLOY="$SRC/engine/deploy"

remote() {
  echo "==> $1"
  brev exec "$INSTANCE" "$2"
}

remote "sync $REF" "set -e
  if [ -d '$SRC/.git' ]; then
    git -C '$SRC' fetch --depth 1 origin '$REF' && git -C '$SRC' checkout -q FETCH_HEAD
  else
    git clone --depth 1 --branch '$REF' '$REPO_URL' '$SRC'
  fi"

remote "env file" "set -e
  cd '$DEPLOY'
  if [ ! -f .env ]; then cp .env.example .env; fi
  if ! grep -q '^TEMPO_ENGINE_TOKEN=.\+' .env; then
    sed -i \"s/^TEMPO_ENGINE_TOKEN=.*/TEMPO_ENGINE_TOKEN=\$(openssl rand -hex 32)/\" .env
    echo 'generated TEMPO_ENGINE_TOKEN in $DEPLOY/.env — copy it into the sidecar as TEMPO_BACKEND_TOKEN'
  fi
  chmod 600 .env"

remote "build + start" "cd '$DEPLOY' && docker compose up -d --build"
remote "prefetch + verify on device" "cd '$DEPLOY' && docker compose exec -T engine python -m tempo_engine.prefetch --verify"
remote "health" "cd '$DEPLOY' && . ./.env && curl -fsS http://127.0.0.1:\${TEMPO_ENGINE_PORT:-8900}/v1/health && echo"
