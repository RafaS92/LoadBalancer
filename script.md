# Load Balancer Video Demo Script

## Before recording

Have these tools ready:

- **Docker Desktop** to run and visually inspect the five containers.
- **Postman** for sending requests and inspecting responses.
- **A terminal** for `make` and Docker Compose commands.
- **A browser** open to `http://127.0.0.1:3000` for the dashboard.
- **The code editor** with this repository open.
- Keep the Docker Desktop **Logs** view for the `load-balancer` container ready to show.

Clean up any previous stack, then start from a predictable state:

```bash
make docker-down
make docker-up
make docker-ps
```

# Part 1 — Live demo first

## 1. Introduction and problem statement — 1 minute

### Show

Start on the dashboard at `http://127.0.0.1:3000`.

### Say

> This project is a small, production-minded reverse proxy and load balancer written in Python. A client always calls one address, port 8080, while the load balancer decides which backend should do the work. The React dashboard lets us observe those decisions, but the Python service is the component actually balancing traffic.

> We have three independent demo backends. The client does not know their addresses and does not have to decide whether they are healthy or busy. That responsibility belongs to the load balancer.

Briefly point out the dashboard summary cards, backend table, and recent requests. Mention that it refreshes every five seconds.

### Code reference for later

- Dashboard UI: `frontend/src/App.tsx`, lines 6–47.
- Five-second polling: `frontend/src/hooks/useDashboard.ts`, lines 6–43.
- Dashboard endpoint: `frontend/src/api.ts`, lines 3–18.

## 2. Why Docker and which tools are used — 2 minutes

### Show

Run:

```bash
make docker-ps
```

Then open Docker Desktop and expand the `load-balancer` Compose application.

### Say

> Docker is especially useful here because a load balancer only makes sense when several independent services are running. Compose gives us five containers: one frontend, one load balancer, and three backends.

> Isolation also makes failure testing realistic. I can stop one backend without stopping the load balancer or the other backends. 

> The main tools are Python for the reverse proxy and demo servers, React and TypeScript for the dashboard, Nginx to serve the production frontend and proxy its API calls, Prometheus's client library for metrics, Docker Compose for orchestration, and Postman for sending and inspecting HTTP requests.


## 3. Demonstrate round robin — 2 minutes

### Show

In Postman, open **Proxied request** and click **Send** six times. Keep the Postman Console open, or pause briefly after each response so the `backend` field is visible.

The `backend` field should rotate through `backend-a`, `backend-b`, and `backend-c`.

Refresh or wait for the dashboard to update.

### Say

> Every request goes to the same public address, but the response tells us which internal server handled it. With the default round-robin strategy, the load balancer repeatedly rotates A, B, C. The path, request ID, and forwarding information also survive the proxy boundary.

> This is the key benefit: clients see one stable interface while the server-side topology remains hidden and changeable.

## 4. Demonstrate health checks and failure isolation — 3 minutes

### Show

Stop one backend:

```bash
docker compose stop backend-a
```

Wait about five seconds. Watch the dashboard until `backend-a` becomes unhealthy. In Postman, send **Proxied request** six more times.

Only `backend-b` and `backend-c` should appear.

Restore the backend:

```bash
docker compose start backend-a
```

After it becomes healthy again, send **Proxied request** six more times in Postman. `backend-a` should appear in the responses again.

### Say

> The client address never changed. After two failed probes, backend A was removed from the eligible set, so traffic continued through B and C. After two successful probes, it rejoined the rotation automatically.

> We do not change a backend's health after only one check. A single failure could be caused by a temporary network delay, so the load balancer requires two failures in a row before removing the backend. It also requires two successful checks before adding it back. This prevents the backend from repeatedly entering and leaving the rotation because of short, temporary problems.


## 5. Demonstrate logs, metrics, and the dashboard — 2 minutes

### Logs

Use the Docker Desktop application:

1. Open **Docker Desktop** and select **Containers** from the sidebar.
2. Find and expand the **load-balancer** Compose application.
3. Select the **load-balancer** container—the Python service, not one of the demo backend containers.
4. Open its **Logs** tab.
5. In Postman, send **Proxied request** once, then return to Docker Desktop. A new `proxy_request_completed` log should appear.
6. Use the Docker Desktop log search to look for `proxy_request_completed`, `backend_health_changed`, a backend name, or a request ID.

Point out one completed-request event and identify these fields:

- `event`: the type of event that occurred.
- `method` and `path`: the request that was handled.
- `status`: the HTTP status returned to the client.
- `backend`: the server selected by the load balancer.
- `outcome`: whether the request completed normally or encountered a classified failure.
- `request_id`: the value used to follow one request across the system.
- `duration_ms`: how long the proxy operation took.

If the earlier failure demonstration is still visible, search for `backend_health_changed` and point out the `healthy`, `reason`, and `threshold` fields.

### Say

> A log records a specific event that happened inside the load balancer. For example, this `proxy_request_completed` entry tells me which request arrived, which backend handled it, the result returned to the client, and how long it took. If I need to investigate one request, I can search for its request ID and find the related record.

