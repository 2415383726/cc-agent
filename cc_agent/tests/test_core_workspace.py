import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from cc_agent.core.config import AgentRunConfig
from cc_agent.core.internal_tools import InternalToolExecutor
from cc_agent.core.messages import AgentState
from cc_agent.core.messages import AgentRunResult
from cc_agent.core.prompt_builder import PromptBuilder
from cc_agent.core.runtime import DifyAgentRuntime
from cc_agent.core import runtime as runtime_module
from cc_agent.core.skill_runtime import SkillRuntime
from cc_agent.core.state_variable import AgentStateBundle
from cc_agent.core.workspace import (
    StorageConfig,
    WorkspaceFile,
    WorkspaceManifest,
    WorkspaceScope,
    WorkspaceSession,
    object_key_for_sha256,
    safe_workspace_path,
)
from cc_agent.core.workspace.history_store import (
    HistoryStoreConflict,
    load_history_from_storage,
    save_history_to_storage,
)
from cc_agent.core.workspace.state_store import load_state_from_storage, save_state_to_storage
from cc_agent.core.workspace.storage_client import ConditionalWriteConflict


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.json_objects = {}
        self.json_etags = {}

    def get_json(self, key):
        value = self.json_objects.get(key)
        return json.loads(json.dumps(value)) if value is not None else None

    def put_json(self, key, payload):
        self.json_objects[key] = json.loads(json.dumps(payload))
        self.json_etags[key] = str(int(self.json_etags.get(key) or "0") + 1)

    def get_json_with_etag(self, key):
        return self.get_json(key), self.json_etags.get(key)

    def put_json_conditional(self, key, payload, expected_etag):
        current_etag = self.json_etags.get(key)
        if current_etag != expected_etag:
            raise ConditionalWriteConflict(f"conditional write conflict for {key}")
        self.put_json(key, payload)
        return self.json_etags[key]

    def object_exists(self, key):
        return key in self.objects

    def upload_file(self, key, local_path, content_type="application/octet-stream"):
        self.objects[key] = {
            "bytes": Path(local_path).read_bytes(),
            "content_type": content_type,
        }

    def download_file(self, key, local_path):
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(self.objects[key]["bytes"])

    def presigned_get_url(self, key, expiry_seconds, filename="", mime_type=""):
        return f"https://minio.example/{key}?X-Amz-Expires={expiry_seconds}&filename={filename or ''}"

    def delete_object(self, key):
        self.objects.pop(key, None)
        self.json_objects.pop(key, None)


def scope():
    return WorkspaceScope(
        app_id="app-1",
        user_id="user-1",
        conversation_id="conv-1",
        run_id="run-1",
    )


def storage_config(**overrides):
    data = {
        "enabled": True,
        "endpoint": "minio:9000",
        "bucket": "cc-agent",
        "access_key": "access",
        "secret_key": "secret",
        "secure": False,
        "presign_expiry_seconds": 3600,
    }
    data.update(overrides)
    return StorageConfig(**data)


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


class ManifestTests(unittest.TestCase):
    def test_manifest_round_trips_version_and_file_metadata(self):
        manifest = WorkspaceManifest.empty(prefix=scope().workspace_prefix)
        file_item = WorkspaceFile(
            id="file_1",
            name="notes.txt",
            path="uploads/notes.txt",
            object_key=object_key_for_sha256("a" * 64),
            sha256="a" * 64,
            size=11,
            mime_type="text/plain",
            source="upload",
            status="ready",
            created_at="2026-06-21T00:00:00Z",
            updated_at="2026-06-21T00:00:00Z",
        )

        manifest.upsert_file(file_item)
        payload = manifest.to_dict()
        loaded = WorkspaceManifest.from_dict(payload, prefix=scope().workspace_prefix)

        self.assertEqual(payload["version"], 1)
        self.assertEqual(loaded.files[0].id, "file_1")
        self.assertEqual(loaded.files[0].object_key, "objects/sha256/aa/" + "a" * 64)
        self.assertEqual(loaded.next_file_id("upload"), "upload_2")

    def test_safe_workspace_path_rejects_absolute_and_parent_escape(self):
        root = Path(tempfile.mkdtemp())

        self.assertEqual(safe_workspace_path(root, "outputs/report.md"), root / "outputs" / "report.md")
        with self.assertRaises(ValueError):
            safe_workspace_path(root, "../secret.txt")
        with self.assertRaises(ValueError):
            safe_workspace_path(root, "C:/secret.txt")


