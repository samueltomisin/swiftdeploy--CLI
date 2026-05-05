# SwiftDeploy

A declarative deployment CLI tool that manages your entire container stack from a single configuration file.

You describe your deployment in `manifest.yaml`. SwiftDeploy reads it and generates all the infrastructure files, brings up your containers, manages health checks, and handles mode switching — all from the command line.

---

## How It Works

```
manifest.yaml  →  swiftdeploy init  →  nginx.conf + docker-compose.yml  →  running stack
```

You only ever edit `manifest.yaml`. Everything else is generated automatically.

---

## Project Structure

```
swiftdeploy/
├── manifest.yaml                   # Your single source of truth — edit this only
├── swiftdeploy                     # The CLI tool
├── app/
│   ├── main.py                     # Python API service
│   ├── Dockerfile                  # How to build the API image
│   └── requirements.txt            # Python dependencies
└── templates/
    ├── nginx.conf.j2               # Nginx template (do not edit directly)
    └── docker-compose.yml.j2       # Docker Compose template (do not edit directly)
```

> `nginx.conf` and `docker-compose.yml` are **generated files** — they are created automatically by `swiftdeploy init` and should never be edited by hand.

---

## Prerequisites

Make sure you have the following installed on your machine before you begin:

| Tool | Purpose | Check if installed |
|---|---|---|
| Docker | Run containers | `docker --version` |
| Docker Compose | Manage multi-container stack | `docker compose version` |
| Python 3.8+ | Run the CLI tool | `python3 --version` |
| pip | Install Python packages | `pip --version` |

---

## Setup Instructions

### Step 1 — Clone the repository

```bash
git clone https://github.com/yourusername/swiftdeploy.git
cd swiftdeploy
```

### Step 2 — Install Python dependencies

The CLI tool needs two Python packages to run:

```bash
pip install pyyaml jinja2
```

- `pyyaml` — reads your `manifest.yaml` file
- `jinja2` — fills in the templates with values from the manifest

### Step 3 — Make the CLI executable

```bash
chmod +x swiftdeploy
```

This allows you to run `./swiftdeploy` directly from the terminal.

### Step 4 — Build the Docker image

```bash
docker build -t swift-deploy-1-node:latest ./app
```

This builds the Python API image locally. The image name must match exactly what is in `manifest.yaml`.

---

## The Manifest File

`manifest.yaml` is the only file you need to understand and edit. Here is what each field means:

```yaml
services:
  image: swift-deploy-1-node:latest   # Docker image name for the API
  port: 3000                          # Port the API listens on (internal only)
  mode: stable                        # Deployment mode: stable or canary
  version: "1.0.0"                    # App version injected into the container

nginx:
  image: nginx:latest                 # Nginx image to use
  port: 8080                          # Port exposed to the outside world
  proxy_timeout: 30                   # How long Nginx waits for a response (seconds)

network:
  name: swiftdeploy-net               # Name of the Docker network
  driver_type: bridge                 # Network type (bridge = standard Docker network)
```

> **Important:** The API port (3000) is never exposed directly to your machine. All traffic goes through Nginx on port 8080. This is intentional and is a security best practice.

---

## Subcommand Walkthrough

### `init` — Generate configuration files

```bash
./swiftdeploy init
```

Reads `manifest.yaml` and generates two files:
- `nginx.conf` — Nginx reverse proxy configuration
- `docker-compose.yml` — Docker Compose stack definition

Run this first, or any time you change `manifest.yaml` manually.

**Expected output:**
```
swiftdeploy init
  ✔  Generated nginx.conf
  ✔  Generated docker-compose.yml
```

---

### `validate` — Check everything before deploying

```bash
./swiftdeploy validate
```

Runs 5 checks to make sure your stack is ready to deploy:

| Check | What it verifies |
|---|---|
| 1 | `manifest.yaml` exists and is valid YAML |
| 2 | All required fields are present and filled in |
| 3 | The Docker image exists locally |
| 4 | The Nginx port is not already in use |
| 5 | The generated `nginx.conf` has no syntax errors |

If any check fails, the tool tells you exactly what is wrong and exits without deploying.

