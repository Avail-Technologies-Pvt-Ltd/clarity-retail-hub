#!/bin/bash
# ============================================================
# Clarity Retail Hub - AWS EC2 Initial Setup Script (Ubuntu)
# ============================================================
# Usage on fresh Ubuntu EC2:
#   curl -fsSL https://raw.githubusercontent.com/Avail-Technologies-Pvt-Ltd/clarity-retail-hub/main/aws/setup_ec2.sh | sudo bash
#   or run locally: sudo bash setup_ec2.sh
# ============================================================

set -e

echo "============================================================"
echo "    CLARITY RETAIL HUB - AWS EC2 SERVER INITIALIZATION"
echo "============================================================"

# Ensure running as root or with sudo
if [ "$EUID" -ne 0 ]; then
  echo "[ERROR] Please run with sudo or as root: sudo bash setup_ec2.sh"
  exit 1
fi

TARGET_USER="${SUDO_USER:-ubuntu}"
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
APP_DIR="$TARGET_HOME/clarity-retail-hub"

echo "[1/6] Updating system packages..."
apt-get update && apt-get upgrade -y
apt-get install -y curl git ufw ca-certificates gnupg lsb-release

echo "[2/6] Installing Docker Engine & Docker Compose plugin..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sh /tmp/get-docker.sh
    rm -f /tmp/get-docker.sh
fi

systemctl enable docker
systemctl start docker

# Add target user to docker group
usermod -aG docker "$TARGET_USER"
echo "[OK] Docker installed. Added $TARGET_USER to docker group."

echo "[3/6] Setting up application directory: $APP_DIR..."
mkdir -p "$APP_DIR/media" "$APP_DIR/staticfiles" "$APP_DIR/logs" "$APP_DIR/data"

# Ensure permissions
chown -R "$TARGET_USER:$TARGET_USER" "$APP_DIR"
chmod -R 775 "$APP_DIR/media" "$APP_DIR/staticfiles" "$APP_DIR/logs"

echo "[4/6] Configuring Firewall (UFW)..."
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP Web'
ufw allow 443/tcp comment 'HTTPS Web'
ufw allow 8003/tcp comment 'Clarity Hub Port Optional'
ufw --force enable

echo "[5/6] Creating default environment and docker-compose files..."
if [ ! -f "$APP_DIR/.env.prod" ]; then
    RANDOM_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))" 2>/dev/null || openssl rand -base64 40)
    RANDOM_DB_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))" 2>/dev/null || openssl rand -base64 20)

    cat << EOF > "$APP_DIR/.env.prod"
# ============================================================
# Clarity Retail Hub — Production Configuration (.env.prod)
# ============================================================

# Django Core Security
SECRET_KEY=$RANDOM_SECRET
DEBUG=False
ALLOWED_HOSTS=*
CSRF_TRUSTED_ORIGINS=http://*.localhost,http://localhost

# Port exposed on AWS Host (default 80 for direct web traffic)
HOST_PORT=80

# PostgreSQL Production Database Credentials
DB_NAME=clarity_retail_hub_prod
DB_USER=hub_prod_user
DB_PASSWORD=$RANDOM_DB_PASS
DB_HOST=db
DB_PORT=5432

# Multi-Tenancy Base Domain
TENANT_BASE_DOMAIN=localhost

# Docker Hub Configuration
DOCKER_REGISTRY=yourdockerhubusername
TAG=latest

# Performance & Workers (0 = dynamic auto-detect)
GUNICORN_WORKERS=0
CSRF_COOKIE_SECURE=False
SESSION_COOKIE_SECURE=False
EOF
    chown "$TARGET_USER:$TARGET_USER" "$APP_DIR/.env.prod"
    chmod 600 "$APP_DIR/.env.prod"
    echo "[OK] Created $APP_DIR/.env.prod with secure random credentials."
fi

echo "[6/6] Creating update.sh and rollback.sh helper scripts..."
cat << 'EOF' > "$APP_DIR/update.sh"
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "    CLARITY RETAIL HUB - PULLING LATEST & RESTARTING"
echo "============================================================"

# Ensure TAG=latest
sed -i 's/^TAG=.*/TAG=latest/' .env.prod 2>/dev/null || true

docker compose -f docker-compose.prod.yml pull web
docker compose -f docker-compose.prod.yml up -d --remove-orphans
docker image prune -f

echo "============================================================"
echo " Update complete! Current status:"
echo "============================================================"
docker compose -f docker-compose.prod.yml ps
EOF

cat << 'EOF' > "$APP_DIR/rollback.sh"
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "    CLARITY RETAIL HUB - ROLLBACK VERSION"
echo "============================================================"

TARGET_TAG="$1"
if [ -z "$TARGET_TAG" ]; then
    read -p "Enter version tag to rollback to (e.g. v1.0.0): " TARGET_TAG
fi

if [ -z "$TARGET_TAG" ]; then
    echo "[ERROR] No version specified. Rollback aborted."
    exit 1
fi

echo "[*] Setting TAG=$TARGET_TAG in .env.prod..."
sed -i "s/^TAG=.*/TAG=$TARGET_TAG/" .env.prod

echo "[*] Pulling image for tag $TARGET_TAG..."
docker compose -f docker-compose.prod.yml pull web

echo "[*] Restarting container with version $TARGET_TAG..."
docker compose -f docker-compose.prod.yml up -d --remove-orphans web

echo "============================================================"
echo " Rollback to $TARGET_TAG successful!"
echo "============================================================"
docker compose -f docker-compose.prod.yml ps
EOF

chmod +x "$APP_DIR/update.sh" "$APP_DIR/rollback.sh"
chown "$TARGET_USER:$TARGET_USER" "$APP_DIR/update.sh" "$APP_DIR/rollback.sh"

echo ""
echo "============================================================"
echo " AWS EC2 SETUP COMPLETE!"
echo " Next steps:"
echo " 1. Update DOCKER_REGISTRY in $APP_DIR/.env.prod with your Docker Hub username."
echo " 2. Add GitHub Repository Secrets: AWS_HOST, AWS_USER, AWS_SSH_PRIVATE_KEY."
echo " 3. Run push.bat from your development PC for 1-click deployments!"
echo "============================================================"
