# Terminal Container Startup Optimization Plan

## Executive Summary

**Current State:** Terminal containers take 5-10 seconds to start (median: ~6-8 seconds)

**Target:** Reduce startup time to <2 seconds (66-75% reduction)

**Challenge:** Containers are stateful - each requires a unique tunnel URL obtained at runtime, which complicates traditional snapshot/checkpoint approaches.

---

## Current Startup Breakdown

Based on codebase analysis, the startup sequence and timing is:

```
Total: 5-10 seconds
├── Container creation (docker run): ~1-2s
├── Terminado server startup: ~2-3s
│   └── Python/Tornado initialization
├── Localtunnel connection: ~1-2s
│   └── Network connection to tunnel server
└── API polling overhead: ~0-2s
    └── 2-second interval polling
```

### Bottleneck Analysis

**Primary Bottlenecks (70% of startup time):**
1. **Python/Tornado cold start** (~2-3s) - Loading Python interpreter, importing dependencies
2. **Container initialization** (~1-2s) - Docker layer extraction, namespace setup
3. **Localtunnel connection** (~1-2s) - Network round-trip to tunnel server

**Secondary Bottlenecks (30% of startup time):**
4. **Image pull/cache** (~0.5-1s) - Even with cached images, layer verification takes time
5. **DNS resolution** (~0.2-0.5s) - If using gVisor with custom DNS
6. **API polling latency** (~0-2s) - Polling interval can add up to 2 seconds

---

## Optimization Strategy Tiers

### Tier 1: Quick Wins (1-2 weeks, 20-30% improvement)

These optimizations require minimal code changes and can be implemented immediately.

#### 1.1 Parallelize Initialization Processes
**Current:** Sequential startup in `entrypoint.sh`
```bash
# Current (sequential):
start_terminado → wait_healthy → start_stats → start_idle → start_tunnel
```

**Optimization:** Start processes in parallel
```bash
# Proposed (parallel):
start_terminado & start_tunnel (in background)
→ wait_for_both → signal_ready
```

**Expected gain:** 1-2 seconds (reduce tunnel acquisition from sequential to parallel)

**Implementation:**
- Modify `terminal-container/entrypoint.sh:75-100`
- Start localtunnel immediately in background
- Start Terminado simultaneously
- Wait for both to be ready before signaling

**Files to modify:**
- `terminal-container/entrypoint.sh`

---

#### 1.2 Optimize Image Layers
**Current:** Base image `python:3.12-slim` + many tools installed

**Optimization:**
- Use multi-stage builds to reduce final image size
- Move heavy dependencies (git, vim, tmux) to optional layer
- Use `.dockerignore` to exclude unnecessary files
- Combine RUN commands to reduce layers

**Expected gain:** 0.5-1 second (faster layer extraction)

**Implementation:**
```dockerfile
# Stage 1: Build dependencies
FROM python:3.12-slim as builder
RUN pip install --user terminado tornado httpx psutil

# Stage 2: Runtime (minimal)
FROM python:3.12-slim
COPY --from=builder /root/.local /root/.local
# Install only essential runtime tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
```

**Files to modify:**
- `terminal-container/Dockerfile`

---

#### 1.3 Reduce Polling Interval
**Current:** API polls every 2 seconds with 60 max attempts

**Optimization:**
- Reduce initial polling interval to 0.5 seconds for first 20 attempts
- Use exponential backoff after that
- Implement WebSocket push notification instead of polling

**Expected gain:** 0.5-1.5 seconds (average case reduces by 1 second)

**Implementation:**
```python
# In terminals.py _poll_container_status()
intervals = [0.5] * 20 + [1.0] * 20 + [2.0] * 20  # Progressive backoff
```

**Files to modify:**
- `src/api/routes/terminals.py:27-82`

---

#### 1.4 Pre-compile Python Bytecode
**Current:** Python files compiled on first run

**Optimization:**
- Add `RUN python -m compileall /app` to Dockerfile
- Use `PYTHONDONTWRITEBYTECODE=0` to enable bytecode caching

**Expected gain:** 0.3-0.5 seconds (faster import times)

**Files to modify:**
- `terminal-container/Dockerfile`

---

#### 1.5 Optimize Localtunnel Connection
**Current:** Each container starts a new localtunnel process

