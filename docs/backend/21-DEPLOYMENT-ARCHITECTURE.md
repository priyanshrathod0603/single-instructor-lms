# Deployment Architecture & Production Infrastructure Specification

## 1. Production Topology Overview

The Single-Instructor LMS backend is designed for containerized deployment on cloud infrastructure (VPS, Kubernetes, or AWS ECS) behind a hardened reverse proxy with managed PostgreSQL and Redis instances.

```mermaid
graph TD
    User([Clients: Web & Mobile]) -->|HTTPS / TLS 1.3| CDN[Cloudflare CDN & Edge DDoS]
    CDN -->|Reverse Proxy / TLS| Ingress[Nginx / Caddy Ingress]
    
    subgraph Compute Cluster
        Ingress --> App1[FastAPI Node 1 (Uvicorn)]
        Ingress --> App2[FastAPI Node 2 (Uvicorn)]
        Worker[Outbox & Transcode Worker]
    end

    subgraph Data & Storage Layer
        App1 --> PgBouncer[PgBouncer Connection Pooler]
        App2 --> PgBouncer
        Worker --> PgBouncer
        PgBouncer --> PG[(PostgreSQL 17 Database)]
        
        App1 --> Redis[(Redis 7 Cluster)]
        App2 --> Redis
        Worker --> Redis
    end

    subgraph Object Storage & Gateways
        App1 --> R2[Cloudflare R2 Object Storage]
        App1 --> RZP[Razorpay Payment Gateway]
        Worker --> Resend[Resend Transactional Email]
    end
```

---

## 2. Multi-Stage Hardened Dockerfile Specification

The production image uses a minimal attack surface, runs as a non-privileged system user, and excludes build compilers from the final image:

```dockerfile
# Stage 1: Build dependencies
FROM python:3.14-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install .

# Stage 2: Hardened Runtime
FROM python:3.14-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user
RUN groupadd -r lmsgroup && useradd -r -g lmsgroup -s /sbin/nologin lmsuser

COPY --from=builder /install /usr/local
COPY . /app

USER lmsuser:lmsgroup

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]
```

---

## 3. Database Connection Pooling (PgBouncer & SQLAlchemy)

To prevent PostgreSQL connection saturation during traffic spikes:
1. **SQLAlchemy Engine Pooling**:
   * `pool_size = 20`
   * `max_overflow = 10`
   * `pool_timeout = 30`
   * `pool_pre_ping = True` (automatically detects and recovers from stale socket disconnects)
2. **Transaction Pooling with PgBouncer**:
   * Run in `pool_mode = transaction`.
   * Maps hundreds of transient web worker connections to 20 persistent PostgreSQL backend processes.

---

## 4. Health Checks & Diagnostics Probes

* **Liveness Probe (`GET /api/v1/health/live`)**:
  - Validates that the Python ASGI runtime is responding.
  - Returns `{"status": "live"}` with HTTP 200.
* **Readiness Probe (`GET /api/v1/health/ready`)**:
  - Performs an active database ping (`SELECT 1`) and Redis ping.
  - Returns HTTP 200 if all downstream dependencies are healthy.
  - If either PostgreSQL or Redis fails, returns HTTP 503 `{"status": "not_ready", "unhealthy": ["database"]}` so the load balancer stops routing user requests to the node.

---

## 5. Zero-Downtime Deployment & Migration Sequencing

To deploy updates without dropping user requests:
1. **Pre-Deployment Migration**:
   - Schema migrations must be **backward-compatible** (Expand and Contract pattern).
   - Execute `alembic upgrade head` before updating container versions.
2. **Rolling Container Update**:
   - Start new container instances with new code.
   - Wait for Kubernetes / Docker Swarm readiness probes to succeed.
   - Gracefully drain traffic from old container instances.
