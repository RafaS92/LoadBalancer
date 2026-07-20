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

The application now accepts HTTP `GET` requests on `127.0.0.1:8080`, selects a
healthy backend with the thread-safe round-robin pool, and forwards the path and
query string to demonstration backends on ports 9001 through 9003. It preserves
the backend status, end-to-end headers, and body, returns `503` when the pool is
exhausted, and returns `502` when a selected backend cannot be reached.

This checkpoint intentionally supports only `GET` and buffers each response in
memory. The next checkpoint will add request-body forwarding for methods such as
`POST` while keeping retry behavior out of scope until its safety rules are
explicit.
