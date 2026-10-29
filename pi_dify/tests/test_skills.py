from __future__ import annotations

import unittest

from _support import ROOT  # noqa: F401

from pi_agent.errors import PiError
from pi_agent.skills import SkillCatalog, normalize_skill_path

YAML = """
skills:
  - name: refund-policy
    description: Refund rules for support agents
    content: |
      Always check the order date first.
      Refunds are allowed within 30 days.
    requires_tools: [lookup_order]
    resources:
      guide.md: |
        Refund guide line one.
        Refund guide line two.
      nested/extra.txt: Extra details.
  - name: disabled-skill
    description: Not enabled
    content: Should not appear.
    enabled: false
"""


class SkillCatalogTests(unittest.TestCase):
    def test_eligibility_requires_configured_tools(self) -> None:
        catalog = SkillCatalog.load(app_yaml=YAML, available_tools={"lookup_order"})
        self.assertEqual(catalog.eligible_names(), {"refund-policy"})
        catalog_without = SkillCatalog.load(app_yaml=YAML, available_tools=set())
        self.assertEqual(catalog_without.eligible_names(), set())

    def test_activation_includes_body_and_user_gate(self) -> None:
        catalog = SkillCatalog.load(app_yaml=YAML, available_tools={"lookup_order"})
        activation = catalog.activate("refund-policy", activated_by="user")
        self.assertIn("Always check the order date", activation.text)
        self.assertEqual(activation.skill.source, "app")
        with self.assertRaises(PiError):
            catalog.activate("missing", activated_by="user")

    def test_resource_reads_are_bounded_and_paged(self) -> None:
        catalog = SkillCatalog.load(app_yaml=YAML, available_tools={"lookup_order"})
        first = catalog.read("refund-policy", "guide.md", offset=0, limit=10)
        self.assertEqual(first.text, "Refund gui")
        self.assertEqual(first.next_offset, 10)
        second = catalog.read("refund-policy", "guide.md", offset=first.next_offset, limit=10)
        self.assertEqual(second.text, "de line on")
        self.assertIsNotNone(second.total_chars)

    def test_path_traversal_is_rejected(self) -> None:
        catalog = SkillCatalog.load(app_yaml=YAML, available_tools={"lookup_order"})
        for path in ["../secret", "/etc/passwd", "a/../../b", ""]:
            with self.assertRaises(PiError):
                catalog.read("refund-policy", path)

    def test_normalize_path(self) -> None:
        self.assertEqual(normalize_skill_path("a/b.md"), "a/b.md")
        with self.assertRaises(PiError):
            normalize_skill_path("a\\..\\b")

    def test_system_section_only_lists_eligible_skills(self) -> None:
        catalog = SkillCatalog.load(app_yaml=YAML, available_tools={"lookup_order"})
        section = catalog.system_section()
        self.assertIn("refund-policy", section)
        self.assertNotIn("disabled-skill", section)
        self.assertNotIn("Refund are allowed", section)


if __name__ == "__main__":
    unittest.main()
