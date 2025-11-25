#!/bin/bash
# Script de deploy para VPS
# Uso: ./deploy.sh

set -e

echo "=== DEPLOY CONCILIADOR API ==="

# Atualizar código
echo "[1/4] Atualizando código do repositório..."
git pull origin main

# Build da imagem
echo "[2/4] Construindo imagem Docker..."
docker compose build --no-cache

# Parar container antigo (se existir)
echo "[3/4] Reiniciando container..."
docker compose down
docker compose up -d

# Limpar imagens antigas
echo "[4/4] Limpando imagens não utilizadas..."
docker image prune -f

echo ""
echo "=== DEPLOY CONCLUÍDO ==="
echo "API disponível em: http://$(hostname -I | awk '{print $1}'):1909"
echo "Documentação: http://$(hostname -I | awk '{print $1}'):1909/docs"
echo ""
echo "Logs: docker compose logs -f"
