import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from cc_agent.core.internal_tools import InternalToolExecutor
from cc_agent.core.messages import AgentRunResult, AgentState
from cc_agent.core.runtime import DifyAgentRuntime
from cc_agent.core import runtime as runtime_module
from cc_agent.core.skill_library import SkillLibrarySession, SkillScope, validate_skill_name
from cc_agent.core.workspace import StorageConfig, WorkspaceScope, WorkspaceSession


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.json_objects = {}

    def get_json(self, key):
        value = self.json_objects.get(key)
        return json.loads(json.dumps(value)) if value is not None else None

    def put_json(self, key, payload):
        self.json_objects[key] = json.loads(json.dumps(payload))

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        self.objects[key] = {"bytes": bytes(data), "content_type": content_type}

    def list_objects(self, prefix):
        keys = [key for key in self.objects if key.startswith(prefix)]
        keys.extend(key for key in self.json_objects if key.startswith(prefix))
        return sorted(set(keys))

    def download_file(self, key, local_path):
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(self.objects[key]["bytes"])

    def delete_object(self, key):
        self.objects.pop(key, None)
        self.json_objects.pop(key, None)

    def object_exists(self, key):
        return key in self.objects

    def upload_file(self, key, local_path, content_type="application/octet-stream"):
        self.objects[key] = {
            "bytes": Path(local_path).read_bytes(),
            "content_type": content_type,
        }

    def presigned_get_url(self, key, expiry_seconds, filename="", mime_type=""):
        return f"https://minio.example/{key}?filename={filename}"


def storage_config():
    return StorageConfig(
        enabled=True,
        endpoint="minio:9000",
        bucket="cc-agent",
        access_key="access",
        secret_key="secret",
        secure=False,
    )


def storage_json(app_id="app-1", user_id="user-1", conversation_id="conv-1"):
    return json.dumps(
        {
            "provider": "minio",
            "endpoint": "minio:9000",
            "bucket": "cc-agent",
            "access_key": "access",
            "secret_key": "secret",
            "scope": {
                "app_id": app_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
            },
        }
    )


def scope():
    return SkillScope(app_id="app-1", user_id="user-1")


def workspace_scope():
    return WorkspaceScope(app_id="app-1", user_id="user-1", conversation_id="conv-1")


def skill_md(name="demo", description="Demo skill"):
    return f"""---
name: {name}
description: {description}
---
Use this skill.
"""


def make_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def put_skill(storage, layer, skill_id, text=None, status="active", manifest_name=None):
    if layer == "agent":
        prefix = f"_cc_agent/skills/agent/{skill_id}"
    elif layer == "app":
        prefix = f"app-1/skills/{skill_id}"
    else:
        prefix = f"app-1/users/user-1/skills/{skill_id}"
    name = manifest_name or skill_id
    storage.put_json(
        f"{prefix}/skill.json",
        {
            "id": skill_id,
            "name": name,
            "display_name": name.title(),
            "layer": layer,
            "version": 1,
            "status": status,
            "description": f"{name} description",
            "updated_at": "2026-06-21T00:00:00Z",
        },
    )
    storage.put_bytes(f"{prefix}/files/SKILL.md", (text or skill_md(name)).encode("utf-8"), "text/markdown")
    storage.put_bytes(f"{prefix}/files/references/guide.md", b"reference", "text/markdown")
    storage.put_bytes(f"{prefix}/files/scripts/run.py", b"print('ok')", "text/x-python")