class WorkspaceSessionTests(unittest.TestCase):
    def test_imports_dify_files_and_commits_manifest_with_presigned_urls(self):
        storage = FakeStorage()
        session = WorkspaceSession(
            config=storage_config(),
            scope=scope(),
            storage=storage,
            dify_files=[
                {
                    "id": "dify-file-1",
                    "name": "input.txt",
                    "mime_type": "text/plain",
                    "content": "hello input",
                }
            ],
        )

        session.open()
        session.commit()

        saved_manifest = storage.get_json(scope().manifest_key)
        self.assertEqual(saved_manifest["files"][0]["name"], "input.txt")
        self.assertEqual(saved_manifest["files"][0]["source"], "upload")
        self.assertTrue(storage.objects[saved_manifest["files"][0]["object_key"]]["bytes"])
        activity = session.activity_payload()
        self.assertEqual(activity["files"][0]["status"], "ready")
        self.assertIn("download_url", activity["files"][0])
        self.assertIn("X-Amz-Expires=3600", activity["files"][0]["download_url"])

    def test_reuses_dify_file_by_source_id_and_cleans_owned_root(self):
        storage = FakeStorage()
        raw_file = {"id": "dify-file-1", "name": "input.txt", "mime_type": "text/plain", "content": "hello"}

        first = WorkspaceSession(config=storage_config(), scope=scope(), storage=storage, dify_files=[raw_file])
        first.open()
        first.commit()
        first_id = first.manifest.files[0].id
        owned_root = first.local_root
        first.close()

        second = WorkspaceSession(config=storage_config(), scope=scope(), storage=storage, dify_files=[raw_file])
        second.open()
        second.commit()

        saved = WorkspaceManifest.from_dict(storage.get_json(scope().manifest_key), prefix=scope().workspace_prefix)
        self.assertEqual(len(saved.files), 1)
        self.assertEqual(saved.files[0].id, first_id)
        self.assertEqual(saved.files[0].source_id, "dify-file-1")
        self.assertFalse(owned_root.exists())
        second.close()

    def test_close_preserves_explicit_local_root(self):
        storage = FakeStorage()
        with tempfile.TemporaryDirectory() as root:
            session = WorkspaceSession(config=storage_config(), scope=scope(), storage=storage, local_root=root)
            session.open()
            session.close()
            self.assertTrue(Path(root).exists())

    def test_write_text_output_materializes_and_updates_manifest(self):
        storage = FakeStorage()
        session = WorkspaceSession(config=storage_config(), scope=scope(), storage=storage)
        session.open()

        artifact = session.write_text_output("report.md", "# Report\n", mime_type="text/markdown")
        session.commit()

        self.assertEqual(artifact["name"], "report.md")
        self.assertEqual(artifact["status"], "ready")
        self.assertTrue(artifact["download_url"].startswith("https://minio.example/objects/sha256/"))
        saved_manifest = WorkspaceManifest.from_dict(storage.get_json(scope().manifest_key), prefix=scope().workspace_prefix)
        self.assertEqual(saved_manifest.files[0].source, "output")
        materialized = session.materialize(saved_manifest.files[0].id)
        self.assertEqual(Path(materialized).read_text(encoding="utf-8"), "# Report\n")

    def test_history_store_uses_revision_conflict_detection(self):
        storage = FakeStorage()

        first = save_history_to_storage(
            storage,
            scope().workspace_prefix,
            messages=[{"role": "user", "content": "one"}],
            summary="first",
            version=1,
            expected_revision=0,
        )
        loaded = load_history_from_storage(storage, scope().workspace_prefix)

        self.assertEqual(first["revision"], 1)
        self.assertEqual(loaded["revision"], 1)
        self.assertEqual(loaded["messages"][0]["content"], "one")
        with self.assertRaises(HistoryStoreConflict):
            save_history_to_storage(
                storage,
                scope().workspace_prefix,
                messages=[{"role": "user", "content": "stale"}],
                expected_revision=0,
            )

    def test_state_store_persists_tasks_to_minio_bundle(self):
        storage = FakeStorage()
        tasks = [{"id": "1", "subject": "ship task state", "status": "pending"}]

        saved = save_state_to_storage(
            storage,
            scope().workspace_prefix,
            AgentStateBundle(tasks=tasks),
            expected_revision=0,
        )
        loaded = load_state_from_storage(storage, scope().workspace_prefix)

        self.assertEqual(saved["state_summary"]["task_count"], 1)
        self.assertEqual(loaded.tasks, tasks)

    def test_prompt_context_hides_deleted_files(self):
        storage = FakeStorage()
        session = WorkspaceSession(config=storage_config(), scope=scope(), storage=storage)
        session.open()
        old_file = session.write_text_output("old.md", "old")
        session.write_text_output("current.md", "current")

        session.delete_file(old_file["id"])
        prompt = session.prompt_context()

        self.assertNotIn("old.md", prompt)
        self.assertIn("current.md", prompt)


