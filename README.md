# Learning Load Balancer

This project is a production-minded HTTP/1.1 load balancer built to develop and
demonstrate senior software engineering skills. It will be implemented in small,
testable steps so that every design decision can be understood and explained.

## The problem

A client should not need to know which application server can handle its
request. The load balancer provides one stable address, selects an available
backend, forwards the request, and returns the backend's response.

If no backend is healthy, the load balancer returns `503 Service Unavailable`
instead of forwarding traffic to a backend that is expected to fail.

## Request flow

```text
Client
  |
  | HTTP request
  v
Load balancer
  |
  | Select a healthy backend and forward the request
  v
Backend service
  |
  | HTTP response
  v
Load balancer
  |
  | Preserve the response status, headers, and body
  v
Client
```

## Version 1 responsibilities

- Accept HTTP/1.1 requests through one stable endpoint.
- Forward request methods, paths, query parameters, headers, and bodies.
- Select a healthy backend using round-robin or least-connections routing.
- Detect unhealthy backends and stop assigning new requests to them.
- Apply explicit connection and response timeouts.
- Retry only when doing so cannot duplicate unsafe work.
- Let operators enable, disable, and gracefully drain backends.
- Expose structured logs, metrics, and a local administration API.
- Show system and backend health through a React dashboard.
- Run as a reproducible, one-command Docker Compose demonstration.

## Non-goals for version 1

- HTTPS termination or certificate management.
- HTTP/2, HTTP/3, or raw TCP load balancing.
- Authentication or a public administration API.
- Multiple load-balancer nodes or distributed state.
- Automatic service discovery.
- Rate limiting, caching, or request transformation.
- Replacing a production proxy such as HAProxy, Envoy, or NGINX.

Keeping these features out of version 1 lets us study the core request path,
failure handling, concurrency, testing, and observability without hiding those
concepts behind a large framework.

## Related infrastructure

- **Reverse proxy:** Receives traffic on behalf of backend servers. Our load
  balancer is a reverse proxy that also chooses among multiple backends.
- **Load balancer:** Distributes traffic across backend instances to improve
  availability and use capacity effectively.
- **API gateway:** Usually adds application-level policies such as
  authentication, quotas, transformations, and API routing. Those policies are
  outside this project's first version.
- **Service mesh:** Manages service-to-service communication across many
  applications, commonly using a proxy beside each service. This project is one
  centralized entry point, not a mesh.

## Definition of done

Version 1 is complete when:

1. `make demo` starts the load balancer, dashboard, traffic generator, and three
   identifiable backend services from a fresh clone.
2. Requests are distributed according to the selected routing strategy.
3. Stopping one backend does not stop successful traffic through the remaining
   healthy backends.
4. When every backend is unavailable, clients receive a controlled `503`
   response.
5. The dashboard and metrics make routing decisions, latency, errors, and
   backend state visible.
6. Automated tests cover routing, concurrency, failure, recovery, draining,
   timeouts, and retry safety.
7. The repository documents its architecture, important tradeoffs, benchmark
   method and results, known limitations, and troubleshooting steps.
8. The full behavior can be explained and demonstrated in approximately five
   minutes without changing source code.

## Learning workflow

The project advances one small step at a time. Each step introduces one main
concept, adds focused verification, records the important tradeoff, and ends at
a runnable checkpoint before the next step begins.

## Current checkpoint

The application accepts HTTP `GET`, `POST`, and `DELETE` requests and can be
configured without editing source code. With no arguments it listens on
`127.0.0.1:8080` and uses demonstration backends on ports 9001 through 9003.

Custom addresses use repeatable `--backend` arguments:

```shell
load-balancer --listen-host 0.0.0.0 --listen-port 8088 \
  --strategy least-connections \
  --upstream-connect-timeout 1 \
  --upstream-response-timeout 5 \
  --max-retries 1 \
  --max-request-body-bytes 1048576 \
  --max-response-body-bytes 1048576 \
  --backend api-a=http://10.0.0.1:9000 \
  --backend api-b=http://10.0.0.2:9000 \
  --health-path /ready \
  --health-interval 5 \
  --health-timeout 1 \
  --health-failure-threshold 3 \
  --health-success-threshold 2
```

Configuration is validated before the server starts. A background health
checker uses HTTPX to request `/health` from every backend immediately at
startup and every two seconds afterward. Only `2xx` responses are healthy;
connection errors, timeouts, and other statuses remove a backend from rotation.
All backends keep being checked, so recovered instances rejoin automatically.

