from pathlib import Path
import re
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DockerfileAgentExtraTest(unittest.TestCase):
    def test_delegate_image_installs_tinker_agent_extra_from_lockfile(self):
        dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertRegex(dockerfile, r"COPY\s+pyproject\.toml\s+uv\.lock\s+\./")
        self.assertRegex(dockerfile, r"uv\s+sync\b")
        self.assertIn("--frozen", dockerfile)
        self.assertIn("--extra agent", dockerfile)

    def test_delegate_image_does_not_install_base_package_only(self):
        dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
        base_only_install = re.compile(r"uv\s+pip\s+install\s+\.(?:\s|&&)")

        self.assertIsNone(base_only_install.search(dockerfile))


if __name__ == "__main__":
    unittest.main()