**Optimization:**
- Add connection pooling/keep-alive to tunnel client
- Consider using `--local-host` flag to bind directly
- Implement retry logic with exponential backoff

**Expected gain:** 0.5-1 second (faster tunnel establishment)

**Files to modify:**
- `terminal-container/entrypoint.sh:100`

---

**Tier 1 Total Expected Improvement:** 3-6 seconds reduction → **Target: 2-4 second startup**

---

### Tier 2: Container Pre-warming (2-4 weeks, 50-70% improvement)

Create a pool of pre-warmed containers ready to accept connections.

#### 2.1 Container Pool Architecture

**Concept:** Maintain a pool of pre-started containers in "warm standby" mode.

**Flow:**
```
1. Pool Manager maintains N containers in READY state
2. User requests terminal → grab from pool → inject terminal_id
3. Background task replenishes pool
```

**Challenges with Stateful Containers:**
- **Tunnel URL uniqueness:** Each container needs unique tunnel
- **Solution:** Pre-allocate tunnels in pool, map to container on assignment

**Implementation approach:**
```python
# New service: ContainerPoolService
class ContainerPoolService:
    def __init__(self, pool_size=5):
        self.pool = asyncio.Queue(maxsize=pool_size)
        self.replenish_task = None

    async def get_warm_container(self):
        """Get a pre-warmed container from pool"""
        container = await self.pool.get()
        # Inject terminal_id via environment or API call
        await self._configure_container(container)
        return container

    async def _maintain_pool(self):
        """Background task to keep pool filled"""
        while True:
            if self.pool.qsize() < self.pool.maxsize:
                container = await self._create_warm_container()
                await self.pool.put(container)
            await asyncio.sleep(5)
```

**Tunnel handling strategy:**
- **Option A:** Pre-create tunnels in pool, assign on allocation
- **Option B:** Use multiplexed tunnel with path-based routing
- **Option C:** Use WebSocket reverse proxy instead of localtunnel

**Expected gain:** 4-6 seconds (eliminate container creation + initialization time)

**Files to create/modify:**
- New: `src/services/container_pool_service.py`
- Modify: `src/api/routes/terminals.py`
- Modify: `src/services/docker_cli_service.py`

---

#### 2.2 Lazy Tunnel Allocation

**Concept:** Don't wait for tunnel in critical path. Return terminal immediately, establish tunnel asynchronously.

**Flow:**
```
1. Create terminal record (PENDING)
2. Return terminal_id immediately to user
3. Background: start container + establish tunnel
4. Frontend polls for tunnel_url
```

**Expected gain:** Perceived latency reduced to <1 second (actual work still happens in background)

**Trade-off:** User must wait for tunnel before using terminal (but gets faster feedback)

**Files to modify:**
- `src/api/routes/terminals.py:151-221`

---

### Tier 3: Advanced Optimizations (4-8 weeks, 70-90% improvement)

#### 3.1 Memory Snapshots (CRIU/gVisor-based)

**Concept:** Checkpoint container after initialization, restore from memory snapshot.

**Approach:**
Based on Modal's implementation and CRIU documentation:

1. **Create golden snapshot:**
   ```bash
   # Start container, wait for Terminado ready
   docker checkpoint create --checkpoint-dir=/snapshots terminal-golden checkpoint-1
   ```

2. **Restore from snapshot:**
   ```bash
   # On terminal request
   docker start --checkpoint-dir=/snapshots --checkpoint=checkpoint-1 terminal-new
   ```

**Challenge with Stateful Containers:**
- **Problem:** Tunnel URL is baked into snapshot
- **Solution A:** Restore snapshot, then re-establish tunnel (still saves 2-3s)
- **Solution B:** Use snapshot for Terminado only, establish tunnel fresh
- **Solution C:** Use path-based routing with shared tunnel (see Tier 3.3)

**Implementation with gVisor:**
Modal uses gVisor's built-in checkpoint/restore instead of CRIU. If you're already using gVisor (`USE_GVISOR=True` in config):

```python
# Using gVisor's checkpoint API
import subprocess

# Create snapshot
subprocess.run([
    "docker", "checkpoint", "create",
    "--checkpoint-dir=/var/lib/gvisor-snapshots",
    "terminal-golden", "snap1"
])

# Restore
subprocess.run([
    "docker", "start",
    "--checkpoint-dir=/var/lib/gvisor-snapshots",
    "--checkpoint=snap1",
    f"terminal-{terminal_id}"
])
```

