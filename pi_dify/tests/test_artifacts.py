from __future__ import annotations

import unittest

from _support import ROOT  # noqa: F401

from pi_agent.artifacts import normalize_dify_responses, normalize_mcp_result


class DifyArtifactTests(unittest.TestCase):
    def test_repeated_halves_are_deduplicated(self) -> None:
        result = normalize_dify_responses(
            [
                {"type": "text", "message": "same"},
                {"type": "json", "message": {"json_object": {"a": 1, "b": 2}}},
                {"type": "text", "message": "same"},
                {"type": "json", "message": {"json_object": {"b": 2, "a": 1}}},
            ]
        )
        self.assertEqual(result.text.count("same"), 1)
        self.assertEqual(result.text.count('"a"'), 1)

    def test_dify_file_artifact_is_metadata_only(self) -> None:
        result = normalize_dify_responses(
            [
                {
                    "type": "blob",
                    "message": {
                        "filename": "report.pdf",
                        "mime_type": "application/pdf",
                        "size": 42,
                    },
                }
            ]
        )
        self.assertEqual(len(result.artifacts), 1)
        public = result.artifacts[0].public()
        self.assertEqual(public["name"], "report.pdf")
        self.assertEqual(public["source"], "dify")
        self.assertNotIn("data", public)

    def test_link_and_image_are_preserved(self) -> None:
        result = normalize_dify_responses(
            [
                {"type": "link", "message": "https://example.test/a"},
                {"type": "image", "message": "https://example.test/a.png"},
            ]
        )
        self.assertEqual([artifact.kind for artifact in result.artifacts], ["link", "image"])
        self.assertIn("result link", result.text)


class McpResultTests(unittest.TestCase):
    def test_text_image_and_blob_are_separated(self) -> None:
        result = normalize_mcp_result(
            {
                "content": [
                    {"type": "text", "text": "rendered"},
                    {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"},
                    {
                        "type": "resource",
                        "resource": {
                            "uri": "file:///report.txt",
                            "mimeType": "application/octet-stream",
                            "blob": "d29ybGQ=",
                        },
                    },
                ]
            }
        )
        self.assertIn("rendered", result.text)
        self.assertEqual(len(result.artifacts), 2)
        self.assertEqual(result.artifacts[0].data, b"hello")
        self.assertEqual(result.artifacts[1].data, b"world")

    def test_structured_content_is_used_when_no_text(self) -> None:
        result = normalize_mcp_result({"content": [], "structuredContent": {"ok": True}})
        self.assertIn('"ok": true', result.text)


if __name__ == "__main__":
    unittest.main()