class WorkspaceToolTests(unittest.TestCase):
    def test_file_tools_list_inspect_read_and_write_outputs(self):
        storage = FakeStorage()
        session = WorkspaceSession(
            config=storage_config(),
            scope=scope(),
            storage=storage,
            dify_files=[
                {
                    "name": "data.json",
                    "mime_type": "application/json",
                    "content": "{\"answer\": 42}",
                }
            ],
        )
        session.open()
        state = AgentState(workspace=session)
        executor = InternalToolExecutor(state, workspace=session, capability_mode="minio")

        listed = json.loads(executor.execute("list_files", {}, "call_list").llm_observation)
        inspected = json.loads(executor.execute("inspect_file", {"file_id": listed["files"][0]["id"]}, "call_inspect").llm_observation)
        read = executor.execute("read_file", {"file_id": listed["files"][0]["id"], "max_chars": 100}, "call_read")
        written = executor.execute("write_file", {"path": "answer.md", "content": "# Answer\n"}, "call_write")

        self.assertEqual(listed["files"][0]["name"], "data.json")
        self.assertEqual(inspected["kind"], "json")
        self.assertIn("\"answer\": 42", read.llm_observation)
        self.assertFalse(written.is_error)
        self.assertEqual(written.metadata["activity_type"], "cc_agent.workspace")
        self.assertIn("download_url", written.metadata["artifacts"][0])

    def test_file_tools_fail_clearly_without_workspace(self):
        result = InternalToolExecutor(AgentState(), capability_mode="minio").execute("list_files", {}, "call_1")

        self.assertTrue(result.is_error)
        self.assertIn("workspace is not configured", result.llm_observation)

    def test_skill_runtime_artifacts_are_registered_as_workspace_outputs(self):
        storage = FakeStorage()
        session = WorkspaceSession(config=storage_config(), scope=scope(), storage=storage)
        session.open()
        skill_dir = Path(tempfile.mkdtemp()) / "demo_skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
        (scripts_dir / "make.py").write_text(
            "\n".join(
                [
                    "import json, os",
                    "from pathlib import Path",
                    "out = Path(os.environ['CC_AGENT_OUTPUTS_DIR']) / 'skill-report.md'",
                    "out.write_text('# Skill Report\\n', encoding='utf-8')",
                    "print(json.dumps({'artifacts': [{'path': str(out), 'name': 'skill-report.md', 'mime_type': 'text/markdown'}]}))",
                ]
            ),
            encoding="utf-8",
        )

        runtime = SkillRuntime(workspace_root=session.outputs_dir, workspace=session)
        result = runtime.run_script({"name": "demo", "path": str(skill_dir / "SKILL.md")}, "scripts/make.py")

        self.assertFalse(result.is_error)
        self.assertEqual(result.metadata["activity_type"], "cc_agent.workspace")
        self.assertIn("download_url", result.metadata["artifacts"][0])
        session.commit()
        saved_manifest = storage.get_json(scope().manifest_key)
        self.assertEqual(saved_manifest["files"][0]["path"], "outputs/skill-report.md")


