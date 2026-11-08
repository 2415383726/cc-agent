"""Tests for the `visualize` internal tool, its lint gate and display projection."""

import unittest
from types import SimpleNamespace

from pi_agent.contract import DisplayEvents
from pi_agent.errors import PiError
from pi_agent.observer import DisplayObserver
from pi_agent.tools import build_specs
from pi_agent.visualize import (
    MAX_FRAGMENT_BYTES,
    MAX_FRAGMENT_CHARS,
    FragmentLint,
    resolve_mode,
    visualize_outcome,
)


def make_config(**overrides):
    base = {"display_result_chars": 8_000, "visualize_max_fragment_chars": MAX_FRAGMENT_CHARS}
    base.update(overrides)
    return SimpleNamespace(**base)


class FragmentLintTests(unittest.TestCase):
    def setUp(self):
        self.lint = FragmentLint()

    def test_ok_fragment_returns_size_and_no_warnings(self):
        size, warnings = self.lint.check("<div id=\"chart\"><script>const x = 1;</script></div>")
        self.assertGreater(size, 0)
        self.assertEqual(warnings, [])

    def test_empty_fragment_raises(self):
        with self.assertRaises(PiError) as ctx:
            self.lint.check("")
        self.assertIn("`fragment` is empty", str(ctx.exception))

    def test_oversize_chars_raises(self):
        with self.assertRaises(PiError) as ctx:
            self.lint.check("x" * (MAX_FRAGMENT_CHARS + 1))
        self.assertIn("over the", str(ctx.exception))

    def test_oversize_bytes_raises(self):
        # CJK chars: under the char cap, over the UTF-8 byte cap.
        with self.assertRaises(PiError) as ctx:
            self.lint.check("测" * (MAX_FRAGMENT_BYTES // 3 + 1))
        self.assertIn("UTF-8 bytes", str(ctx.exception))
        self.assertGreater(MAX_FRAGMENT_BYTES, 0)

    def test_document_skeleton_raises(self):
        for bad in [
            "<!DOCTYPE html><div>x</div>",
            "<html lang=\"en\"><div>x</div></html>",
            "<head><title>t</title></head>",
            "<BODY><p>x</p></BODY>",
        ]:
            with self.assertRaises(PiError):
                self.lint.check(bad)

    def test_external_references_raise(self):
        for bad in [
            "<script src=\"https://cdn.example.com/x.js\"></script>",
            "<img src=\"//evil.example/x.png\">",
            "<link href=\"https://fonts.example/x.css\" rel=\"stylesheet\">",
            "<style>body { background: url('https://x.example/bg.png') }</style>",
            "<style>@import url('https://x.example/y.css');</style>",
        ]:
            with self.assertRaises(PiError) as ctx:
                self.lint.check(bad)
            self.assertIn("external resources", str(ctx.exception))

    def test_network_apis_raise(self):
        for bad in [
            "<script>fetch('/api')</script>",
            "<script>const x = new XMLHttpRequest();</script>",
            "<script>new WebSocket('wss://x');</script>",
            "<script>new EventSource('/sse');</script>",
            "<script>navigator.sendBeacon('/log');</script>",
        ]:
            with self.assertRaises(PiError) as ctx:
                self.lint.check(bad)
            self.assertIn("network APIs", str(ctx.exception))

    def test_plain_form_is_legal(self):
        """A bare <form> used as layout does not warn (reference VZ008 scope)."""
        _, warnings = self.lint.check("<form><input></form>")
        self.assertEqual(warnings, [])

    def test_form_submission_variants_are_errors(self):
        for markup in [
            '<form action="#"><input></form>',
            '<form method="post"><input></form>',
            '<button formaction="/go">go</button>',
        ]:
            with self.assertRaises(PiError) as ctx:
                self.lint.check(markup)
            self.assertIn("[VZ008]", str(ctx.exception))

    def test_anchor_hrefs_are_allowed(self):
        """<a href> is not a resource load; outbound links do not trip VZ005."""
        _, warnings = self.lint.check('<a href="https://example.com">docs</a>')
        self.assertEqual(warnings, [])

    def test_data_import_passes_but_remote_import_fails(self):
        _, warnings = self.lint.check("<style>@import url(data:text/css,body{color:red})</style>")
        self.assertEqual(warnings, [])
        with self.assertRaises(PiError) as ctx:
            self.lint.check("<style>@import url(\"https://evil.example/x.css\")</style>")
        self.assertIn("[VZ005]", str(ctx.exception))

    def test_relative_resource_url_warns(self):
        for markup in [
            '<img src="chart.png" alt="c">',
            '<link href="./theme.css">',
            '<img src="/a.png">',
        ]:
            with self.subTest(markup=markup):
                _, warnings = self.lint.check(markup)
                self.assertEqual(len(warnings), 1)
                self.assertIn("[VZ106]", warnings[0])

    def test_storage_api_warns(self):
        _, warnings = self.lint.check("<script>localStorage.setItem('k', 'v')</script>")
        self.assertEqual(len(warnings), 1)
        self.assertIn("[VZ108]", warnings[0])
        self.assertIn("localStorage", warnings[0])

    def test_hardcoded_colour_warns_with_examples(self):
        _, warnings = self.lint.check(
            '<div style="color:#1a73e8"><style>.a{border-color:#f00}</style></div>'
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("[VZ101]", warnings[0])
        self.assertIn("#1a73e8", warnings[0])

    def test_prose_does_not_trip_colour_warning(self):
        _, warnings = self.lint.check("<p>Read the #docs section.</p>")
        self.assertEqual(warnings, [])

    def test_color_scheme_is_rejected(self):
        for markup in [
            "<style>:root { color-scheme: dark }</style>",
            "<script>el.style.colorScheme = 'dark'</script>",
            '<meta name="color-scheme" content="dark">',
        ]:
            with self.assertRaises(PiError) as ctx:
                self.lint.check(markup)
            self.assertIn("[VZ009]", str(ctx.exception))

    def test_current_script_is_rejected(self):
        with self.assertRaises(PiError) as ctx:
            self.lint.check("<script>const root = document.currentScript.parentElement</script>")
        self.assertIn("[VZ010]", str(ctx.exception))

    def test_escaped_markup_is_rejected(self):
        for markup in [
            '<div class=\\"card\\">x</div>',
            "<div>one</div>\\n\\n<div>two</div>",
            "<script>\\nvar x = 1</script>",
        ]:
            with self.assertRaises(PiError) as ctx:
                self.lint.check(markup)
            self.assertIn("[VZ004]", str(ctx.exception))

    def test_real_newlines_and_js_escapes_pass(self):
        _, warnings = self.lint.check(
            '<div class="card">\n  <p>line</p>\n</div>\n<script>var s = "a\\nb"</script>'
        )
        self.assertEqual(warnings, [])

    def test_data_uris_and_inline_resources_pass(self):
        _, warnings = self.lint.check(
            "<style>body { background: url(data:image/png;base64,AAA) }</style>"
            "<img src=\"data:image/svg+xml;base64,AAA\">"
        )
        self.assertEqual(warnings, [])


class ResolveModeTests(unittest.TestCase):
    def test_defaults_to_inline(self):
        self.assertEqual(resolve_mode(None), "inline")
        self.assertEqual(resolve_mode(""), "inline")

    def test_accepts_known_modes(self):
        self.assertEqual(resolve_mode("wide"), "wide")

    def test_unknown_mode_raises(self):
        with self.assertRaises(PiError) as ctx:
            resolve_mode("page")
        self.assertIn("`mode` must be one of", str(ctx.exception))


class VisualizeOutcomeTests(unittest.TestCase):
    def test_ok_outcome_keeps_model_text_short_and_projects_visual(self):
        fragment = (
            "<div id=\"v\"><script>document.getElementById('v').textContent = 'ok';</script></div>"
        )
        outcome = visualize_outcome(
            {"fragment": fragment, "title": "  排序演示  ", "mode": "wide"},
            max_fragment_chars=MAX_FRAGMENT_CHARS,
        )
        self.assertFalse(outcome["is_error"])
        self.assertLess(len(outcome["text"]), 300)
        self.assertNotIn(fragment, outcome["text"])
        visual = outcome["details"]["visual"]
        self.assertEqual(visual["fragment"], fragment)
        self.assertEqual(visual["title"], "排序演示")
        self.assertEqual(visual["mode"], "wide")
        self.assertEqual(visual["size_bytes"], len(fragment.encode("utf-8")))
        self.assertEqual(outcome["details"]["kind"], "visualize")
        self.assertEqual(outcome["details"]["execution_outcome"], "executed")

    def test_title_defaults_and_clamps(self):
        outcome = visualize_outcome({"fragment": "<p>x</p>"}, max_fragment_chars=100)
        self.assertEqual(outcome["details"]["visual"]["title"], "Visualization")
        outcome = visualize_outcome(
            {"fragment": "<p>x</p>", "title": "长" * 100}, max_fragment_chars=100
        )
        self.assertEqual(len(outcome["details"]["visual"]["title"]), 80)

    def test_lint_error_raises_pi_error(self):
        with self.assertRaises(PiError):
            visualize_outcome({"fragment": "<html><body>x</body></html>"}, max_fragment_chars=100)
        with self.assertRaises(PiError):
            visualize_outcome({}, max_fragment_chars=100)
        with self.assertRaises(PiError):
            visualize_outcome({"fragment": 42}, max_fragment_chars=100)

    def test_custom_char_cap(self):
        with self.assertRaises(PiError):
            visualize_outcome({"fragment": "x" * 51}, max_fragment_chars=50)


class BuildSpecsTests(unittest.TestCase):
    def test_visualize_spec_is_registered_as_internal(self):
        specs = build_specs([], None)
        spec = next((item for item in specs if item.name == "visualize"), None)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.source, "internal")
        self.assertIn("Load the `visualize` skill", spec.description)


class _Result:
    def __init__(self, details):
        self.content = [{"type": "text", "text": "Rendered \"T\" as an inline card (10 chars)."}]
        self.details = details


class ObserverVisualTests(unittest.TestCase):
    def _run_tool_end(self, details, tool_name="visualize", config=None):
        events = DisplayEvents(run_id="run_1")
        seen: list[dict] = []
        observer = DisplayObserver(events, seen.append, config or make_config())
        event = SimpleNamespace(
            type="tool_execution_end",
            tool_call_id="call_1",
            tool_name=tool_name,
            result=_Result(details),
            is_error=False,
        )
        import asyncio

        asyncio.run(observer(event))
        # The emit surface is the Dify log envelope; unwrap the display event.
        return [item["data"]["piagent"] for item in seen]

    def test_visual_payload_passes_through_without_clipping(self):
        fragment = "<div>" + "x" * 30_000 + "</div>"
        seen = self._run_tool_end(
            {
                "kind": "visualize",
                "status": "ok",
                "visual": {
                    "fragment": fragment,
                    "title": "T",
                    "mode": "inline",
                    "size_bytes": 30010,
                },
                "execution_outcome": "executed",
            }
        )
        self.assertEqual(len(seen), 1)
        fields = seen[0]
        self.assertEqual(fields["type"], "tool.end")
        self.assertEqual(fields["name"], "visualize")
        self.assertEqual(fields["visual"]["fragment"], fragment)
        self.assertLess(len(fields["result"]), 200)
        # The whole event stays within the visual envelope.
        import json

        self.assertLessEqual(
            len(json.dumps(fields, ensure_ascii=False, default=str).encode("utf-8")), 131_072
        )

    def test_other_tools_keep_the_display_clip(self):
        seen = self._run_tool_end(
            {"kind": "other", "status": "ok", "execution_outcome": "executed"},
            tool_name="lookup_order",
            config=make_config(display_result_chars=100),
        )
        fields = seen[0]
        self.assertNotIn("visual", fields)
        self.assertLessEqual(len(fields["result"]), 100)

    def test_visualize_without_visual_payload_stays_clean(self):
        seen = self._run_tool_end({"kind": "visualize", "status": "error"}, tool_name="visualize")
        fields = seen[0]
        self.assertEqual(fields["status"], "error")
        self.assertNotIn("visual", fields)


class VisualEventBudgetTests(unittest.TestCase):
    def test_visual_event_uses_larger_envelope(self):
        events = DisplayEvents(run_id="run_1")
        big = "x" * 40_000
        payload = events.make("tool.end", name="visualize", visual={"fragment": big})
        encoded = __import__("json").dumps(payload, ensure_ascii=False, default=str)
        self.assertIn("fragment", encoded)  # not truncated to skeleton
        self.assertLessEqual(len(encoded.encode("utf-8")), 131_072)

    def test_regular_event_keeps_the_small_envelope(self):
        events = DisplayEvents(run_id="run_1")
        big = "x" * 30_000
        payload = events.make("tool.end", name="other", result=big)
        self.assertTrue(payload.get("truncated") or len(str(payload.get("result", ""))) < len(big))


if __name__ == "__main__":
    unittest.main()


class DisplayEventBudgetTests(unittest.TestCase):
    """display_max_events 只约束结构事件；delta 是内容流，永不因预算丢尾。"""

    def _events(self, **kwargs):
        from pi_agent.contract import DisplayEvents

        return DisplayEvents(run_id="run_budget", **kwargs)

    def test_deltas_bypass_the_structural_cap(self):
        events = self._events(max_events=5)
        recorded = []
        for _ in range(20):
            event = events.make("message.delta", message_id="a1", delta="x")
            out = events.record(event)
            if out is not None:
                recorded.append(out)
        self.assertEqual(len(recorded), 20)
        self.assertEqual(events.delta_events, 20)
        self.assertEqual(events.emitted, 0)

    def test_message_end_survives_after_delta_flood(self):
        events = self._events(max_events=5)
        for _ in range(300):
            events.record(events.make("message.delta", delta="x"))
        end = events.record(
            events.make("message.end", message_id="a1", text="done", stop_reason="stop")
        )
        self.assertIsNotNone(end)
        state = events.record(events.make("tool.end", tool_call_id="c1", name="t", status="ok"))
        self.assertIsNotNone(state)

    def test_structural_events_still_capped(self):
        events = self._events(max_events=3)
        kept = 0
        for _ in range(6):
            out = events.record(events.make("tool.end", tool_call_id="c", name="t", status="ok"))
            if out is not None:
                kept += 1
        self.assertEqual(kept, 3)
        self.assertEqual(events.dropped, 3)

    def test_delta_flood_ceiling(self):
        from pi_agent.contract import MAX_DELTA_EVENTS

        events = self._events()
        events.delta_events = MAX_DELTA_EVENTS
        self.assertIsNone(events.record(events.make("message.delta", delta="x")))