**Expected output (all passing):**
```
swiftdeploy validate

  [1/5] manifest.yaml exists and is valid YAML
  ✔  manifest.yaml found and parsed successfully

  [2/5] Required fields present and non-empty
  ✔  All required fields present

  [3/5] Docker image exists locally
  ✔  Image 'swift-deploy-1-node:latest' found locally

  [4/5] Nginx port not already bound on host
  ✔  Port 8080 is available

  [5/5] nginx.conf syntax check
  ✔  nginx.conf syntax is valid

  All 5 checks passed. Stack is ready to deploy.
```

---

### `deploy` — Bring up the full stack

```bash
./swiftdeploy deploy
```

Does three things in order:
1. Runs `init` to generate fresh config files
2. Starts all containers with `docker compose up`
3. Polls `http://localhost:8080/healthz` every 3 seconds until the stack is healthy (60 second timeout)

Once healthy, your API is reachable at `http://localhost:8080`.

**Expected output:**
```
swiftdeploy deploy

swiftdeploy init
  ✔  Generated nginx.conf
  ✔  Generated docker-compose.yml

  Starting stack with docker compose...

  Waiting for stack to be healthy (polling http://localhost:8080/healthz)...
     3s — waiting...
     6s — waiting...
  ✔  Stack is healthy after 9s
  ✔  Service reachable at http://localhost:8080
```

---

### `promote` — Switch deployment mode

```bash
./swiftdeploy promote canary    # switch to canary mode
./swiftdeploy promote stable    # switch back to stable mode
```

Switches the API between stable and canary mode without rebuilding the image or restarting Nginx. It:
1. Updates the `mode` field in `manifest.yaml`
2. Regenerates `docker-compose.yml` with the new mode
3. Restarts the API container only
4. Hits `/healthz` to confirm the new mode is live

**What changes in canary mode:**
- Every API response includes an `X-Mode: canary` header
- The `POST /chaos` endpoint becomes active

**Expected output:**
```
swiftdeploy promote → canary

  ✔  manifest.yaml updated: mode stable → canary
  ✔  docker-compose.yml regenerated

  Restarting app container...
  ✔  App container restarted

  Confirming new mode via http://localhost:8080/healthz...
  ✔  /healthz confirmed mode: canary
```

---

### `teardown` — Stop and remove everything

```bash
./swiftdeploy teardown           # stop containers, remove network and volumes
./swiftdeploy teardown --clean   # also delete nginx.conf and docker-compose.yml
```

Stops all containers and removes the Docker network and volumes.

Use `--clean` when you want a completely fresh start — it deletes the generated config files too so `init` starts from scratch next time.

---

## API Endpoints

Once deployed, the API is available at `http://localhost:8080`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Welcome message with current mode, version, and timestamp |
| GET | `/healthz` | Health check — returns status and how long the service has been running |
| POST | `/chaos` | Simulate failures (canary mode only) |

### Testing the endpoints

```bash
# Welcome message
curl http://localhost:8080/

# Health check
curl http://localhost:8080/healthz

# Simulate slow responses (canary mode only)
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "slow", "duration": 3}'

# Simulate random errors at 50% rate (canary mode only)
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "error", "rate": 0.5}'

# Stop all chaos
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "recover"}'
```

---

## Full Workflow Example

```bash
# 1. Build the image
docker build -t swift-deploy-1-node:latest ./app

# 2. Validate everything is ready
./swiftdeploy validate

# 3. Deploy the stack
./swiftdeploy deploy

# 4. Test the API
curl http://localhost:8080/
curl http://localhost:8080/healthz

# 5. Switch to canary mode
./swiftdeploy promote canary

# 6. Confirm canary is active
curl http://localhost:8080/healthz

# 7. Test chaos endpoint
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "error", "rate": 0.5}'

# 8. Recover and switch back to stable
curl -X POST http://localhost:8080/chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "recover"}'

./swiftdeploy promote stable

# 9. Tear everything down
./swiftdeploy teardown --clean
```

---

## Troubleshooting

**`Permission denied` when running `./swiftdeploy`**
```bash
chmod +x swiftdeploy
```

**`ModuleNotFoundError: No module named 'yaml'`**
```bash
pip install pyyaml jinja2
```

**`Image not found` on validate check 3**
```bash
docker build -t swift-deploy-1-node:latest ./app
```