> The logs use JSON instead of unstructured sentences. Each piece of information has a consistent field name, which makes the records easier to search, filter, and process in a logging system. A `backend_health_changed` event records a different kind of event: a backend crossed its failure or recovery threshold and changed health state.

> I intentionally do not log request headers or bodies. They could contain authorization tokens, passwords, personal information, or large payloads. The log keeps only the operational information needed to understand the request safely.

# Part 2 — Concepts and code walkthrough

## 6. Proxy versus reverse proxy — 1.5 minutes

### Say

> A proxy is a program in the middle that passes a request and response between two programs. A forward proxy represents clients. A reverse proxy represents servers: the client calls the proxy without knowing which internal server will handle the request.

> This project has two reverse-proxy boundaries. The Python load balancer receives application traffic and chooses one of three backends. 

### Show in code

2. `backend/src/load_balancer/adapters/inbound/http/handler.py`, lines 61–89: incoming `GET` and `POST` handling.
3. `backend/src/load_balancer/adapters/outbound/http/upstream.py`: the outgoing HTTP connection to the selected backend.
4. `backend/src/load_balancer/adapters/outbound/http/response.py`: the safe response relay back to the client.

## 7. Complete request flow — 3 minutes

Use this summary while moving through the files:

```text
Client
  → HTTP handler validates and creates UpstreamRequest
  → ProxyService acquires an eligible backend
  → routing policy selects the backend and counts active work
  → UpstreamTransport forwards the request
  → ResponseRelay sends the backend response to the client
  → finally releases the backend
  → RequestCompleted event feeds logs, metrics, and dashboard
```

### Step 1: inbound HTTP boundary

Show `backend/src/load_balancer/adapters/inbound/http/handler.py`, lines 61–76 and 152–174.

Say:

> The handler is the HTTP-specific entry point. It validates message framing and size before selecting a backend, preserves or creates a request ID, and converts the incoming request into an `UpstreamRequest`. That object is a DTO: it carries data without making routing decisions.

### Step 2: orchestration

Show `backend/src/load_balancer/application/proxying.py`, lines 46–135.

Say:

> `ProxyService.execute` owns the complete use case. It acquires a backend, sends the request, relays the response, classifies failures, optionally retries, and always releases the backend in a `finally` block.

Point to:

- Lines 58–67: attempt loop and backend acquisition.
- Lines 78–85: outbound send and response relay.
- Lines 86–102: failure classification and retry decision.
- Lines 122–133: completion and guaranteed release.

### Step 3: transport and response

Show these sections in `backend/src/load_balancer/adapters/outbound/http/upstream.py`:

- **Lines 44–59 — connection and timeouts:** creates the connection using the selected backend's host and port, applies the connection timeout, classifies connection failures, and changes to the response timeout after connecting.
- **Lines 60–75 — forwarding the request:** sends the original method, path, body, and prepared headers; receives the backend response; classifies response failures; and always closes the connection in `finally`.
- **Lines 77–96 — trusted forwarding headers:** removes untrusted client-supplied forwarding and hop-by-hop headers, then creates trusted `Host`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and `X-Request-Id` values.

Then show these sections in `backend/src/load_balancer/adapters/outbound/http/response.py`:

- **Lines 29–55 — response framing and size limit:** reads the backend status and headers, determines whether a body is expected and how its length is framed, and rejects a response that exceeds the configured limit.
- **Lines 56–78 — streaming and failure detection:** sends the backend status and headers to the client, reads the body in bounded chunks, and detects timeouts, incomplete responses, and client disconnections.
- **Lines 109–117 — safe response headers:** removes hop-by-hop headers and values that the proxy must generate itself before returning headers to the client.

Say:

> The transport handles how to communicate with a backend: connection, timeout, and trusted forwarding headers. The relay preserves the backend status and safe headers while enforcing response limits and detecting incomplete responses or client disconnections.

While showing `upstream.py`, say:

> This is where the selected backend becomes a real HTTP connection. The transport has one timeout for establishing the connection and another for waiting on the connected backend. It forwards the client's method, path, and body, but it replaces forwarding headers with values that the load balancer trusts instead of accepting values that a client could fake.

While showing `response.py`, say:

> The response relay takes the selected backend's response and safely delivers it to the original client. It keeps the backend's status, filters unsafe connection-specific headers, limits the response size, and streams framed bodies in chunks. If the backend stops early, takes too long, or the client disconnects, the relay returns a specific outcome that the proxy service can record.

### Step 4: observable completion

Show `backend/src/load_balancer/application/proxying.py`, lines 217–241.

Say:

> At the end, the service publishes one typed `RequestCompleted` event.

## 8. Routing strategies: round robin and least connections — 2 minutes

Open `backend/src/load_balancer/domain/routing.py`.

### Round robin

Show lines 40–57.

Say:

> Round robin starts at a shared cursor and picks the first eligible backend. Modulo arithmetic wraps the cursor back to the beginning, so the order repeats. It skips any backend that is unhealthy, disabled, or excluded because this request already tried it.

