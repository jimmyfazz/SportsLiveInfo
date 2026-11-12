"""Static Home Assistant App packaging checks; not a replacement for HAOS install."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "sportsliveinfo"

class HaosPackagingTests(unittest.TestCase):
    def test_custom_supervisor_image_labels_and_build_args(self):
        dockerfile = (APP / "Dockerfile").read_text()
        for value in ("ARG BUILD_VERSION=", "ARG BUILD_ARCH=",
                      'io.hass.version="${BUILD_VERSION}"',
                      'io.hass.type="app"',
                      'io.hass.arch="${BUILD_ARCH}"'):
            self.assertIn(value, dockerfile)

    def test_app_store_and_private_ingress_layout(self):
        self.assertTrue((ROOT / "repository.yaml").is_file())
        config = (APP / "config.yaml").read_text()
        self.assertIn("slug: sportsliveinfo", config)
        self.assertIn("ingress: true", config)
        self.assertIn("ingress_port: 8099", config)
        self.assertIn("panel_admin: true", config)
        self.assertIn("stage: experimental", config)
        self.assertNotIn("\nports:", config)
        for file in ("Dockerfile", "DOCS.md", "icon.png", "logo.png"):
            self.assertTrue((APP / file).is_file(), file)

if __name__ == "__main__":
    unittest.main()
