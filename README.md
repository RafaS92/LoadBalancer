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

The application accepts HTTP `GET` and `POST` requests and can now be configured
without editing source code. With no arguments it listens on `127.0.0.1:8080`
and uses demonstration backends on ports 9001 through 9003.

Custom addresses use repeatable `--backend` arguments:

```shell
load-balancer --listen-host 0.0.0.0 --listen-port 8088 \
  --strategy least-connections \
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
traffic listener, so it should not be exposed publicly. This checkpoint still
performs probes sequentially and buffers request and response bodies in memory.
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
configurable. The next checkpoint will expose health transitions through
structured logs and metrics so operators can see why routing state changed.