Then show lines 174–194.

> The pool builds the eligible set, delegates selection to the policy, and advances the cursor to the position after the selected backend.

### Least connections

Show lines 60–85.

Say:

> Least connections chooses the eligible backend with the smallest number of active requests. This is useful when requests take different amounts of time, because equal request counts do not necessarily mean equal current load. If several backends are tied, it uses the round-robin cursor to keep the tie-break fair.

Show lines 215–222.

> `create_pool` selects the policy from the configured `--strategy`. Round robin is the default; `least-connections` is the alternative.

For a concise executable proof, show tests instead of trying to create slow live traffic:

- Round-robin order: `backend/tests/test_routing.py`, lines 21–34.
- Least-connections behavior: `backend/tests/test_routing.py`, lines 172–195.

Optional command:

```bash
cd backend
python -m pytest tests/test_routing.py -q
```

## 9. What a lock is and why this project needs one — 2 minutes

Show `backend/src/load_balancer/domain/routing.py`, lines 88–134.

### Say

> The HTTP server is threaded, so several client requests can select and update backends at the same time. Health checks and operator actions also update this shared state. A lock allows only one thread at a time into a short critical section, like one person at a time updating a shared whiteboard.

> Without the lock, two threads could read the same round-robin cursor and both take the same turn. They could also overwrite active-request counts. Here, selecting a backend and incrementing its active count happen atomically under the same lock.

Point to:

- Line 109: creation of `Lock`.
- Lines 117–124: atomic select plus active-request increment.
- Lines 126–134: safe decrement.
- Lines 136–172: health, operator state, draining, and snapshots protected by the same lock.

## 10. Why snapshots are needed — 1.5 minutes

Show `backend/src/load_balancer/domain/models.py`, lines 16–24, and `backend/src/load_balancer/domain/routing.py`, lines 159–172.

### Say

> A snapshot is a stable copy of state at one moment. The pool copies every backend's health, enabled state, draining state, and active-request count while holding the lock, then immediately releases the lock.

> Readers get a coherent view without accessing mutable dictionaries or holding the routing lock during slower work. A snapshot does not promise that the world cannot change afterward; it promises that the fields in the returned view agree with one another.

### Where snapshots are used

- Admin reads
- Dashboard combination
- Health worker
- Dashboard traffic snapshot

## 11. Why health checks are needed — 1.5 minutes

Show `backend/src/load_balancer/infrastructure/health_worker.py`, lines 37–53 and 73–76.

### Say

> A routing algorithm is useful only if it avoids servers that cannot handle work. The worker probes every backend immediately and then every two seconds by default. The probes run concurrently, so one slow server does not delay the checks for all the others.

Then show `backend/src/load_balancer/application/health.py`, lines 34–75.

> The evaluator turns consecutive probe results into state changes. Two failures mark a backend unhealthy and two successes restore it. Only when a threshold is crossed does it update the pool and publish a `HealthChanged` event.



> A retry can preserve availability when the chosen backend cannot even be reached. The failed backend is added to `attempted_backends`, and the next acquisition excludes it, so the same request can try another eligible server.

> Retrying everything would be dangerous. This project allows one additional attempt only for `GET` requests and only for connection timeout or connection failure. It does not retry `POST`, response timeouts, or failures after work may have started, because that could perform a write twice.

Show the policy constants at `backend/src/load_balancer/infrastructure/defaults.py`, lines 13–15 and 36–39.

Useful test references:

- Successful safe retry: `backend/tests/test_proxy_service.py`, lines 133–151.
- Mutating request is not retried: `backend/tests/test_proxy_service.py`, lines 154–175.

Important phrase:

> The request ID correlates attempts in logs, but it is not an idempotency key and cannot by itself make a repeated write safe.

## 13. Why logs are needed — 1 minute

Show `backend/src/load_balancer/ports/events.py`, lines 11–58, then `backend/src/load_balancer/adapters/observability/events.py`, lines 24–106.

### Say

> Typed events describe what happened without deciding how it will be displayed. `CompositeEventSink` sends each event to independent consumers. `StructuredLogEventSink` converts meaningful events into compact JSON.

> Logs let an operator investigate a particular request, failure, health transition, or manual backend action. Stable fields such as event, status, backend, outcome, request ID, and duration are much easier to search than prose.

Point out the three main log events:

- `proxy_request_completed`
- `backend_health_changed`
- `backend_operator_state_changed`

# Part 3 — Closing

## 16. Closing statement — 30 seconds

Return to the dashboard.

### Say

> The main idea is not just distributing requests. A useful load balancer combines routing, concurrency safety, health awareness, conservative retries, and observability behind one stable address. Docker makes the complete distributed setup reproducible, and the code keeps each responsibility small enough to inspect and test independently.

> This project is intentionally educational rather than a replacement for production systems such as Nginx, HAProxy, Envoy, or a managed cloud load balancer, but it demonstrates the same core decisions those systems must make.