class SkillLibraryTests(unittest.TestCase):
    def test_validates_skill_names(self):
        self.assertEqual(validate_skill_name("spreadsheet_1"), "spreadsheet_1")
        for value in ("bad name", "../bad", "", "x" * 65):
            with self.assertRaises(ValueError):
                validate_skill_name(value)

    def test_loads_three_layers_with_prefix_resources_and_conflict_warnings(self):
        storage = FakeStorage()
        put_skill(storage, "agent", "common")
        put_skill(storage, "app", "slides")
        put_skill(storage, "user", "common")
        put_skill(storage, "user", "deleted-one", status="deleted")

        library = SkillLibrarySession(storage_config(), scope(), storage=storage).open()

        names = [skill["name"] for skill in library.skills]
        self.assertEqual(names, ["common", "slides"])
        common = next(skill for skill in library.skills if skill["name"] == "common")
        slides = next(skill for skill in library.skills if skill["name"] == "slides")
        self.assertEqual(common["layer"], "agent")
        self.assertEqual(slides["layer"], "app")
        self.assertEqual(slides["resources"]["references"], ["references/guide.md"])
        self.assertEqual(slides["resources"]["scripts"], ["scripts/run.py"])
        self.assertIn("conflicts", " ".join(warning["reason"] for warning in library.warnings))

    def test_installs_workspace_zip_as_user_skill_and_refreshes_catalog(self):
        storage = FakeStorage()
        workspace = WorkspaceSession(
            storage_config(),
            workspace_scope(),
            storage=storage,
            dify_files=[
                {
                    "name": "skill.zip",
                    "mime_type": "application/zip",
                    "bytes": make_zip(
                        {
                            "demo-skill/SKILL.md": skill_md("zip-skill", "Zip skill"),
                            "demo-skill/references/guide.md": "details",
                        }
                    ),
                }
            ],
        ).open()
        library = SkillLibrarySession(storage_config(), scope(), storage=storage, workspace=workspace).open()

        result = library.install(from_file_id="upload_1")

        self.assertEqual(result["status"], "installed")
        self.assertEqual(result["name"], "zip-skill")
        self.assertTrue(storage.get_json("app-1/users/user-1/skills/zip-skill/skill.json"))
        self.assertIn("zip-skill", [skill["name"] for skill in library.skills])

    def test_install_requires_overwrite_for_existing_user_skill_and_protects_app_skill(self):
        storage = FakeStorage()
        put_skill(storage, "user", "demo")
        put_skill(storage, "app", "protected")
        workspace = WorkspaceSession(
            storage_config(),
            workspace_scope(),
            storage=storage,
            dify_files=[
                {"name": "demo.md", "mime_type": "text/markdown", "content": skill_md("demo", "New demo")},
                {"name": "protected.md", "mime_type": "text/markdown", "content": skill_md("protected", "Protected")},
            ],
        ).open()
        library = SkillLibrarySession(storage_config(), scope(), storage=storage, workspace=workspace).open()

        existing = library.install(from_file_id="upload_1")
        protected = library.install(from_file_id="upload_2", overwrite=True)
        overwritten = library.install(from_file_id="upload_1", overwrite=True)

        self.assertEqual(existing["status"], "needs_confirmation")
        self.assertEqual(protected["status"], "protected")
        self.assertEqual(overwritten["status"], "installed")

    def test_install_protects_app_skill_by_manifest_name(self):
        storage = FakeStorage()
        put_skill(
            storage,
            "app",
            "admin-folder",
            text=skill_md("admin-name", "Admin skill"),
            manifest_name="admin-name",
        )
        workspace = WorkspaceSession(
            storage_config(),
            workspace_scope(),
            storage=storage,
            dify_files=[
                {"name": "admin.md", "mime_type": "text/markdown", "content": skill_md("admin-name", "User copy")},
            ],
        ).open()
        library = SkillLibrarySession(storage_config(), scope(), storage=storage, workspace=workspace).open()

        result = library.install(from_file_id="upload_1", overwrite=True)

        self.assertEqual(result["status"], "protected")
        self.assertEqual(result["name"], "admin-name")

    def test_rejects_unsafe_zip_paths(self):
        storage = FakeStorage()
        workspace = WorkspaceSession(
            storage_config(),
            workspace_scope(),
            storage=storage,
            dify_files=[
                {
                    "name": "bad.zip",
                    "mime_type": "application/zip",
                    "bytes": make_zip({"../SKILL.md": skill_md("bad")}),
                }
            ],
        ).open()
        library = SkillLibrarySession(storage_config(), scope(), storage=storage, workspace=workspace).open()

        result = library.install(from_file_id="upload_1")

        self.assertEqual(result["status"], "invalid")
        self.assertIn("unsafe", result["message"])

    def test_removes_only_user_skill(self):
        storage = FakeStorage()
        put_skill(storage, "user", "mine")
        put_skill(storage, "agent", "core")
        library = SkillLibrarySession(storage_config(), scope(), storage=storage).open()

        removed = library.remove("mine")
        protected = library.remove("core")

        self.assertEqual(removed["status"], "removed")
        self.assertEqual(protected["status"], "protected")
        self.assertEqual(storage.get_json("app-1/users/user-1/skills/mine/skill.json")["status"], "deleted")
        self.assertNotIn("mine", [skill["name"] for skill in library.skills])


class SkillLibraryToolTests(unittest.TestCase):
    def test_internal_tools_install_and_remove_user_skill(self):
        storage = FakeStorage()
        workspace = WorkspaceSession(
            storage_config(),
            workspace_scope(),
            storage=storage,
            dify_files=[
                {
                    "name": "skill.zip",
                    "mime_type": "application/zip",
                    "bytes": make_zip({"SKILL.md": skill_md("tool-skill", "Tool skill")}),
                }
            ],
        ).open()
        library = SkillLibrarySession(storage_config(), scope(), storage=storage, workspace=workspace).open()
        state = AgentState(
            skills=[
                {
                    "name": "bundled-skill",
                    "source": "bundled",
                    "description": "Bundled skill must remain visible",
                }
            ],
            workspace=workspace,
            skill_library=library,
        )
        executor = InternalToolExecutor(
            state,
            workspace=workspace,
            skill_library=library,
            capability_mode="minio",
        )

        installed = executor.execute("SkillInstall", {"from_file_id": "upload_1"}, "call_install")
        listed = executor.execute("SkillList", {}, "call_list")
        removed = executor.execute("SkillRemove", {"name": "tool-skill"}, "call_remove")

        self.assertFalse(installed.is_error, installed.llm_observation)
        self.assertIn("tool-skill", installed.llm_observation)
        self.assertIn("tool-skill", listed.llm_observation)
        self.assertIn("bundled-skill", [skill["name"] for skill in state.skills])
        self.assertFalse(removed.is_error, removed.llm_observation)
        self.assertNotIn("tool-skill", [skill["name"] for skill in state.skills])
        self.assertIn("bundled-skill", [skill["name"] for skill in state.skills])