**Expected gain:** 3-5 seconds (skip Python initialization + dependency loading)

**Files to create/modify:**
- New: `src/services/snapshot_service.py`
- Modify: `src/services/docker_cli_service.py`
- New: Scripts for creating golden snapshots

**Limitations:**
- CRIU requires specific kernel versions (>4.3)
- Not all container runtimes support checkpoint/restore
- Network connections cannot be checkpointed (tunnel must reconnect)

---

#### 3.2 Replace Localtunnel with Custom Solution

**Current:** Node.js localtunnel client (adds ~500MB to image, 1-2s startup)

**Optimization:** Implement lightweight tunnel in Go/Rust

**Options:**

**Option A: Custom WebSocket Reverse Proxy**
```go
// Lightweight Go tunnel client (~5MB binary)
package main

import (
    "github.com/gorilla/websocket"
)

func main() {
    // Connect to tunnel server
    conn, _ := websocket.Dial("wss://tunnel.newsml.io/register", ...)
    // Get assigned subdomain
    // Forward local port 8888 to websocket
}
```

**Option B: Use existing lightweight tunnel (bore, ngrok alternative)**
- [bore](https://github.com/ekzhang/bore) - Rust-based, <5MB
- [chisel](https://github.com/jpillora/chisel) - Go-based, fast
- [frp](https://github.com/fatedier/frp) - Production-ready, 15MB

**Expected gain:** 0.5-1 second (faster tunnel establishment) + 400MB image size reduction

**Files to modify:**
- `terminal-container/Dockerfile`
- `terminal-container/entrypoint.sh`
- Infrastructure: Deploy custom tunnel server

---

#### 3.3 Multiplexed Tunnel Architecture

**Concept:** Use a single tunnel with path-based routing instead of per-container tunnels.

**Architecture:**
```
User Request → https://tunnel.newsml.io/terminal/{id}
           → API Gateway → Container {id}:8888
```

**Flow:**
1. Single persistent tunnel connection (or one per host)
2. Path includes `terminal_id`
3. API gateway routes to correct container by ID
4. No per-container tunnel needed

**Benefits:**
- Eliminates tunnel startup time completely
- Reduces tunnel server load
- Simpler container architecture

**Trade-offs:**
- Requires custom tunnel server
- Adds API gateway component
- Different security model (path-based auth vs subdomain isolation)

**Expected gain:** 1-2 seconds (eliminate tunnel connection entirely)

**Files to create:**
- New: Tunnel gateway service
- Modify: Frontend to use path-based URLs
- Remove: Localtunnel from container

---

#### 3.4 Lazy Image Loading (Stargz/Nydus)

**Concept:** Use containerd snapshotter to lazy-load container images.

Based on the documentation from lokiwager.github.io, this enables "pulling" images in <1 second by only downloading necessary layers.

**Implementation:**
```bash
# 1. Convert image to stargz format
ctr-remote images convert --estargz terminal-server:latest terminal-server:stargz

# 2. Configure containerd to use stargz snapshotter
# /etc/containerd/config.toml
[plugins."io.containerd.snapshotter.v1.stargz"]
  root_path = "/var/lib/containerd/snapshotter/stargz"
```

**Expected gain:** 0.5-1 second (faster image extraction)

**Requirements:**
- Switch from Docker to containerd (or Docker with containerd snapshotter)
- Pre-convert images to stargz/nydus format
- More complex infrastructure

---

#### 3.5 GPU Memory Snapshots (if using GPUs)

Not applicable for current terminal containers, but documented for future reference.

If you add GPU support (e.g., for ML workloads in terminals):

Based on Modal's GPU snapshot documentation:
- CUDA initialization takes 5-10 seconds
- GPU memory snapshots can preserve loaded models
- Requires `snap=False` lifecycle method for GPU transfer

---

### Tier 4: Architectural Alternatives (8-12 weeks, 90%+ improvement)

Fundamental architecture changes that eliminate container startup entirely.

#### 4.1 Persistent Terminal Containers

**Concept:** Keep containers running, multiplex users onto shared containers.

**Architecture:**
```
┌─────────────────────────────────────┐
│  Terminal Pool (persistent)         │
│  ├─ terminal-1 (10 tmux sessions)   │
│  ├─ terminal-2 (10 tmux sessions)   │
│  └─ terminal-3 (10 tmux sessions)   │
└─────────────────────────────────────┘
          ↓
User request → assign tmux session → return URL
```

**Flow:**
1. Maintain pool of long-running containers
2. Each container runs multiple tmux/screen sessions
3. Assign user to available session
4. Cleanup on disconnect

**Expected gain:** <500ms startup (just session allocation)

**Trade-offs:**
- Multi-tenant security concerns (user isolation)
- Resource limits more complex (per-session vs per-container)
- Requires process isolation within container
- Idle timeout affects multiple users

---

#### 4.2 WebAssembly Terminal (WASM)

**Concept:** Run terminal entirely in browser using WebAssembly.

**Architecture:**
```
Browser → WASM Shell (xterm.js + container2wasm) → API for persistence
```

**Benefits:**
- Zero server-side startup latency
- Infinite scaling (runs client-side)
- No container orchestration needed

**Trade-offs:**
- Limited functionality (no real filesystem, network)
- Requires complete rewrite
- Persistence/collaboration harder

---

#### 4.3 Hybrid: Pre-warmed + Snapshot

**Concept:** Combine container pooling (Tier 2) with snapshots (Tier 3).

**Flow:**
1. Pool maintains snapshots (not running containers)
2. On request, restore snapshot (1-2s) instead of cold start (5-10s)
3. Background replenishes snapshot pool

**Expected gain:** Combines benefits of both approaches

---

## Recommended Implementation Roadmap

### Phase 1: Quick Wins (Week 1-2)
**Target: 40% reduction → 3-4 second startup**

Priority order:
1. ✅ Parallelize initialization (`entrypoint.sh`)
2. ✅ Optimize polling interval (`terminals.py`)
3. ✅ Pre-compile Python bytecode (`Dockerfile`)
4. ✅ Optimize image layers (multi-stage build)

**Effort:** Low | **Impact:** Medium | **Risk:** Low

---

### Phase 2: Container Pooling (Week 3-4)
**Target: 65% reduction → 2 second startup**

1. Implement container pool service
2. Modify API to use pool
3. Handle tunnel pre-allocation or lazy allocation

**Effort:** Medium | **Impact:** High | **Risk:** Medium

---

### Phase 3: Snapshots (Week 5-8)
**Target: 80% reduction → 1 second startup**

1. Test CRIU/gVisor checkpoint support
2. Create golden snapshot pipeline
3. Modify service to restore from snapshots
4. Handle tunnel re-establishment after restore

**Effort:** High | **Impact:** High | **Risk:** High

---

### Phase 4: Custom Tunnel (Week 9-12)
**Target: 85% reduction → <1 second startup**

1. Evaluate lightweight tunnel alternatives (bore, chisel)
2. Deploy custom tunnel infrastructure
3. Replace localtunnel in containers
4. OR implement multiplexed tunnel architecture

**Effort:** High | **Impact:** Medium | **Risk:** Medium

---

## Handling the Stateful Container Challenge

The core challenge: **Each container needs a unique tunnel URL**, which is obtained at runtime.

### Strategy 1: Lazy Tunnel Allocation (Recommended for Phase 1-2)

Don't wait for tunnel before returning to user:
```
User Request → Create Terminal (PENDING) → Return immediately
            ↓
Background: Start container → Get tunnel → Update terminal (READY)
            ↓
Frontend: Poll for tunnel URL
```

**Pros:** Simple, non-breaking change
**Cons:** User still waits (but with better feedback)

---

### Strategy 2: Pre-allocated Tunnel Pool (Recommended for Phase 2)

Maintain pool of pre-established tunnels:
```python
class TunnelPool:
    def __init__(self):
        self.available_tunnels = Queue()
        # Pre-create 10 tunnel connections
        for _ in range(10):
            tunnel = self._create_tunnel()
            self.available_tunnels.put(tunnel)

    async def get_tunnel(self):
        tunnel = await self.available_tunnels.get()
        # Start background task to replenish
        return tunnel
```

**Pros:** Eliminates tunnel startup time
**Cons:** More complex, may waste tunnel resources

---

### Strategy 3: Multiplexed Tunnel (Recommended for Phase 4)

Single tunnel with path-based routing:
```
https://tunnel.newsml.io/{terminal_id} → API Gateway → Container
```

**Pros:** Eliminates per-container tunnels completely
**Cons:** Requires infrastructure changes

---

### Strategy 4: Snapshot with Fresh Tunnel (Recommended for Phase 3)

Use snapshots for Terminado initialization, but establish tunnel fresh:
```
Restore snapshot (Terminado ready in 1s) → Establish tunnel (1s) = 2s total
vs
Cold start (Terminado 3s + tunnel 1s) = 4s total
```

**Pros:** Still achieves significant speedup
**Cons:** Can't snapshot tunnel state (but that's inherent to network connections)

---

## Benchmarking Plan

Use the provided benchmark scripts to measure improvements:

### Baseline Measurement
```bash
# Run existing benchmark
python benchmark_startup.py

# Run comprehensive API benchmark
python benchmark_api_startup.py --iterations 20 --output baseline.json
```

### After Each Phase
```bash
python benchmark_api_startup.py --iterations 20 --output phase1.json
python benchmark_api_startup.py --iterations 20 --output phase2.json
# etc.
```

### Key Metrics to Track
- **Total startup time:** API call to tunnel ready
- **P50, P95, P99 latencies**
- **Container creation time**
- **Tunnel acquisition time**
- **Success rate** (% of terminals that start successfully)

---

## Risk Mitigation

### Technical Risks

1. **CRIU compatibility**
   - **Risk:** Kernel/runtime may not support checkpoint/restore
   - **Mitigation:** Test on staging first, fallback to pooling if unsupported

2. **Tunnel pool exhaustion**
   - **Risk:** Pool runs dry during traffic spikes
   - **Mitigation:** Dynamic pool sizing, circuit breaker pattern

3. **Snapshot invalidation**
   - **Risk:** Snapshots become stale (dependency updates)
   - **Mitigation:** Automatic snapshot refresh on image updates

4. **Network state after restore**
   - **Risk:** Restored containers have stale network connections
   - **Mitigation:** Force tunnel reconnect after restore

### Operational Risks

1. **Increased resource usage**
   - **Risk:** Container pools consume more memory
   - **Mitigation:** Monitor resource usage, tune pool size

2. **Complexity increase**
   - **Risk:** More moving parts, harder to debug
   - **Mitigation:** Comprehensive logging, gradual rollout

---

## Expected Results Summary

| Phase | Implementation | Startup Time | Reduction | Effort |
|-------|---------------|--------------|-----------|--------|
| Baseline | Current | 5-10s (median 6-8s) | - | - |
| Phase 1 | Quick wins | 3-4s | 40% | Low |
| Phase 2 | Container pooling | 1.5-2s | 65-75% | Medium |
| Phase 3 | Snapshots | 0.8-1.2s | 80-85% | High |
| Phase 4 | Custom tunnel | 0.5-1s | 85-90% | High |

---

## Monitoring & Observability

Add instrumentation to track:

```python
# In docker_cli_service.py
import time
from prometheus_client import Histogram

startup_duration = Histogram('terminal_startup_seconds', 'Terminal startup duration',
                             buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0])

@startup_duration.time()
async def create_terminal_container(self, terminal_id):
    # ... existing code
```

**Metrics to track:**
- `terminal_startup_seconds` - Total startup time
- `container_pool_size` - Available warm containers
- `tunnel_pool_size` - Available pre-allocated tunnels
- `snapshot_restore_seconds` - Time to restore from snapshot
- `startup_failure_rate` - % of failed startups

---

## Conclusion

With a phased approach focusing on quick wins first, you can achieve:
- **Short term (2 weeks):** 40% reduction → ~3-4 second startup
- **Medium term (4 weeks):** 70% reduction → ~2 second startup
- **Long term (8-12 weeks):** 85% reduction → <1 second startup

The recommended path balances implementation complexity with impact, starting with low-risk optimizations before tackling architectural changes.

**Next Steps:**
1. Run baseline benchmarks
2. Implement Phase 1 quick wins
3. Re-benchmark and validate improvements
4. Proceed to Phase 2 based on results
