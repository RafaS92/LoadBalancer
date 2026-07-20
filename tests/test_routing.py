from concurrent.futures import ThreadPoolExecutor

import pytest

from load_balancer.routing import Backend, LeastConnectionsPool, RoundRobinPool


@pytest.fixture
def backends() -> list[Backend]:
    return [
        Backend("backend-a", "http://127.0.0.1:9001"),
        Backend("backend-b", "http://127.0.0.1:9002"),
        Backend("backend-c", "http://127.0.0.1:9003"),
    ]


def test_selects_backends_in_round_robin_order(backends: list[Backend]) -> None:
    pool = RoundRobinPool(backends)

    selected = [pool.choose() for _ in range(7)]

    assert selected == [
        backends[0],
        backends[1],
        backends[2],
        backends[0],
        backends[1],
        backends[2],
        backends[0],
    ]


def test_skips_unhealthy_backends(backends: list[Backend]) -> None:
    pool = RoundRobinPool(backends)
    pool.set_health("backend-b", healthy=False)

    assert [pool.choose() for _ in range(4)] == [
        backends[0],
        backends[2],
        backends[0],
        backends[2],
    ]


def test_backend_can_rejoin_rotation_after_recovery(backends: list[Backend]) -> None:
    pool = RoundRobinPool(backends)
    pool.set_health("backend-b", healthy=False)

    assert pool.choose() == backends[0]
    pool.set_health("backend-b", healthy=True)

    assert [pool.choose() for _ in range(3)] == backends[1:3] + backends[:1]


def test_returns_none_when_all_backends_are_unhealthy(
    backends: list[Backend],
) -> None:
    pool = RoundRobinPool(backends)
    for backend in backends:
        pool.set_health(backend.name, healthy=False)

    assert pool.choose() is None


def test_rejects_an_empty_pool() -> None:
    with pytest.raises(ValueError, match="at least one backend"):
        RoundRobinPool([])


def test_rejects_duplicate_backend_names() -> None:
    with pytest.raises(ValueError, match="names must be unique"):
        RoundRobinPool(
            [
                Backend("api", "http://127.0.0.1:9001"),
                Backend("api", "http://127.0.0.1:9002"),
            ]
        )


def test_rejects_health_updates_for_unknown_backends(backends: list[Backend]) -> None:
    pool = RoundRobinPool(backends)

    with pytest.raises(KeyError, match="unknown backend: missing"):
        pool.set_health("missing", healthy=False)


def test_snapshot_is_consistent_and_ordered(backends: list[Backend]) -> None:
    pool = RoundRobinPool(backends)
    pool.set_health("backend-b", healthy=False)

    snapshot = pool.snapshot()

    assert [status.backend for status in snapshot] == backends
    assert [status.healthy for status in snapshot] == [True, False, True]
    assert [status.enabled for status in snapshot] == [True, True, True]
    assert [status.active_requests for status in snapshot] == [0, 0, 0]


def test_acquire_and_release_track_active_requests(backends: list[Backend]) -> None:
    pool = RoundRobinPool(backends)

    first = pool.acquire()
    second = pool.acquire()

    assert first == backends[0]
    assert second == backends[1]
    assert [status.active_requests for status in pool.snapshot()] == [1, 1, 0]

    pool.release("backend-a")
    pool.release("backend-b")
    assert [status.active_requests for status in pool.snapshot()] == [0, 0, 0]


def test_rejects_release_without_matching_acquire(backends: list[Backend]) -> None:
    pool = RoundRobinPool(backends)

    with pytest.raises(RuntimeError, match="no active requests: backend-a"):
        pool.release("backend-a")


def test_disabled_backend_stays_out_of_rotation_after_health_recovery(
    backends: list[Backend],
) -> None:
    pool = RoundRobinPool(backends)
    pool.set_enabled("backend-b", enabled=False)

    assert [pool.choose() for _ in range(4)] == [
        backends[0],
        backends[2],
        backends[0],
        backends[2],
    ]

    pool.set_health("backend-b", healthy=False)
    pool.set_health("backend-b", healthy=True)
    assert pool.snapshot()[1].enabled is False
    assert [pool.choose() for _ in range(2)] == [backends[0], backends[2]]


def test_least_connections_selects_the_least_busy_backend(
    backends: list[Backend],
) -> None:
    pool = LeastConnectionsPool(backends)

    assert pool.acquire() == backends[0]
    assert pool.acquire() == backends[1]
    assert pool.acquire() == backends[2]
    assert pool.acquire() == backends[0]
    pool.release("backend-b")

    assert pool.acquire() == backends[1]


def test_least_connections_uses_round_robin_to_break_ties(
    backends: list[Backend],
) -> None:
    pool = LeastConnectionsPool(backends)

    assert pool.acquire() == backends[0]
    pool.release("backend-a")

    assert pool.acquire() == backends[1]


def test_least_connections_skips_unhealthy_backend(
    backends: list[Backend],
) -> None:
    pool = LeastConnectionsPool(backends)
    pool.set_health("backend-a", healthy=False)

    assert pool.acquire() == backends[1]
    assert pool.acquire() == backends[2]


def test_concurrent_selection_preserves_an_even_distribution(
    backends: list[Backend],
) -> None:
    pool = RoundRobinPool(backends)

    with ThreadPoolExecutor(max_workers=12) as executor:
        selected = list(executor.map(lambda _: pool.choose(), range(300)))

    assert selected.count(backends[0]) == 100
    assert selected.count(backends[1]) == 100
    assert selected.count(backends[2]) == 100