class SkillCommandTests(unittest.TestCase):
    def test_skill_slash_command_installs_lists_and_deletes(self):
        storage = FakeStorage()
        workspace = WorkspaceSession(
            storage_config(),
            workspace_scope(),
            storage=storage,
            dify_files=[
                {
                    "name": "skill.zip",
                    "mime_type": "application/zip",
                    "bytes": make_zip({"SKILL.md": skill_md("cmd-skill", "Command skill")}),
                }
            ],
        ).open()
        library = SkillLibrarySession(storage_config(), scope(), storage=storage, workspace=workspace).open()
        state = AgentState(workspace=workspace, skill_library=library)

        from cc_agent.core.builtin_skills import _skill_handler

        validated = _skill_handler(state, "validate upload_1", skill_library=library)
        added = _skill_handler(state, "add upload_1", skill_library=library)
        listed = _skill_handler(state, "list", skill_library=library)
        shown = _skill_handler(state, "show cmd-skill", skill_library=library)
        deleted = _skill_handler(state, "delete cmd-skill", skill_library=library)
        after_delete = _skill_handler(state, "list", skill_library=library)
        restored = _skill_handler(state, "restore cmd-skill", skill_library=library)
        after_restore = _skill_handler(state, "list", skill_library=library)

        self.assertIn("valid", validated)
        self.assertIn("installed", added)
        self.assertIn("cmd-skill", listed)
        self.assertIn("found", shown)
        self.assertIn("removed", deleted)
        self.assertNotIn("cmd-skill", after_delete)
        self.assertIn("restored", restored)
        self.assertIn("cmd-skill", after_restore)


class SkillLibraryRuntimeTests(unittest.TestCase):
    def test_runtime_loads_minio_skill_library_into_agent_state(self):
        storage = FakeStorage()
        put_skill(storage, "user", "runtime-skill", text=skill_md("runtime-skill", "Runtime skill"))
        captured = {}

        class FakeWorkspaceSession:
            def __init__(self, config, scope, dify_files=None):
                self.storage = storage
                self.scope = scope
                self.outputs_dir = Path(tempfile.mkdtemp())

            def open(self):
                self.imported_files = []
                return self

            def commit(self):
                pass

            def activity_payload(self):
                return {"message": "Workspace files updated.", "files": []}

            def close(self):
                pass

        class FakeSummarizer:
            def __init__(self, session, model_config):
                pass

        class FakeModelAdapter:
            def __init__(self, *args, **kwargs):
                pass

        class FakeLoop:
            def __init__(self, **kwargs):
                captured["state"] = kwargs["state"]

            def run(self):
                self.final_result = AgentRunResult(
                    answer="ok",
                    history=[],
                    memory=[],
                    tasks=[],
                    execution_metadata={"finish_reason": "final"},
                )
                return
                yield

        original_workspace = runtime_module.WorkspaceSession
        original_summarizer = runtime_module.DifyHistorySummarizer
        original_model_adapter = runtime_module.DifyModelAdapter
        original_loop = runtime_module.AgentLoop
        runtime_module.WorkspaceSession = FakeWorkspaceSession
        runtime_module.DifyHistorySummarizer = FakeSummarizer
        runtime_module.DifyModelAdapter = FakeModelAdapter
        runtime_module.AgentLoop = FakeLoop
        try:
            strategy = SimpleNamespace(session=SimpleNamespace(conversation_id="conv-1"), _init_prompt_tools=lambda tools: [])
            events = list(
                DifyAgentRuntime(strategy).run(
                    {
                        "query": "hello",
                        "capability_mode": "minio",
                        "storage": storage_json(),
                        "model": SimpleNamespace(name="default"),
                    }
                )
            )
        finally:
            runtime_module.WorkspaceSession = original_workspace
            runtime_module.DifyHistorySummarizer = original_summarizer
            runtime_module.DifyModelAdapter = original_model_adapter
            runtime_module.AgentLoop = original_loop

        self.assertTrue(any(event.get("type") == "RUN_FINISHED" for event in events))
        names = [skill["name"] for skill in captured["state"].skills]
        self.assertIn("create-skill", names)
        self.assertIn("runtime-skill", names)
        self.assertIsNotNone(captured["state"].skill_library)


if __name__ == "__main__":
    unittest.main()
