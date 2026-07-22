import unittest
from threading import Event, Thread

from load_balancer.app import project_status, serve_until_shutdown


class ProjectStatusTest(unittest.TestCase):
    def test_reports_that_project_is_ready(self) -> None:
        self.assertEqual(project_status(), "Load balancer project is ready")


class GracefulShutdownTest(unittest.TestCase):
    def test_stops_server_and_health_checker_in_order(self) -> None:
        calls: list[str] = []
        server_started = Event()
        server_stopped = Event()
        shutdown_requested = Event()

        class FakeServer:
            def serve_forever(self) -> None:
                calls.append("server_started")
                server_started.set()
                server_stopped.wait(timeout=1)

            def shutdown(self) -> None:
                calls.append("server_shutdown")
                server_stopped.set()

            def server_close(self) -> None:
                calls.append("server_closed")

        class FakeHealthChecker:
            def start(self) -> None:
                calls.append("health_started")

            def stop(self) -> None:
                calls.append("health_stopped")

        def trigger_shutdown() -> None:
            self.assertTrue(server_started.wait(timeout=1))
            shutdown_requested.set()

        trigger = Thread(target=trigger_shutdown)
        trigger.start()
        serve_until_shutdown(
            FakeServer(),  # type: ignore[arg-type]
            FakeHealthChecker(),  # type: ignore[arg-type]
            shutdown_event=shutdown_requested,
            install_signal_handlers=False,
        )
        trigger.join()

        self.assertEqual(
            calls,
            [
                "health_started",
                "server_started",
                "server_shutdown",
                "server_closed",
                "health_stopped",
            ],
        )


if __name__ == "__main__":
    unittest.main()
