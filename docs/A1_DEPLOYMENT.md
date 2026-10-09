# SONAR A1 deployment guide for laboratory IT

No laboratory infrastructure was modified or public deployment performed. The
server's OS, ports, resources, runtime and networking are unverified. The supplied
container configuration is for **Linux containers**; IT must verify compatibility
and choose settings for its existing environment. No infrastructure purchase or
managed database is needed.

## Local Windows development

Follow the README's virtual environment instructions. Run `python -m sonar_web`
and open `http://127.0.0.1:8000`. Node is unnecessary for application startup.
Uvicorn binds loopback by default, uses one worker, does not trust forwarded
headers and disables request access logs to keep URL parameters out of logs.

Environment variables are read from the launching process. `.env` is read by
Docker Compose, **not** automatically by the Python command. For example:

```powershell
$env:SONAR_PORT = "8080"
$env:SONAR_ALLOWED_ORIGINS = "http://127.0.0.1:8080,http://localhost:8080"
.\.venv\Scripts\python.exe -m sonar_web
```

## Docker Compose on an IT-verified host

Prerequisites: a compatible Docker Engine and Compose v2 on an IT-approved server
or local Linux-container environment, and internet access for package installation
and permitted supplier HTTPS reads. Validate the runtime and available ports first.

```sh
cp .env.example .env
# Edit .env for the verified host and intended reverse-proxy origin.
docker compose config
docker compose build
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8000/healthz
docker compose logs --tail=50 sonar
```

On Windows use `Copy-Item .env.example .env`. `SONAR_HOST_PORT` controls the host
port in Compose. Container port 8000 is internal and mapped to **host loopback**
by default. Do not change the mapping to a public interface for A1. Docker is not
installed on the development machine; container build/run is **not yet validated**.
See the validation record for the checks that were actually executed.

The image runs as UID 10001; Compose drops capabilities, sets a read-only root
filesystem, a bounded temporary filesystem, an init process and a health check.
No BoM volume or database is configured because storage is temporary. `restart:
unless-stopped` does not preserve sessions. Stop/redeploy clears work; users must
export first. A Docker base-image tag is used for portability; IT should pin an
approved tested digest when promoting a deployment under its update policy.

## Reverse proxy and private access

IT owns HTTPS, DNS, firewall, reverse proxy and any existing access-control system.
Before exposing the application to laboratory users:

- Verify the runtime, architecture, CPU/memory capacity and outbound HTTPS policy.
  Tune `SONAR_MAX_SESSIONS` / upload limit to actual available resources.
- Set `SONAR_ALLOWED_HOSTS` to the actual proxy hostname **plus localhost and
  127.0.0.1** (needed for health checks). These are hostnames without scheme/port;
  avoid wildcards. Example hostname placeholders are not actual infrastructure.
- Set `SONAR_ALLOWED_ORIGINS` to the exact browser origin including HTTPS and any
  nondefault port. Do not put paths or trailing slashes in origins.
- Set `SONAR_SECURE_COOKIE=true` when browsers access SONAR through HTTPS.
- Restrict access to the trusted laboratory network or use IT's existing proxy
  authentication. A1 has no account/login system and is not for public exposure.
- Limit upstream request bodies to the configured file size and apply appropriate
  proxy timeouts/rate limits. Preserve the original Host header; do not cache API
  responses. Serve frontend and API together at the origin root.
- Allow outbound HTTPS only as required for supported supplier domains, redirects
  and robots reads. No supplier credentials or API secrets are required.

If the reverse proxy is itself containerized, host loopback may not be reachable
from that container. IT must select an appropriate private network arrangement
after inspecting its existing setup; this repository does not alter that setup.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SONAR_BIND_HOST` | `127.0.0.1` locally | Uvicorn bind; image sets `0.0.0.0` inside container |
| `SONAR_PORT` | `8000` | Application listen port |
| `SONAR_HOST_PORT` | `8000` | Compose loopback host port |
| `SONAR_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated accepted Host names |
| `SONAR_ALLOWED_ORIGINS` | two local HTTP origins | Allowed origins for browser mutations |
| `SONAR_SECURE_COOKIE` | `false` | `true` for IT-managed HTTPS |
| `SONAR_MAX_UPLOAD_MB` | `8` | Request/upload byte limit in MiB |
| `SONAR_SESSION_TTL_SECONDS` | `7200` | Inactivity expiry |
| `SONAR_MAX_SESSIONS` | `100` | Session capacity; tune for measured resource capacity |

**Keep one worker and one replica.** In-memory sessions and supplier pacing are
process-local. Do not run concurrent A0 CLI probes against the same suppliers as
the application. Supplier requests are globally queued; the same proxy IP shares
the API's conservative 20-retrievals/minute quota because forwarded IP headers are
not trusted. This may limit throughput in a larger lab and is an A1 limitation.

## Operations and updates

`/healthz` confirms process health, not supplier access. The UI reports retrieval
failures and partial data; do not bypass supplier protections when those occur.
Logs report imports and exception types without request bodies or credentials.
Session expiry and process restarts remove BoMs; exported lists are user-managed.

To update: notify users to export, fetch the approved Git revision without force
overwrites, run tests, rebuild the image and restart. To stop: `docker compose down`.
IT should monitor memory, disk/container image capacity, health and dependency
updates according to its existing procedures. No external telemetry is configured.
