#!/bin/bash
# Script de setup inicial para VPS Ubuntu/Debian
# Execute como root: sudo bash setup-vps.sh

set -e

echo "=== SETUP VPS PARA CONCILIADOR API ==="

# Atualizar sistema
echo "[1/5] Atualizando sistema..."
apt-get update && apt-get upgrade -y

# Instalar Docker
echo "[2/5] Instalando Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
else
    echo "Docker já instalado"
fi

# Instalar Docker Compose (plugin)
echo "[3/5] Verificando Docker Compose..."
if ! docker compose version &> /dev/null; then
    apt-get install -y docker-compose-plugin
fi

# Instalar Git
echo "[4/5] Instalando Git..."
apt-get install -y git

# Configurar firewall (se ufw estiver instalado)
echo "[5/5] Configurando firewall..."
if command -v ufw &> /dev/null; then
    ufw allow 1909/tcp
    ufw allow 22/tcp
    ufw --force enable
fi

echo ""
echo "=== SETUP CONCLUÍDO ==="
echo ""
echo "Próximos passos:"
echo "1. Clone o repositório:"
echo "   git clone https://github.com/SEU_USUARIO/SEU_REPO.git"
echo ""
echo "2. Entre na pasta e execute o deploy:"
echo "   cd SEU_REPO"
echo "   chmod +x deploy.sh"
echo "   ./deploy.sh"
echo ""
