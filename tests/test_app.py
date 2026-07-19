import unittest

from load_balancer.app import project_status


class ProjectStatusTest(unittest.TestCase):
    def test_reports_that_project_is_ready(self) -> None:
        self.assertEqual(project_status(), "Load balancer project is ready")


if __name__ == "__main__":
    unittest.main()
