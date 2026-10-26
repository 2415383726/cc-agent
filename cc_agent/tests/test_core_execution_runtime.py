import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from cc_agent.core.config import AgentRunConfig
from cc_agent.core.internal_tools import InternalToolExecutor
from cc_agent.core.messages import AgentState
from cc_agent.core.prompt_builder import PromptBuilder
from cc_agent.core.python_runtime import PythonCodeRuntime
from cc_agent.core.skill_runtime import SkillRuntime
from cc_agent.core.tool_registry import ToolRegistry
from cc_agent.core.workspace import WorkspaceSession
from cc_agent.tests.test_core_workspace import FakeStorage, scope, storage_config


class ExecutionRuntimeToolTests(unittest.TestCase):
    def test_dify_only_model_tools_hide_workspace_and_script_tools(self):
        names = {tool["name"] for tool in ToolRegistry.create().prompt_tools()}

        self.assertIn("Skill", names)
        self.assertIn("MemorySave", names)
        self.assertIn("TaskCreate", names)
        self.assertIn("UserPrompt", names)
        self.assertNotIn("AskUserQuestion", names)
        self.assertNotIn("run_python", names)
        self.assertNotIn("SkillRunScript", names)
        self.assertNotIn("SkillInstall", names)
        self.assertNotIn("SkillRemove", names)
        self.assertNotIn("list_files", names)
        self.assertNotIn("bash", names)

    def test_dify_native_model_tools_hide_user_prompt_interrupt_tool(self):
        names = {tool["name"] for tool in ToolRegistry.create(output_protocol="dify_native").prompt_tools()}

        self.assertNotIn("UserPrompt", names)
        self.assertNotIn("AskUserQuestion", names)
        self.assertIn("TaskCreate", names)

    def test_minio_model_tools_expose_python_and_skill_script_but_not_bash(self):
        names = {tool["name"] for tool in ToolRegistry.create(capability_mode="minio").prompt_tools()}

        self.assertIn("run_python", names)
        self.assertIn("SkillRunScript", names)
        self.assertIn("SkillInstall", names)
        self.assertIn("SkillRemove", names)
        self.assertIn("list_files", names)
        self.assertNotIn("bash", names)

    def test_dify_only_prompt_does_not_inject_workspace_even_if_state_has_one(self):
        storage = FakeStorage()
        session = WorkspaceSession(
            config=storage_config(),
            scope=scope(),
            storage=storage,
            dify_files=[{"name": "input.csv", "mime_type": "text/csv", "content": "value\n1\n"}],
        ).open()

        prompt = PromptBuilder(AgentRunConfig(query="q"), AgentState(workspace=session)).system_prompt()

        self.assertNotIn("Workspace files", prompt)
        self.assertNotIn("run_python", prompt)
        self.assertNotIn("CC_AGENT_FILES_JSON", prompt)

    def test_minio_workspace_prompt_describes_python_runner_not_bash(self):
        storage = FakeStorage()
        session = WorkspaceSession(
            config=storage_config(),
            scope=scope(),
            storage=storage,
            dify_files=[{"name": "input.csv", "mime_type": "text/csv", "content": "value\n1\n"}],
        ).open()

        prompt = PromptBuilder(
            AgentRunConfig(query="q", capability_mode="minio"),
            AgentState(workspace=session),
        ).system_prompt()

        self.assertIn("run_python", prompt)
        self.assertIn("CC_AGENT_FILES_JSON", prompt)
        self.assertNotIn("Bash tool", prompt)
        self.assertNotIn("use bash", prompt.lower())

    def test_run_python_sees_all_workspace_files_when_inputs_are_omitted(self):
        storage = FakeStorage()
        session = WorkspaceSession(
            config=storage_config(),
            scope=scope(),
            storage=storage,
            dify_files=[{"name": "numbers.csv", "mime_type": "text/csv", "content": "value\n2\n3\n"}],
        ).open()
        session.write_text_output("notes.md", "# Notes\n", mime_type="text/markdown")
        code = "\n".join(
            [
                "import csv, json, os",
                "from pathlib import Path",
                "files = json.loads(os.environ['CC_AGENT_FILES_JSON'])",
                "names = sorted(item['name'] for item in files)",
                "total = 0",
                "for item in files:",
                "    if item['name'] == 'numbers.csv':",
                "        with open(item['local_path'], newline='', encoding='utf-8') as handle:",
                "            for row in csv.DictReader(handle):",
                "                total += int(row['value'])",
                "out = Path(os.environ['CC_AGENT_OUTPUTS_DIR']) / 'summary.json'",
                "out.write_text(json.dumps({'names': names, 'total': total}), encoding='utf-8')",
                "print(json.dumps({'names': names, 'total': total}))",
            ]
        )

        result = PythonCodeRuntime(workspace=session).run(code)

        self.assertFalse(result.is_error, result.llm_observation)
        self.assertIn('"numbers.csv"', result.metadata["stdout"])
        self.assertEqual(result.metadata["artifacts"][0]["name"], "summary.json")
        session.commit()
        saved_manifest = storage.get_json(scope().manifest_key)
        self.assertEqual(saved_manifest["files"][-1]["path"], "outputs/summary.json")

    def test_run_python_environment_does_not_include_storage_secrets(self):
        storage = FakeStorage()
        session = WorkspaceSession(config=storage_config(), scope=scope(), storage=storage).open()
        os.environ["MINIO_SECRET_KEY"] = "must-not-leak"
        try:
            result = PythonCodeRuntime(workspace=session).run(
                "import os\nprint('MINIO_SECRET_KEY' in os.environ)"
            )
        finally:
            os.environ.pop("MINIO_SECRET_KEY", None)

        self.assertFalse(result.is_error, result.llm_observation)
        self.assertIn("False", result.metadata["stdout"])

    def test_run_python_registers_modified_output_artifacts(self):
        storage = FakeStorage()
        session = WorkspaceSession(config=storage_config(), scope=scope(), storage=storage).open()
        session.write_text_output("report.md", "old", mime_type="text/markdown")

        result = PythonCodeRuntime(workspace=session).run(
            "from pathlib import Path\n"
            "import os\n"
            "Path(os.environ['CC_AGENT_OUTPUTS_DIR'], 'report.md').write_text('new', encoding='utf-8')\n"
        )

        self.assertFalse(result.is_error, result.llm_observation)
        self.assertIn("report.md", [artifact["name"] for artifact in result.metadata["artifacts"]])

    def test_run_python_registers_svg_output_artifacts(self):
        storage = FakeStorage()
        session = WorkspaceSession(config=storage_config(), scope=scope(), storage=storage).open()

        result = PythonCodeRuntime(workspace=session).run(
            "from pathlib import Path\n"
            "import os\n"
            "Path(os.environ['CC_AGENT_OUTPUTS_DIR'], 'chart.svg').write_text("
            "'<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>', encoding='utf-8')\n"
        )

        self.assertFalse(result.is_error, result.llm_observation)
        artifacts = result.metadata["artifacts"]
        self.assertEqual(artifacts[0]["name"], "chart.svg")
        self.assertEqual(artifacts[0]["mime_type"], "image/svg+xml")

    def test_run_python_sandbox_does_not_leak_into_skill_scripts(self):
        storage = FakeStorage()
        session = WorkspaceSession(config=storage_config(), scope=scope(), storage=storage).open()

        blocked = PythonCodeRuntime(workspace=session).run(
            "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'print(1)'], check=True)\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo"
            (skill_dir / "scripts").mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: Demo\n---\nBody\n", encoding="utf-8")
            (skill_dir / "scripts" / "nested.py").write_text(
                "import subprocess, sys\n"
                "subprocess.run([sys.executable, '-c', 'print(\"nested-ok\")'], check=True)\n",
                encoding="utf-8",
            )
            script_result = SkillRuntime(workspace_root=session.outputs_dir, workspace=session).run_script(
                {"name": "demo", "path": str(skill_dir / "SKILL.md")},
                "scripts/nested.py",
            )

        self.assertTrue(blocked.is_error)
        self.assertIn("subprocess is disabled", blocked.metadata["stderr"] or blocked.llm_observation)
        self.assertFalse(script_result.is_error, script_result.llm_observation)
        self.assertIn("nested-ok", script_result.metadata["stdout"])

    def test_run_python_internal_tool_requires_workspace(self):
        result = InternalToolExecutor(AgentState(), capability_mode="minio").execute(
            "run_python",
            {"code": "print(1)"},
            "call_run",
        )

        self.assertTrue(result.is_error)
        self.assertIn("workspace is not configured", result.llm_observation)


if __name__ == "__main__":
    unittest.main()
