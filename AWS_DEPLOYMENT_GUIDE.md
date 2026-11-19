# 🚀 Clarity Retail Hub — AWS Deployment & CI/CD Pipeline Guide

Continuous Deployment pipeline connecting local development to AWS EC2 via **GitHub Actions** and **Docker Hub** with **1-click automatic updates**, multi-tenant schema isolation, semantic versioning, and instant rollback support (matching the standard established in `RODZ TUTORING`).

---

## 🏗️ 1-Click Architecture

```mermaid
flowchart TD
    subgraph DevWorkstation["💻 Developer PC"]
        Code["Code Changes / Feature Updates"] --> PushBat["push.bat (1-Click Push)"]
        PushBat --> VersionMgr["Auto-increments version.txt (e.g. v1.0.1)"]
        PushBat --> RunTests["Runs Django Automated Test Suite (25 Tests)"]
        RunTests --> GitPush["Pushes branch 'main' + release tag 'v1.0.1'"]
    end

    subgraph GitHubActions["🐙 GitHub Actions (.github/workflows/build-and-push.yml)"]
        GitPush --> TestJob["1. Run Automated Test Suite in CI"]
        TestJob --> BuildJob["2. Build Production Docker Image (Buildx Cache)"]
        BuildJob --> DockerHubPush["Pushes to Docker Hub:
        • :latest (Active production)
        • :v1.0.1 (Immutable rollback tag)"]
        DockerHubPush --> DeployJob["3. Deploy to AWS via SSH (appleboy/ssh-action)"]
    end

    subgraph AWSEC2["☁️ AWS EC2 Production Server"]
        DeployJob --> SCP["Transfers docker-compose.prod.yml via SCP"]
        SCP --> SSH["SSH Command Execution"]
        SSH --> Pull["docker compose pull web"]
        SSH --> Restart["docker compose up -d web"]
        Restart --> Entrypoint["entrypoint.sh auto-runs:
        • nc wait for PostgreSQL readiness
        • python manage.py migrate_schemas
        • python manage.py create_public_tenant
        • python manage.py collectstatic"]
        Restart --> Prune["docker image prune -f"]
        Entrypoint --> LiveApp["Clarity Retail Hub Live on Port 80 / Domain!"]
    end
```

---

## 🔑 GitHub Repository Secrets Configuration

In your GitHub repository (`clarity-retail-hub`), navigate to **Settings > Secrets and variables > Actions** and click **New repository secret**:

| Secret Name | Value / Description | Example |
| :--- | :--- | :--- |
| `DOCKERHUB_USERNAME` | Your Docker Hub account username. | `tinashemp` |
| `DOCKERHUB_TOKEN` | Docker Hub Personal Access Token (PAT with Read & Write access). | `dckr_pat_...` |
| `AWS_HOST` | Public IPv4 Address or Elastic IP of your AWS EC2 instance. | `13.244.120.45` |
| `AWS_USER` | SSH Username on the AWS instance (default for Ubuntu is `ubuntu`). | `ubuntu` |
| `AWS_SSH_PRIVATE_KEY` | Entire content of your AWS `.pem` private key file (including `-----BEGIN RSA PRIVATE KEY-----`). | `-----BEGIN RSA...` |

*(Optional)*: If your SSH port is not 22, add `AWS_PORT`.

---

## ☁️ 1-Command AWS Server Setup

### Step 1: Launch an AWS EC2 Instance
1. Go to AWS Management Console $\rightarrow$ **EC2** $\rightarrow$ **Launch Instance**.
2. **Name**: `clarity-retail-hub-production`
3. **OS**: **Ubuntu Server 22.04 LTS** or **24.04 LTS** (64-bit x86).
4. **Instance Type**: `t3.small` (recommended for PostgreSQL + Gunicorn + Multi-Tenancy) or `t3.micro`.
5. **Key Pair**: Select or create a `.pem` key pair (download and store it securely).
6. **Network & Security Groups**: Allow:
   - ☑ **SSH (Port 22)** — Anywhere or your IP
   - ☑ **HTTP (Port 80)** — Anywhere (0.0.0.0/0)
   - ☑ **HTTPS (Port 443)** — Anywhere (0.0.0.0/0)
   - ☑ **Custom TCP (Port 8003)** — Optional alternative access port
