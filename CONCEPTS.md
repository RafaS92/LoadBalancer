# Load balancer concepts: quick review

This file is a compact glossary of the main concepts demonstrated by this
project. Use it as a quick review before reading the detailed flow or presenting
the project.

## Core load-balancing concepts

- **Load balancer:** A system that distributes client requests across multiple backend servers.
- **Stable entry point:** The single address clients use instead of knowing every backend address.
- **Traffic distribution:** Sharing requests across multiple backends instead of overloading one server.
- **Availability:** Keeping the service usable when some backends are unavailable.
- **Scalability:** Increasing capacity by adding more backend instances.
- **Horizontal scaling:** Adding more servers rather than making one server larger.
- **Single point of failure:** A component whose failure can make the entire system unavailable.
- **Eligible backend:** A backend that is healthy, enabled, and allowed to receive a request.

## Proxy concepts

- **Proxy:** A program that receives information and passes it between two other programs.
- **Forward proxy:** A proxy that represents clients when they access another service.
- **Reverse proxy:** A proxy that represents servers and hides them behind one public address.
- **Upstream:** The backend side toward which the load balancer forwards a request.
- **Downstream:** The client side to which the load balancer returns a response.
- **Request forwarding:** Sending the client's method, path, headers, and body to a selected backend.
- **Response relay:** Returning the backend's status, safe headers, and body to the client.
- **API gateway:** A reverse proxy that commonly adds authentication, quotas, and API policies.
- **Service mesh:** Infrastructure that manages service-to-service traffic across many applications.

## Routing concepts

- **Routing policy:** The rule used to choose the next eligible backend.
- **Round robin:** Repeatedly rotating through eligible backends in order.
- **Routing cursor:** The saved position that identifies where the next round-robin search begins.
- **Modulo:** The operation that wraps the routing cursor back to the first backend.
- **Least connections:** Selecting the eligible backend with the fewest active requests.
- **Tie-breaking:** Using round-robin order when multiple backends are equally eligible.
- **Exclusion set:** Backends that must not be selected again during the same request.
- **Routing state:** Health, operator state, active counts, draining state, and cursor position.
- **Routing algorithm:** The focused calculation that chooses among eligible backends.
- **Backend pool:** The component that owns backend state and applies a routing policy.

## Concurrency concepts

- **Concurrency:** Multiple requests or background operations making progress during the same period.
- **Thread:** An independent execution path inside the load-balancer process.
- **Threaded HTTP server:** A server that can handle different client connections in separate threads.
- **Shared mutable state:** Data that multiple threads can read and change.
- **Race condition:** A bug caused by operations happening in an unexpected concurrent order.
- **Lock:** A guard that allows only one thread at a time to modify protected state.
- **Critical section:** The small block of code that runs while a lock is held.
- **Atomic operation:** A group of changes that other threads observe as one complete action.
- **Acquire:** Atomically selecting a backend and increasing its active-request count.
- **Release:** Decreasing a backend's active-request count when its request finishes.
- **Active-request accounting:** Tracking how many requests are currently assigned to each backend.
- **`finally` cleanup:** Code that releases resources whether an operation succeeds or fails.
- **Thread pool:** A managed collection of threads used here to probe backends concurrently.

## Snapshot and state concepts

- **Snapshot:** A consistent copy of state at one moment.
- **Consistent read:** A view whose related fields were copied from the same protected state.
- **Live state:** Current mutable information that may change while the system is running.
- **In-memory state:** Information stored only inside the current process.
- **Bounded history:** A fixed-size collection that discards older entries as new ones arrive.
- **Read model:** Data organized specifically for efficient display or querying.
- **State transition:** A change such as healthy to unhealthy or enabled to disabled.

## Health and resilience concepts

- **Health check:** A periodic test that asks whether a backend can serve traffic.
- **Health endpoint:** A backend route, such as `/health`, used for health probes.
- **Health probe:** One attempt to contact a backend's health endpoint.
- **Probe interval:** The time between health-check cycles.
- **Probe timeout:** The maximum time allowed for one health probe.
- **Failure threshold:** Consecutive failed probes required to mark a backend unhealthy.
- **Success threshold:** Consecutive successful probes required to restore a backend.
- **Flapping:** Rapid switching between healthy and unhealthy states.
- **Failure isolation:** Preventing one failed backend from stopping the complete service.
- **Recovery:** Returning a healthy backend to the eligible routing set.
- **Graceful degradation:** Continuing with reduced capacity when one backend fails.
- **Health transition event:** A record emitted when a backend crosses a health threshold.


## Retry and idempotency concepts

- **Retry:** An additional attempt after a previous backend attempt fails.
- **Retry policy:** The rules deciding which failures and methods may be attempted again.
- **Retry budget:** The maximum number of additional attempts allowed.
- **Retryable method:** A method considered safe enough for the configured retry behavior.
- **Retryable outcome:** A failure category for which another attempt is permitted.
- **Attempted backend:** A backend already tried and excluded from the next attempt.
- **Idempotency:** Repeating an operation has the same intended effect as doing it once.
- **Non-idempotent operation:** An operation that may create another side effect when repeated.
- **Idempotency key:** A durable application key used to prevent duplicate side effects.
- **Request ID:** A correlation identifier for tracing one request; it is not an idempotency key.
- **Retry safety:** Avoiding retries when the backend may already have performed unsafe work.

## Forwarded identity concepts

- **`X-Forwarded-For`:** The original client IP passed to the backend.
- **`X-Forwarded-Host`:** The host originally requested by the client.
- **`X-Forwarded-Proto`:** The original request scheme, such as `http`.
- **`X-Request-Id`:** The request correlation value carried through the proxy flow.
- **Header spoofing:** A client pretending to supply trusted proxy identity information.
- **Header sanitization:** Removing or replacing headers that should not be trusted or forwarded.

