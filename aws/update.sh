#!/bin/bash
# ============================================================
# update.sh — Clarity Retail Hub
# 1-Click manual update script for AWS EC2 instance
# ============================================================

set -e
cd "$(dirname "$0")/.."

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
