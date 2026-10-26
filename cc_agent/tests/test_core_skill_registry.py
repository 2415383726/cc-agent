import json
import tempfile
import unittest
from pathlib import Path

from cc_agent.core.skill_registry import SkillRegistry
from cc_agent.core.internal_tools import InternalToolExecutor
from cc_agent.core.messages import AgentState
from cc_agent.core.skills import list_skills, render_skill
from cc_agent.core.skill_runtime import (
    SkillRuntime,
)
from cc_agent.core.runtime import _prompt_skill_user_message


class SkillRegistryTests(unittest.TestCase):
    def test_scans_skill_frontmatter_metadata_and_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo"
            (skill_dir / "references").mkdir(parents=True)
            (skill_dir / "assets").mkdir()
            (skill_dir / "scripts").mkdir()
            (skill_dir / "references" / "guide.md").write_text("reference", encoding="utf-8")
            (skill_dir / "assets" / "sample.txt").write_text("asset", encoding="utf-8")
            (skill_dir / "scripts" / "run.ps1").write_text("throw 'must not run'", encoding="utf-8")
            (skill_dir / "SKILL.md").write_text(
                """---
name: demo-skill
description: Demo skill
allowed-tools: [Read, Write]
argument-hint: TOPIC
when_to_use: Use for demo requests
version: 1.2.3
model: fast
context:
  - references/guide.md
  - assets/sample.txt
user-invocable: false
disable-model-invocation: true
unknown-field: kept
---
Skill body for {{topic}} with $ARGUMENTS.
""",
                encoding="utf-8",
            )

            snapshot = SkillRegistry(Path(tmp)).load()

        self.assertEqual(snapshot.warnings, [])
        self.assertEqual(len(snapshot.skills), 1)
        skill = snapshot.skills[0]
        self.assertEqual(skill["id"], "demo")
        self.assertEqual(skill["name"], "demo")
        self.assertEqual(skill["display_name"], "demo-skill")
        self.assertEqual(skill["description"], "Demo skill")
        self.assertEqual(skill["allowed_tools"], ["Read", "Write"])
        self.assertEqual(skill["argument_hint"], "TOPIC")
        self.assertEqual(skill["when_to_use"], "Use for demo requests")
        self.assertEqual(skill["version"], "1.2.3")
        self.assertEqual(skill["model"], "fast")
        self.assertEqual(skill["context"], ["references/guide.md", "assets/sample.txt"])
        self.assertFalse(skill["user_invocable"])
        self.assertTrue(skill["disable_model_invocation"])
        self.assertEqual(skill["metadata"]["unknown-field"], "kept")
        self.assertEqual(skill["source"], "bundled")
        self.assertEqual(skill["resources"]["references"], ["references/guide.md"])
        self.assertEqual(skill["resources"]["assets"], ["assets/sample.txt"])
        self.assertEqual(skill["resources"]["scripts"], ["scripts/run.ps1"])
        self.assertIn("Skill body for", skill["body"])

    def test_standard_skill_directory_uses_directory_id_and_optional_display_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "doc-maker"
            (skill_dir / "agents").mkdir(parents=True)
            (skill_dir / "agents" / "openai.yaml").write_text(
                """display_name: Document Maker
short_description: Build documents
default_prompt: Make a document
""",
                encoding="utf-8",
            )
            (skill_dir / "SKILL.md").write_text(
                """---
name: "Document Maker"
description: "Create document artifacts."
allowed-tools:
  - Read
  - Write
argument-hint: TOPIC
metadata:
  owner: docs
shell: powershell
---
Build documents for $ARGUMENTS[0].
""",
                encoding="utf-8",
            )

            snapshot = SkillRegistry(Path(tmp)).load()

        self.assertEqual(snapshot.warnings, [])
        skill = snapshot.skills[0]
        self.assertEqual(skill["id"], "doc-maker")
        self.assertEqual(skill["name"], "doc-maker")
        self.assertEqual(skill["display_name"], "Document Maker")
        self.assertEqual(skill["allowed_tools"], ["Read", "Write"])
        self.assertEqual(skill["argument_hint"], "TOPIC")
        self.assertEqual(skill["shell"], "powershell")
        self.assertEqual(skill["metadata"]["metadata"]["owner"], "docs")
        self.assertEqual(skill["ui"]["display_name"], "Document Maker")

    def test_invalid_skill_without_frontmatter_is_skipped_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "invalid"
            skill_dir.mkdir()
            skill_path = skill_dir / "SKILL.md"
            skill_path.write_text("No frontmatter here.", encoding="utf-8")

            snapshot = SkillRegistry(Path(tmp)).load()

        self.assertEqual(snapshot.skills, [])
        self.assertEqual(len(snapshot.warnings), 1)
        self.assertEqual(snapshot.warnings[0]["path"], str(skill_path))
        self.assertIn("frontmatter", snapshot.warnings[0]["reason"])

    def test_list_skills_omits_body(self):
        skills = [
            {
                "name": "demo",
                "description": "Demo",
                "body": "secret prompt",
                "allowed_tools": ["Read"],
                "argument_hint": "topic",
                "context": ["references/a.md"],
                "resources": {"references": ["references/a.md"], "assets": [], "scripts": []},
                "source": "bundled",
            }
        ]

        compact = list_skills(skills)

        self.assertEqual(compact[0]["name"], "demo")
        self.assertEqual(compact[0]["allowed_tools"], ["Read"])
        self.assertEqual(compact[0]["argument_hint"], "topic")
        self.assertNotIn("body", compact[0])

    def test_render_skill_substitutes_arguments_and_includes_resource_index(self):
        skills = [
            {
                "name": "demo",
                "description": "Demo",
                "body": "Explain {{topic}} using $ARGUMENTS.",
                "resources": {
                    "references": ["references/guide.md"],
                    "assets": [],
                    "scripts": ["scripts/run.ps1"],
                },
            }
        ]

        rendered = render_skill(skills, "demo", {"topic": "registries"})

        self.assertIn("Explain registries using", rendered)
        self.assertIn(json.dumps({"topic": "registries"}, ensure_ascii=False), rendered)
        self.assertIn("Resource index:", rendered)
        self.assertIn("- references:", rendered)
        self.assertIn("  - references/guide.md", rendered)
        self.assertIn("- scripts:", rendered)
        self.assertIn("  - scripts/run.ps1", rendered)
        self.assertIn("Scripts are not executed automatically.", rendered)

    def test_render_skill_supports_standard_argument_placeholders(self):
        skills = [
            {
                "name": "demo",
                "description": "Demo",
                "body": "Topic=$1; Second=$ARGUMENTS[1]; Raw=$ARGUMENTS; Named={{mode}}.",
                "resources": {},
            }
        ]

        rendered = render_skill(skills, "demo", {"_raw": "alpha beta", "_argv": ["alpha", "beta"], "mode": "fast"})

        self.assertIn("Topic=alpha", rendered)
        self.assertIn("Second=beta", rendered)
        self.assertIn("Raw=alpha beta", rendered)
        self.assertIn("Named=fast", rendered)

    def test_render_skill_appends_arguments_when_body_does_not_reference_them(self):
        rendered = render_skill(
            [{"name": "demo", "description": "Demo", "body": "Do the work.", "resources": {}}],
            "demo",
            {"_raw": "make slides", "_argv": ["make", "slides"]},
        )

        self.assertIn("Do the work.", rendered)
        self.assertIn("ARGUMENTS:", rendered)
        self.assertIn("make slides", rendered)

    def test_render_skill_includes_resource_index_without_eager_resource_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo"
            (skill_dir / "references").mkdir(parents=True)
            (skill_dir / "assets").mkdir()
            (skill_dir / "scripts").mkdir()
            (skill_dir / "references" / "guide.md").write_text("Use this reference detail.", encoding="utf-8")
            (skill_dir / "assets" / "template.md").write_text("Template asset detail.", encoding="utf-8")
            (skill_dir / "assets" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            (skill_dir / "scripts" / "danger.py").write_text("print('must not be read or executed')", encoding="utf-8")
            skills = [
                {
                    "name": "demo",
                    "description": "Demo",
                    "body": "Use bundled resources.",
                    "path": str(skill_dir / "SKILL.md"),
                    "resources": {
                        "references": ["references/guide.md"],
                        "assets": ["assets/logo.png", "assets/template.md"],
                        "scripts": ["scripts/danger.py"],
                    },
                }
            ]

            rendered = render_skill(skills, "demo", {})

        self.assertIn("Resource index:", rendered)
        self.assertIn("references/guide.md", rendered)
        self.assertIn("assets/template.md", rendered)
        self.assertNotIn("Bundled resource content:", rendered)
        self.assertNotIn("Use this reference detail.", rendered)
        self.assertNotIn("Template asset detail.", rendered)
        self.assertNotIn("must not be read or executed", rendered)

    def test_render_skill_rejects_resource_paths_outside_skill_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo"
            skill_dir.mkdir()
            skills = [
                {
                    "name": "demo",
                    "description": "Demo",
                    "body": "Use bundled resources.",
                    "path": str(skill_dir / "SKILL.md"),
                    "resources": {
                        "references": ["../secret.txt"],
                        "assets": [],
                        "scripts": [],
                    },
                }
            ]

            rendered = render_skill(skills, "demo", {})

        self.assertIn("Resource index:", rendered)
        self.assertIn("../secret.txt", rendered)
        self.assertNotIn("not loaded", rendered)

    def test_skill_runtime_reads_resources_and_rejects_outside_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo"
            (skill_dir / "references").mkdir(parents=True)
            (skill_dir / "references" / "guide.md").write_text("reference detail", encoding="utf-8")
            skill = {"name": "demo", "path": str(skill_dir / "SKILL.md")}
            runtime = SkillRuntime()

            ok = runtime.read_resource(skill, "references/guide.md")
            prefixed = runtime.read_resource(skill, "files/demo/references\\guide.md")
            bad = runtime.read_resource(skill, "../secret.txt")

        self.assertFalse(ok.is_error)
        self.assertIn("reference detail", ok.llm_observation)
        self.assertFalse(prefixed.is_error)
        self.assertIn("reference detail", prefixed.llm_observation)
        self.assertTrue(bad.is_error)
        self.assertIn("outside skill directory", bad.llm_observation)

    def test_skill_runtime_rejects_resource_reads_without_skill_path(self):
        runtime = SkillRuntime()

        result = runtime.read_resource({"name": "inline"}, "cc_agent/manifest.yaml")

        self.assertTrue(result.is_error)
        self.assertIn("no resource directory", result.llm_observation)


    def test_skill_tool_does_not_execute_dynamic_shell_blocks(self):
        state = AgentState(
            skills=[
                {
                    "name": "demo",
                    "description": "Demo",
                    "body": "Before\n!`Write-Output SHOULD_NOT_RUN`\nAfter",
                    "resources": {},
                    "shell": "powershell",
                }
            ]
        )

        result = InternalToolExecutor(state).execute("Skill", {"name": "demo"}, "call_skill")

        self.assertFalse(result.is_error, result.llm_observation)
        injected = result.metadata["injected_message"]
        self.assertIn("!`Write-Output SHOULD_NOT_RUN`", injected)
        self.assertNotIn("Before\nSHOULD_NOT_RUN\nAfter", injected)

    def test_slash_prompt_skill_does_not_execute_dynamic_shell_blocks(self):
        injected = _prompt_skill_user_message(
            {
                "name": "demo",
                "description": "Demo",
                "body": "Before\n!`Write-Output SHOULD_NOT_RUN`\nAfter",
                "resources": {},
                "shell": "powershell",
            },
            "",
        )

        self.assertIn("!`Write-Output SHOULD_NOT_RUN`", injected)
        self.assertNotIn("Before\nSHOULD_NOT_RUN\nAfter", injected)


    def test_bundled_skills_include_default_skills(self):
        from cc_agent.core.skills import load_bundled_skills

        names = {skill["name"] for skill in load_bundled_skills()}

        self.assertEqual(names, {"answers-charts", "answers-ui"})

    def test_answers_charts_skill_is_bundled_with_reference_and_ui_metadata(self):
        skills_root = Path(__file__).resolve().parent.parent / "skills"
        snapshot = SkillRegistry(skills_root).load()
        skill = next(item for item in snapshot.skills if item["name"] == "answers-charts")

        self.assertEqual(snapshot.warnings, [])
        self.assertIn("cc-chart", skill["body"])
        self.assertEqual(skill["resources"]["references"], [])
        self.assertEqual(skill["resources"]["assets"], [])
        self.assertEqual(skill["resources"]["scripts"], [])
        self.assertEqual(skill["ui"]["interface"]["display_name"], "Answers Charts")
        self.assertTrue(skill["ui"]["policy"]["allow_implicit_invocation"])

    def test_answers_ui_skill_is_bundled_with_protocols_and_ui_metadata(self):
        skills_root = Path(__file__).resolve().parent.parent / "skills"
        snapshot = SkillRegistry(skills_root).load()
        skill = next(item for item in snapshot.skills if item["name"] == "answers-ui")

        self.assertEqual(snapshot.warnings, [])
        for protocol in ("cc-record", "cc-table", "cc-compare", "cc-timeline"):
            self.assertIn(protocol, skill["body"])
        self.assertIn("Never wrap these protocols in the removed `cc-ui` envelope", skill["body"])
        self.assertIn("UserPrompt.fields", skill["body"])
        self.assertIn("daterange", skill["body"])
        self.assertIn("structured `values`", skill["body"])
        self.assertEqual(skill["resources"]["references"], [])
        self.assertEqual(skill["resources"]["assets"], [])
        self.assertEqual(skill["resources"]["scripts"], [])
        self.assertEqual(skill["ui"]["interface"]["display_name"], "Answers UI")
        self.assertTrue(skill["ui"]["policy"]["allow_implicit_invocation"])

    def test_package_builder_does_not_skip_bundled_skills(self):
        from cc_agent.scripts.build_offline_package import should_skip

        self.assertFalse(should_skip(Path("skills/brainstorm/SKILL.md"), "all"))
        self.assertFalse(should_skip(Path("skills/meeting-notes/SKILL.md"), "amd64"))

    def test_package_builder_skips_local_virtualenv(self):
        from cc_agent.scripts.build_offline_package import should_skip

        self.assertTrue(should_skip(Path(".venv/Lib/site-packages/pydantic/__init__.py"), "all"))
        self.assertTrue(should_skip(Path(".venv/Lib/site-packages/pydantic_core/_pydantic_core.cp312-win_amd64.pyd"), "amd64"))


if __name__ == "__main__":
    unittest.main()
