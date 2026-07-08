from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _service_block(compose_text: str, service_name: str) -> str:
    lines = compose_text.splitlines()
    start = next(index for index, line in enumerate(lines) if line == f"  {service_name}:")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            end = index
            break
    return "\n".join(lines[start:end])


class ComposeHardeningTest(unittest.TestCase):
    def assert_service_disables_core_dumps(self, compose_name: str, service_name: str):
        compose = (ROOT / compose_name).read_text()
        block = _service_block(compose, service_name)

        self.assertIn("ulimits:", block)
        self.assertIn("core: 0", block)

    def test_local_delegate_compose_disables_core_dumps(self):
        self.assert_service_disables_core_dumps("docker-compose.yaml", "delegate")

    def test_all_in_one_local_compose_disables_core_dumps(self):
        for service in ("neko", "oracle", "delegate"):
            self.assert_service_disables_core_dumps("docker-compose.all.yaml", service)

    def test_phala_compose_disables_core_dumps(self):
        for service in ("neko", "oracle", "delegate", "delegate-browser"):
            self.assert_service_disables_core_dumps("docker-compose.all.phala.yaml", service)


if __name__ == "__main__":
    unittest.main()