7. Click **Launch Instance**.

### Step 2: Initialize Server (Run Once)
Connect to your EC2 instance via SSH:
```bash
ssh -i /path/to/your-key.pem ubuntu@YOUR_AWS_PUBLIC_IP
```

Run the automated setup script:
```bash
curl -fsSL https://raw.githubusercontent.com/Avail-Technologies-Pvt-Ltd/clarity-retail-hub/main/aws/setup_ec2.sh | sudo bash
```

This will automatically:
- Install Docker & Docker Compose plugin
- Configure UFW firewall (Ports 22, 80, 443, 8003)
- Create `/home/ubuntu/clarity-retail-hub` with `media`, `staticfiles`, and `logs`
- Generate `/home/ubuntu/clarity-retail-hub/.env.prod` with strong cryptographic secrets
- Set up `update.sh` and `rollback.sh`

### Step 3: Configure `.env.prod` on AWS
Edit `/home/ubuntu/clarity-retail-hub/.env.prod`:
```bash
nano /home/ubuntu/clarity-retail-hub/.env.prod
```

Ensure:
- `DOCKER_REGISTRY=yourdockerhubusername` (matches your Docker Hub account)
- `ALLOWED_HOSTS=*` (or your domain e.g. `*.clarityhub.co.za,clarityhub.co.za,YOUR_AWS_IP`)
- `CSRF_TRUSTED_ORIGINS=http://*.clarityhub.co.za,https://*.clarityhub.co.za`

---

## 🌐 Multi-Tenant Domain Configuration (DNS)

To enable automatic subdomains for each client company (e.g. `demo.clarityhub.co.za`, `freshmart.clarityhub.co.za`):

1. In your Domain Registrar / DNS Provider (Route 53, Cloudflare, Namecheap, etc.):
   - Create an **A Record**: `@` $\rightarrow$ `YOUR_AWS_ELASTIC_IP`
   - Create a **Wildcard A Record**: `*` $\rightarrow$ `YOUR_AWS_ELASTIC_IP`
2. All tenant requests are automatically routed by `django-tenants` to the appropriate PostgreSQL tenant schema!

---

## ⚡ How to Trigger the 1-Click Update (From Your PC)

Whenever you have finished code changes or features:

1. Double-click **`push.bat`** (or `push_to_github.bat`).
2. The script will:
   - Read current version from `version.txt` (e.g. `1.0.0`) and propose `1.0.1`.
   - Prompt for an optional commit message.
   - Automatically execute all **25 automated tests** (`python manage.py test --settings=retail_hub.settings_test`).
   - If tests pass, commit and create a Git release tag (`v1.0.1`).
   - Push branch and tag to GitHub origin `main`.
3. **GitHub Actions takes over completely**:
   - Runs full test suite in GitHub's Ubuntu environment.
   - Builds and publishes `:latest` and `:v1.0.1` to Docker Hub.
   - Connects to your AWS EC2 instance via SSH.
   - Pulls the new Docker image and restarts the container stack.
   - Runs `migrate_schemas` and `create_public_tenant` automatically via `entrypoint.sh`.
   - Cleans up old Docker images.
   - **Your AWS Clarity Retail Hub is live and updated!**

---

## 🔄 Useful AWS Server Commands

Connect to your AWS instance anytime:

```bash
# View live web container logs
docker logs -f clarity_hub_prod_app

# View live database logs
docker logs -f clarity_hub_prod_db

# Manual 1-click update on server
/home/ubuntu/clarity-retail-hub/update.sh

# 1-second Instant Rollback to an older version (e.g. v1.0.0)
/home/ubuntu/clarity-retail-hub/rollback.sh v1.0.0

# Create Django Superuser inside the production container
docker compose -f /home/ubuntu/clarity-retail-hub/docker-compose.prod.yml exec web python manage.py createsuperuser

# Inspect tenant schemas in PostgreSQL
docker compose -f /home/ubuntu/clarity-retail-hub/docker-compose.prod.yml exec db psql -U hub_prod_user -d clarity_retail_hub_prod -c "\dn"
```
