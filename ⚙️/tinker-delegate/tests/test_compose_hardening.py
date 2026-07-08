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

    def test_phala_playwright_sidecar_is_digest_pinned(self):
        block = _service_block(
            (ROOT / "docker-compose.all.phala.yaml").read_text(),
            "delegate-browser",
        )

        self.assertIn(
            "mcr.microsoft.com/playwright:v1.58.0-noble@sha256:",
            block,
        )

    def test_delegate_run_metadata_store_is_under_data_volume(self):
        for compose_name in (
            "docker-compose.yaml",
            "docker-compose.dstack.yaml",
            "docker-compose.all.yaml",
            "docker-compose.all.dstack.yaml",
            "docker-compose.all.phala.yaml",
        ):
            with self.subTest(compose_name=compose_name):
                block = _service_block((ROOT / compose_name).read_text(), "delegate")
                self.assertIn("TINKER_RUN_METADATA_STORE_PATH: /data/run_metadata.enc", block)

        for compose_name in (
            "docker-compose.dstack.yaml",
            "docker-compose.all.dstack.yaml",
            "docker-compose.all.phala.yaml",
        ):
            with self.subTest(compose_name=compose_name):
                block = _service_block((ROOT / compose_name).read_text(), "delegate")
                self.assertIn("TINKER_RUN_METADATA_KEY_PATH", block)
                self.assertIn("tinker/run_metadata", block)

    def test_delegate_funding_mode_defaults_to_manual_prefund(self):
        for compose_name in (
            "docker-compose.yaml",
            "docker-compose.dstack.yaml",
            "docker-compose.all.yaml",
            "docker-compose.all.dstack.yaml",
            "docker-compose.all.phala.yaml",
        ):
            with self.subTest(compose_name=compose_name):
                block = _service_block((ROOT / compose_name).read_text(), "delegate")
                self.assertIn("TINKER_FUNDING_MODE: ${TINKER_FUNDING_MODE:-manual_prefund}", block)


if __name__ == "__main__":
    unittest.main()