The health path, interval, and timeout are configurable and validated before
startup. Backend state is available from the read-only administration endpoint:

```shell
curl http://127.0.0.1:8080/admin/backends
```

It returns each backend's name, URL, and current health as JSON without changing
the routing sequence. The endpoint is currently unauthenticated and shares the
traffic listener, so it should not be exposed publicly. Health probes for
independent backends run concurrently, so one slow probe does not delay probes
to the remaining backends. Request and response bodies are buffered in memory
within configured limits.
Each completed proxy request writes one JSON log event containing its method,
path, selected backend, status, outcome, and duration. Request headers and
bodies are intentionally excluded to avoid leaking sensitive data.

Prometheus counters and latency histograms derived from the same completed
request events are available from `GET /metrics`. The official Prometheus client
provides thread-safe metric updates and the standard exposition format. Like the
administration endpoint, metrics currently share the traffic listener and
should not be exposed publicly. The routing pool now tracks active requests per
backend through matched acquire/release operations, and `/admin/backends`
includes each count. Routing defaults to `round-robin`; passing
`--strategy least-connections` selects the healthy backend with the lowest
active-request count and uses round-robin ordering to break ties. The next
health checker requires two consecutive failures before removing a backend and
two consecutive successes before restoring it by default. Either threshold is
configurable. Each resulting state change emits a structured
`backend_health_changed` log event. Prometheus exposes current backend health as
a `1` or `0` gauge and counts transitions by backend and destination state. The
administration API now separates automatic health from operator intent:

```shell
curl -X POST http://127.0.0.1:8080/admin/backends/backend-a/disable
curl -X POST http://127.0.0.1:8080/admin/backends/backend-a/enable
```

Disabled backends receive no new requests, but existing requests finish and
health checks continue. A health recovery never overrides a disabled state.
These unauthenticated actions are intended for local administration only. The
graceful drain action makes maintenance readiness explicit:

```shell
curl -X POST http://127.0.0.1:8080/admin/backends/backend-a/drain
```

It stops new assignments immediately while existing requests finish. The
response and backend snapshot report `drained: true` once `active_requests`
reaches zero. Backend connection and response waits have separate two-second
defaults and can be configured with `--upstream-connect-timeout` and
`--upstream-response-timeout`. Either timeout produces a controlled `502` and
releases the backend's active-request count. Clients still receive the same safe
`502`, while logs and Prometheus labels distinguish connection timeouts,
connection failures, response timeouts, and other response failures. The next
safe retry policy gives `GET` one additional attempt by default only after a
connection timeout or failure, before request bytes were sent. Retries exclude
previously attempted backends. `POST` and response-phase failures are never
retried, preventing duplicate writes. `--max-retries 0` disables retries. The
proxy now forwards trusted `X-Forwarded-For`, `X-Forwarded-Host`, and
`X-Forwarded-Proto` values so backends retain client IP, original host, and
scheme context after proxying. Client-supplied versions are overwritten to
prevent spoofing. Because version 1 has no TLS listener, the forwarded scheme is
always `http`. Each proxied request also carries a validated client-provided or
generated `X-Request-Id` through every retry, the backend request, client
response, and structured completion log. Request IDs are intentionally excluded
from Prometheus labels to avoid unbounded metric cardinality. Request bodies are
limited to 1 MiB by default and the limit can be configured with
`--max-request-body-bytes`. A declared body above the limit is rejected with
`413 Payload Too Large` before a backend is selected or the body is buffered.
The connection is then closed so unread request bytes cannot be interpreted as
a subsequent request. `DELETE` shares that bounded-body path, preserves request
headers and bodies, and is never retried. It also cannot reach the local
administration or metrics endpoints, which remain read-only except for the
explicit backend actions handled by `POST`. Backend responses are limited to
1 MiB by default and configurable with `--max-response-body-bytes`. The proxy
reads at most one byte beyond the limit, closes the upstream connection, and
returns a controlled `502` without exposing a partial response to the client.
The proxy accepts only unambiguous `Content-Length` request framing. Requests
using `Transfer-Encoding`, duplicate content lengths, or a body on `GET` are
rejected and disconnected before backend selection, preventing unread bytes
from desynchronizing the persistent HTTP connection. The next checkpoint will
handle client disconnects without leaking backend accounting. Process shutdown
is now coordinated for both `SIGINT` and `SIGTERM`: the listener stops accepting
new traffic, the server waits for active request threads, the health checker is
stopped, and signal handlers are restored before exit.