**`Port 8080 already in use` on validate check 4**
```bash
# Find what is using the port
lsof -i :8080
# Stop it, then re-run validate
```

**Stack not becoming healthy during deploy**
```bash
# Check container logs
docker compose logs app
docker compose logs nginx
```

---

## Nginx Behaviour

All traffic enters through Nginx on port 8080. The API container is never accessible directly from outside.

**Headers added to every response:**

| Header | Value | Purpose |
|---|---|---|
| `X-Deployed-By` | `swiftdeploy` | Identifies this stack |
| `X-Mode` | `canary` | Only present in canary mode, forwarded from the API |

**Error responses:**

If the API is down or unreachable, Nginx returns a JSON error body instead of the default HTML page:

```json
{ "error": "bad gateway", "code": "502", "service": "app", "contact": "ops@swiftdeploy" }
```

This applies to 502, 503, and 504 errors.

**Access log format:**

Every request is logged in this format:

```
2026-05-05T10:00:00+00:00 | 200 | 0.003s | 172.18.0.2:3000 | GET / HTTP/1.1
```

To view live access logs:

```bash
docker compose logs -f nginx
```

---

## Security Practices

This project follows container security best practices throughout.

**Non-root user** — the API container runs as `appuser`, not as root. Running as root inside a container is a security risk because if the container is compromised, the attacker has root-level access.

**Dropped Linux capabilities** — the compose file includes `cap_drop: ALL`, which strips all Linux kernel privileges from the container. The API does not need any special system permissions to serve HTTP traffic.

**No exposed service port** — the API container uses `expose` (internal only) instead of `ports` (host-accessible). This means port 3000 is only reachable by other containers on the same Docker network. All external traffic must go through Nginx.

**Lightweight image** — the API image is built on `python:3.12-alpine` which is a minimal Linux base. This keeps the image small (well under 300MB) and reduces the attack surface.

**Gunicorn as the production server** — Flask's built-in development server is not suitable for production. Gunicorn is a proper WSGI server that handles concurrent requests safely.

---

## Design Decisions

**Why a single manifest file?**
Having one source of truth means you can never have a mismatch between your Nginx config and your Compose file. Both are generated from the same values at the same time.

**Why Jinja2 for templates?**
Jinja2 is the industry standard templating engine used by Ansible, Helm, and SaltStack. It handles substitution, whitespace control, and is readable without prior knowledge.

**Why Python for the CLI?**
Python has native YAML parsing (PyYAML) and Jinja2 support. Bash would require external tools like `yq` and `envsubst` which may not be installed on every machine.

**Why Gunicorn with 2 workers?**
A single Flask process can only handle one request at a time. Gunicorn with 2 workers allows the API to handle concurrent requests, including the chaos simulation which involves `time.sleep()`.

**Why are `/healthz` and `/chaos` exempt from chaos?**
`/healthz` must always respond accurately so health checks and deploy polling work correctly. `/chaos` is the control endpoint — applying chaos to the chaos controller would make it impossible to recover.

---

## Screenshots

Screenshots required for submission are stored in Google Drive and cover:

1. `validate` output — all 5 checks passing
2. `deploy` output — stack coming up and health check confirming
3. `promote canary` output + `/healthz` response confirming canary mode
4. Generated `nginx.conf` contents
5. Generated `docker-compose.yml` contents
6. Nginx access logs output

---

## Repository Contents

```
swiftdeploy/
├── manifest.yaml                   # Single source of truth
├── swiftdeploy                     # CLI executable
├── README.md                       # This file
├── app/
│   ├── main.py                     # Python API (Flask + Gunicorn)
│   ├── Dockerfile                  # Alpine-based image, non-root user
│   └── requirements.txt            # flask, gunicorn
└── templates/
    ├── nginx.conf.j2               # Nginx Jinja2 template
    └── docker-compose.yml.j2       # Docker Compose Jinja2 template
```

> `nginx.conf` and `docker-compose.yml` are generated at runtime by `./swiftdeploy init` and are not committed to the repository.

---

## Tech Stack

| Component | Technology |
|---|---|
| API Service | Python + Flask + Gunicorn |
| Reverse Proxy | Nginx |
| Containerisation | Docker + Docker Compose |
| Config Generation | Python + Jinja2 templates |
| CLI | Python |
| Manifest | YAML |