class PromptAndRuntimeWorkspaceTests(unittest.TestCase):
    def test_prompt_builder_injects_workspace_rules_without_secrets_or_internal_urls(self):
        storage = FakeStorage()
        session = WorkspaceSession(
            config=storage_config(secret_key="do-not-leak"),
            scope=scope(),
            storage=storage,
            dify_files=[{"name": "input.txt", "mime_type": "text/plain", "content": "hello"}],
        )
        session.open()
        prompt = PromptBuilder(
            AgentRunConfig(query="q", capability_mode="minio"),
            AgentState(workspace=session),
        ).system_prompt()

        self.assertIn("Workspace files", prompt)
        self.assertIn("file_id", prompt)
        self.assertIn("uploads are read-only", prompt)
        self.assertNotIn("do-not-leak", prompt)
        self.assertNotIn("https://minio.example", prompt)

    def test_runtime_reports_missing_minio_config_when_minio_mode_but_no_creds(self):
        strategy = SimpleNamespace(session=SimpleNamespace(conversation_id="conv-1"), _init_prompt_tools=lambda tools: [])

        events = list(
            DifyAgentRuntime(strategy).run(
                {
                    "query": "summarize file",
                    "capability_mode": "minio",
                    "model": SimpleNamespace(name="default"),
                }
            )
        )

        error_events = [event for event in events if event.get("type") == "RUN_ERROR"]
        self.assertTrue(error_events)
        self.assertIn("MinIO", error_events[0]["message"])

    def test_runtime_imports_files_and_emits_workspace_activity_with_fake_storage(self):
        created = {}

        class FakeWorkspaceSession:
            def __init__(self, config, scope, dify_files=None):
                created["config"] = config
                created["scope"] = scope
                created["dify_files"] = list(dify_files or [])
                self.outputs_dir = Path(tempfile.mkdtemp())
                created["workspace_instance"] = self

            def open(self):
                created["opened"] = True
                self.imported_files = []
                return self

            def commit(self):
                created["committed"] = True

            def activity_payload(self):
                return {
                    "message": "Workspace files updated.",
                    "files": [
                        {
                            "name": "answer.md",
                            "size": 9,
                            "mime_type": "text/markdown",
                            "status": "ready",
                            "download_url": "https://minio.example/answer.md?X-Amz-Expires=3600",
                            "expires_at": "2026-06-21T01:00:00Z",
                        }
                    ],
                }

            def close(self):
                created["closed"] = True

        class FakeSummarizer:
            def __init__(self, session, model_config):
                pass

        class FakeModelAdapter:
            def __init__(self, *args, **kwargs):
                pass

        class FakeLoop:
            def __init__(self, **kwargs):
                created["workspace_on_state"] = kwargs["state"].workspace

            def run(self):
                self.final_result = AgentRunResult(
                    answer="done",
                    history=[],
                    memory=[],
                    tasks=[],
                    execution_metadata={"finish_reason": "final"},
                )
                return
                yield

        original_workspace_session = runtime_module.WorkspaceSession
        original_summarizer = runtime_module.DifyHistorySummarizer
        original_model_adapter = runtime_module.DifyModelAdapter
        original_loop = runtime_module.AgentLoop
        runtime_module.WorkspaceSession = FakeWorkspaceSession
        runtime_module.DifyHistorySummarizer = FakeSummarizer
        runtime_module.DifyModelAdapter = FakeModelAdapter
        runtime_module.AgentLoop = FakeLoop
        try:
            strategy = SimpleNamespace(session=SimpleNamespace(conversation_id="conv-1", app_id="app-1"), _init_prompt_tools=lambda tools: [])
            events = list(
                DifyAgentRuntime(strategy).run(
                    {
                        "query": "summarize file",
                        "capability_mode": "minio",
                        "files": [{"name": "input.txt", "content": "hello"}],
                        "model": SimpleNamespace(name="default"),
                        "storage": storage_json(),
                    }
                )
            )
        finally:
            runtime_module.WorkspaceSession = original_workspace_session
            runtime_module.DifyHistorySummarizer = original_summarizer
            runtime_module.DifyModelAdapter = original_model_adapter
            runtime_module.AgentLoop = original_loop

        workspace_events = [
            event
            for event in events
            if event.get("type") == "ACTIVITY_SNAPSHOT" and event.get("activityType") == "cc_agent.workspace"
        ]
        finished = next(event for event in events if event.get("type") == "RUN_FINISHED")

        self.assertTrue(created["opened"])
        self.assertTrue(created["committed"])
        self.assertTrue(created["closed"])
        self.assertEqual(created["dify_files"][0]["name"], "input.txt")
        self.assertIs(created["workspace_on_state"], created["workspace_instance"])
        self.assertTrue(workspace_events)
        self.assertEqual(workspace_events[0]["content"]["files"][0]["download_url"], "https://minio.example/answer.md?X-Amz-Expires=3600")
        self.assertEqual(
            finished["result"]["execution_metadata"]["workspace"]["files"][0]["name"],
            "answer.md",
        )
        self.assertNotIn("secret", json.dumps(finished, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