## Observability concepts

- **Observability:** Understanding internal system behavior through its external signals.
- **Operational event:** A typed fact describing something meaningful that happened.
- **Event sink:** A component that receives operational events.
- **Composite event sink:** A sink that forwards one event to several independent outputs.
- **Structured log:** A machine-readable log entry with stable named fields.
- **Correlation:** Connecting records from different components using a shared request ID.
- **Metric:** A numeric measurement aggregated across many events.
- **Prometheus:** The metrics format and monitoring ecosystem used by the project.
- **Metrics endpoint:** The `/metrics` route that exposes Prometheus measurements.
- **Counter:** A metric that only increases, such as total completed requests.
- **Gauge:** A metric that can increase or decrease, such as current backend health.
- **Histogram:** A metric that groups observed values into buckets.
- **Latency:** The time required to complete a request.
- **Average latency:** Total measured duration divided by the number of requests.
- **Tail latency:** The slower end of the latency distribution experienced by some requests.
- **Percentile:** A value below which a percentage of measurements falls.
- **Metric label:** A bounded dimension used to separate metric series.
- **Cardinality:** The number of unique label combinations stored by a metrics system.

## Clean architecture concepts

- **Clean architecture:** Organizing code so business rules do not depend on technical details.
- **Dependency direction:** Outer technical layers depend on inner business layers.
- **Domain layer:** Backend models, routing state, and routing policies.
- **Port:** A protocol describing what the application needs from another component.
- **Application layer:** Use cases coordinating routing, retries, health, administration, and queries.
- **Adapter:** A concrete translator between the application and a technical system.
- **Inbound adapter:** Code that receives input, such as the CLI or HTTP handler.
- **Outbound adapter:** Code that contacts another system, such as a backend transport.
- **Infrastructure:** Runtime details such as configuration, threads, signals, and servers.
- **Composition root:** The one place where concrete implementations are constructed and connected.
- **Bootstrap:** Starting the application by wiring all runtime dependencies.
- **Dependency injection:** Giving an object its dependencies instead of constructing them internally.
- **Protocol:** A Python structural interface describing required behavior.
- **DTO:** A simple data-transfer object used across an application boundary.
- **Separation of concerns:** Giving each component one focused responsibility.
- **Compatibility boundary:** A stable public interface protected while internals change.
- **Architecture test:** An automated check that rejects forbidden layer imports.

## Runtime and lifecycle concepts

- **Configuration:** Runtime values such as ports, backends, strategies, limits, and thresholds.
- **Default:** A standard value used when the operator provides no override.
- **Validation:** Rejecting invalid configuration or input before runtime work begins.
- **CLI:** The command-line interface used to start and configure the application.
- **Process:** A running instance of the load-balancer program.
- **Background worker:** A separate execution loop used for periodic health checks.
- **Signal:** An operating-system notification such as `SIGINT` or `SIGTERM`.
- **Graceful shutdown:** Stopping new work, waiting for active work, and closing resources in order.
- **Resource cleanup:** Closing servers, HTTP clients, threads, and connections after use.

## Docker concepts

- **Docker image:** A packaged, immutable template used to create containers.
- **Container:** An isolated running instance of an image.
- **Dockerfile:** Instructions for building a Docker image.
- **Docker Compose:** A definition and lifecycle tool for a multi-container application.
- **Compose service:** One container role defined in `compose.yaml`.
- **Compose application:** The complete group of related services started together.
- **Container health check:** A check Docker uses to report whether a container is healthy.
- **Service dependency:** A startup relationship between Compose services.
- **Docker network:** The private network used for communication between containers.
- **Published port:** A container port made available on the host computer.
- **Exposed port:** A container port available to other containers without host publication.
- **Container log:** Standard output and error captured from a container process.
- **Reproducible environment:** A consistent runtime created from versioned build definitions.

## Testing concepts

- **Unit test:** A fast test of one component in isolation.
- **Fake:** A small in-memory implementation used instead of a real dependency.
- **Integration test:** A test of multiple components working together.
- **End-to-end test:** A test through real external boundaries such as HTTP sockets.
- **Smoke test:** A focused check that the most important complete-system behavior works.
- **Characterization test:** A test that records existing behavior before refactoring it.
- **Contract test:** A test that verifies an adapter follows an expected boundary.
- **Concurrency test:** A test that checks behavior under simultaneous operations.
- **Failure test:** A test that verifies controlled behavior when a dependency fails.
- **Recovery test:** A test that verifies a restored backend rejoins the system.
- **Regression:** A previously working behavior that becomes broken after a change.
- **Test suite:** The complete collection of automated tests.
- **Linting:** Static checks for code quality and consistency.
- **Type checking:** Verifying that values match declared TypeScript types.
- **Production build:** Creating the optimized frontend files served by Nginx.
- **Continuous integration:** Automatically testing and building changes in a shared pipeline.

## Security and safety concepts

- **Input validation:** Checking untrusted values before using them.
- **Resource limit:** A configured boundary that prevents excessive resource use.
- **Sensitive-data logging:** Accidentally recording secrets or private information in logs.
- **Least privilege:** Giving a process only the capabilities it needs.
- **Unauthenticated endpoint:** A route that anyone with network access can call.
- **Local-only listener:** A service bound to the local computer rather than the public network.
- **Attack surface:** The set of exposed behaviors that an attacker could attempt to misuse.

## One-sentence project review

> This project is a synchronous HTTP reverse proxy that safely selects healthy
> backends, coordinates concurrent state, applies conservative retries,
> forwards bounded traffic, and exposes its behavior through logs, metrics, and
> a dashboard.
