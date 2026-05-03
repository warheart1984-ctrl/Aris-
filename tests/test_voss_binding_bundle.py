from __future__ import annotations

import unittest

from evolving_ai.voss_binding import load_governance_bundle
from evolving_ai.voss_binding import voss_binary, voss_binding


class VossBindingBundleTests(unittest.TestCase):
    def test_voss_binding_bundle_loads(self) -> None:
        bundle = load_governance_bundle()
        self.assertEqual(bundle["suite"]["name"], "AAIS Governance Artifacts")
        self.assertEqual(bundle["artifacts"][0]["document_id"], "AAIS-VB-Λ-001")

    def test_voss_binding_modules_import(self) -> None:
        self.assertTrue(hasattr(voss_binary, "VMState"))
        self.assertTrue(hasattr(voss_binding, "CycleContext"))


if __name__ == "__main__":
    unittest.main()
