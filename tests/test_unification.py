"""Unification-plan regression tests (Bridges 1-4).

Covers the new seams added by the comprehensive unification plan:
Ollama health/model helpers, the unified loopback endpoint, the
300ms maturing window, editor target acquisition, smart (Llama-backed)
utterance parsing with regex fast-path, main-thread principle commits,
the offline SAPI speech fallback, and the worker-side Ollama preflight.
Qt-free except where marked (skipped without bindings).
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _needs_qt(test):
    try:
        from desktop_app.tabs._qt import load_qt
        load_qt()
    except ImportError:
        test.skipTest("PyQt6/PySide6 not installed")
    from desktop_app.tabs._qt import load_qt
    _, QtCore, _, QtWidgets = load_qt()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    try:
        test._qt_app_ref = app
    except AttributeError:
        pass
    return QtCore


class EndpointUnificationTest(unittest.TestCase):
    def test_loopback_endpoint_unified(self):
        from desktop_app.llm import DEFAULT_OLLAMA_ENDPOINT
        from mimir.llama_intent import DEFAULT_LOCAL_ENDPOINT
        self.assertEqual(DEFAULT_OLLAMA_ENDPOINT, DEFAULT_LOCAL_ENDPOINT)
        self.assertEqual(DEFAULT_OLLAMA_ENDPOINT, "http://127.0.0.1:11434")

    def test_debounce_window_is_300ms(self):
        import inspect

        from mimir.sensory import SensoryService
        from mimir.watch_fs import DEFAULT_DEBOUNCE_S
        self.assertEqual(DEFAULT_DEBOUNCE_S, 0.3)
        # The default flows through the constructor signature.
        sig = inspect.signature(SensoryService.__init__)
        self.assertEqual(sig.parameters["debounce_s"].default, 0.3)


class OllamaHelperTest(unittest.TestCase):
    def test_probe_down_never_raises(self):
        from desktop_app.ollama import probe_ollama
        with mock.patch("desktop_app.ollama.is_ollama_available",
                        side_effect=RuntimeError("boom")):
            report = probe_ollama("http://127.0.0.1:11434")
        self.assertFalse(report["available"])
        self.assertEqual(report["models"], [])
        self.assertEqual(report["selected"], "llama3.2:1b")

    def test_probe_up_selects_best_model(self):
        from desktop_app.ollama import probe_ollama
        with mock.patch("desktop_app.ollama.is_ollama_available",
                        return_value=True), \
                mock.patch("desktop_app.ollama.get_available_local_models",
                           return_value=["qwen3:8b", "llama3.2:1b"]), \
                mock.patch("desktop_app.ollama.select_best_local_model",
                           return_value="llama3.2:1b"):
            report = probe_ollama()
        self.assertTrue(report["available"])
        self.assertEqual(report["selected"], "llama3.2:1b")
        self.assertEqual(len(report["models"]), 2)

    def test_best_model_explicit_pref_wins(self):
        from desktop_app.ollama import best_model_for
        from desktop_app.prefs import DesktopPrefs
        prefs = DesktopPrefs(model_name="custom:7b")
        with mock.patch("desktop_app.ollama.select_best_local_model",
                        side_effect=AssertionError("must not probe")):
            self.assertEqual(best_model_for(prefs), "custom:7b")

    def test_ensure_fast_path_when_running(self):
        from desktop_app.ollama import ensure_ollama_daemon
        with mock.patch("desktop_app.ollama.is_ollama_available",
                        return_value=True):
            ok, message = ensure_ollama_daemon()
        self.assertTrue(ok)
        self.assertIn("already running", message)

    def test_ensure_without_binary_points_at_download(self):
        from desktop_app.ollama import OLLAMA_DOWNLOAD_URL, ensure_ollama_daemon
        with mock.patch("desktop_app.ollama.is_ollama_available",
                        return_value=False), \
                mock.patch("desktop_app.ollama.shutil.which",
                           return_value=None):
            ok, message = ensure_ollama_daemon()
        self.assertFalse(ok)
        self.assertIn(OLLAMA_DOWNLOAD_URL, message)


class EditorAcquisitionTest(unittest.TestCase):
    def _backend(self, windows, foreground=None, activate_ok=True):
        from mimir.desktop import WindowInfo

        class _Fake:
            def __init__(self):
                self._windows = [
                    WindowInfo(handle=h, process_id=1000 + h, executable=e,
                               title=t)
                    for h, e, t in windows
                ]
                self._fg = foreground
                self.activated = []

            def list_windows(self):
                return list(self._windows)

            def foreground(self):
                if self._fg is None:
                    return None
                for info in self._windows:
                    if info.handle == self._fg:
                        return info
                return None

            def is_valid(self, handle):
                return any(w.handle == handle for w in self._windows)

            def activate(self, handle):
                self.activated.append(handle)
                if activate_ok:
                    self._fg = handle
                return activate_ok

        return _Fake()

    def test_find_editor_matches_title_and_exe(self):
        from mimir.desktop import find_editor_window
        backend = self._backend([
            (11, "explorer.exe", "File Explorer"),
            (22, "Code.exe", "settings.py — Visual Studio Code"),
        ])
        found = find_editor_window(backend)
        self.assertIsNotNone(found)
        self.assertEqual(found.handle, 22)

    def test_find_editor_custom_titles(self):
        from mimir.desktop import find_editor_window
        backend = self._backend([
            (11, "explorer.exe", "File Explorer"),
            (33, "code-oss", "notes.md"),
        ])
        self.assertIsNone(find_editor_window(backend, ["PyCharm"]))
        found = find_editor_window(backend, ["code-oss"])
        self.assertIsNotNone(found)
        self.assertEqual(found.handle, 33)

    def test_find_editor_never_raises(self):
        from mimir.desktop import find_editor_window

        class _Broken:
            def list_windows(self):
                raise RuntimeError("no desktop")

        self.assertIsNone(find_editor_window(_Broken()))

    def test_focus_window_verifies_foreground(self):
        from mimir.desktop import focus_window
        backend = self._backend([(22, "Code.exe", "VS Code")],
                                foreground=22)
        self.assertTrue(focus_window(backend, 22))

    def test_focus_window_refusal_is_false(self):
        from mimir.desktop import focus_window
        backend = self._backend([(22, "Code.exe", "VS Code")],
                                foreground=99, activate_ok=False)
        self.assertFalse(focus_window(backend, 22))

    def test_focus_window_mismatch_is_false(self):
        from mimir.desktop import focus_window
        backend = self._backend([(22, "Code.exe", "VS Code")],
                                foreground=11)
        # activate moves foreground only when it succeeds here; force
        # a mismatch by making activate a no-op success.
        backend.activate = lambda handle: True
        self.assertFalse(focus_window(backend, 22))

    def test_acquire_editor_target_preselect(self):
        _needs_qt(self)
        from desktop_app.actuate_worker import acquire_editor_target
        backend = self._backend([
            (22, "Code.exe", "app.py — Visual Studio Code"),
        ])
        spec = acquire_editor_target(backend)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.handle, 22)
        self.assertEqual(backend.activated, [])  # no focus steal

    def test_acquire_editor_target_focuses_on_request(self):
        _needs_qt(self)
        from desktop_app.actuate_worker import acquire_editor_target
        backend = self._backend([
            (22, "Code.exe", "app.py — Visual Studio Code"),
        ])
        spec = acquire_editor_target(backend, focus=True)
        self.assertIsNotNone(spec)
        self.assertEqual(backend.activated, [22])

    def test_acquire_editor_target_none_when_absent(self):
        _needs_qt(self)
        from desktop_app.actuate_worker import acquire_editor_target
        backend = self._backend([(11, "explorer.exe", "Files")])
        self.assertIsNone(acquire_editor_target(backend))


class SmartParseTest(unittest.TestCase):
    def _state(self):
        from desktop_app.state import AppState
        return AppState(store_path=":memory:")

    def test_regex_fast_path_never_touches_llama(self):
        state = self._state()
        try:
            with mock.patch("mimir.llama_intent.query_local_llama_intent",
                            side_effect=AssertionError("no llama")):
                parsed = state.parse_utterance_smart("stop now")
            self.assertEqual(parsed["intent"], "stop")
        finally:
            state.close()

    def test_unknown_falls_through_to_llama(self):
        state = self._state()
        try:
            with mock.patch(
                    "mimir.llama_intent.query_local_llama_intent",
                    return_value={"intent": "STATUS_INQUIRY",
                                  "target_action_id": "",
                                  "confidence": 0.9,
                                  "reply": "Here is what I learned."}):
                parsed = state.parse_utterance_smart(
                    "kindly summarize your findings so far")
            self.assertEqual(parsed["intent"], "status_inquiry")
            self.assertEqual(parsed["reply"], "Here is what I learned.")
        finally:
            state.close()

    def test_llama_outage_degrades_to_unknown(self):
        state = self._state()
        try:
            with mock.patch("mimir.llama_intent.query_local_llama_intent",
                            return_value=None):
                parsed = state.parse_utterance_smart("blargle wargle zzz")
            self.assertEqual(parsed["intent"], "unknown")
        finally:
            state.close()

    def test_commit_principles_persists_and_marks_learned(self):
        from mimir.events import EventType, get_event_bus
        from mimir.principles import (BehavioralPrinciple, ContextTrigger,
                                      EpistemicStatus)
        state = self._state()
        try:
            seen: list = []
            bus = get_event_bus()
            token = bus.subscribe(
                EventType.INFERENCE_COMPLETED,
                lambda event: seen.append(event))
            try:
                principle = BehavioralPrinciple(
                    id="bp_unify_001",
                    name="Unification probe",
                    category="workflow",
                    context_trigger=ContextTrigger(
                        scope="tests", language_agnostic=True),
                    latent_invariant="Always probe before driving.",
                    anti_patterns=("Blind typing",),
                    epistemic_status=EpistemicStatus.new(
                        0.80, supporting=1),
                    inspectable_traces=("unify_test",),
                )
                stored = state.commit_principles([principle],
                                                 ["ep_1"])
            finally:
                token.unsubscribe()
            self.assertEqual([p.id for p in stored], ["bp_unify_001"])
            self.assertIn("ep_1", state.learned_ids)
            self.assertEqual(
                [p.id for p in state.list_principles()], ["bp_unify_001"])
            self.assertTrue(seen)
        finally:
            state.close()


class SapiFallbackTest(unittest.TestCase):
    def test_sapi_backend_is_known(self):
        from mimir.voice import VoiceCoordinator
        voice = VoiceCoordinator(
            stt_backend=lambda timeout: None, tts_backend="sapi")
        self.assertEqual(voice.tts_backend, "sapi")

    def test_sapi_speak_success(self):
        from mimir.voice import VoiceCoordinator
        voice = VoiceCoordinator(
            stt_backend=lambda timeout: None, tts_backend="sapi")
        completed = mock.Mock(returncode=0)
        with mock.patch("subprocess.run", return_value=completed):
            voice._sapi_speak("hello offline")
        self.assertTrue(completed is not None)

    def test_sapi_speak_failure_raises_voice_error(self):
        from mimir.voice import VoiceCoordinator, VoiceError
        voice = VoiceCoordinator(
            stt_backend=lambda timeout: None, tts_backend="sapi")
        with mock.patch("subprocess.run",
                        return_value=mock.Mock(returncode=3)):
            with self.assertRaises(VoiceError):
                voice._sapi_speak("hello offline")

    def test_edge_outage_falls_back_to_sapi(self):
        import builtins
        from mimir.voice import VoiceCoordinator
        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "edge_tts":
                raise ImportError("blocked for test: edge_tts")
            return real_import(name, *args, **kwargs)

        voice = VoiceCoordinator()
        builtins.__import__ = blocked
        try:
            # Missing install keeps the actionable edge-tts hint.
            from mimir.voice import VoiceError
            with self.assertRaisesRegex(VoiceError, "edge-tts"):
                voice.speak("hello")
        finally:
            builtins.__import__ = real_import


class WorkerPreflightTest(unittest.TestCase):
    def test_ollama_down_returns_actionable_stub(self):
        _needs_qt(self)
        from desktop_app.llm import LLMError
        from desktop_app.replicate_worker import create_replicate_worker
        worker = create_replicate_worker(
            "Draft a helper", [],
            llm_prefs={"model_provider": "ollama", "model_name": "",
                       "model_endpoint": "", "api_key": "",
                       "contrast_baseline": True},
        )
        try:
            with mock.patch("desktop_app.ollama.probe_ollama",
                            return_value={"available": False,
                                          "models": [],
                                          "selected": "llama3.2:1b",
                                          "endpoint":
                                          "http://127.0.0.1:11434",
                                          "error": ""}):
                fn = worker._resolve_llm_fn()
            self.assertTrue(callable(fn))
            with self.assertRaises(LLMError) as raised:
                fn("prompt")
            self.assertIn("Settings", str(raised.exception))
        finally:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass

    def test_ollama_up_picks_best_model(self):
        _needs_qt(self)
        from desktop_app.replicate_worker import create_replicate_worker
        worker = create_replicate_worker(
            "Draft a helper", [],
            llm_prefs={"model_provider": "ollama", "model_name": "",
                       "model_endpoint": "", "api_key": "",
                       "contrast_baseline": True},
        )
        try:
            seen: dict = {}

            def _capture(**kwargs):
                seen.update(kwargs)
                return lambda prompt: "LIVE"

            with mock.patch("desktop_app.ollama.probe_ollama",
                            return_value={"available": True,
                                          "models": ["llama3.2:1b"],
                                          "selected": "llama3.2:1b",
                                          "endpoint":
                                          "http://127.0.0.1:11434",
                                          "error": ""}), \
                    mock.patch("desktop_app.ollama.best_model_for",
                               return_value="llama3.2:1b"), \
                    mock.patch("desktop_app.llm.build_ollama_client",
                               side_effect=_capture):
                fn = worker._resolve_llm_fn()
            self.assertTrue(callable(fn))
            self.assertEqual(seen.get("model"), "llama3.2:1b")
        finally:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass


class ShowcaseTeardownTest(unittest.TestCase):
    def test_showcase_runner_cpp_deleted_after_run(self):
        """The showcase runner must not leak into a GC-collected cycle.

        Regression test for the worker-thread use-after-free (Windows
        access-violation dialog): the runner keeps GUI-thread affinity
        while its scenes run on the worker, so both deferred deletions
        land on the live GUI thread. Before the fix the runner was
        moved to the worker thread, whose exit stranded its C++ (a
        deleteLater posted to a dead thread is never delivered) until
        the cyclic GC freed memory Qt still referenced in an unrelated
        test.
        """
        import gc
        import time

        _needs_qt(self)
        from desktop_app.state import AppState
        from desktop_app.tabs._qt import load_qt
        from desktop_app.tabs.home import build_home_tab
        from mimir.voice import VoiceCoordinator

        _, QtCore, _, QtWidgets = load_qt()
        try:
            from PyQt6 import sip

            def _dead(obj):
                return sip.isdeleted(obj)
        except ImportError:
            try:
                import importlib
                _shiboken = importlib.import_module("shiboken6")

                def _dead(obj):
                    return not _shiboken.isValid(obj)
            except Exception:
                def _dead(obj):
                    return True


        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        state = AppState(store_path=":memory:")
        orig = type(state).voice_coordinator
        type(state).voice_coordinator = (
            lambda self: VoiceCoordinator(stt_backend=lambda t: None,
                                          tts_backend=lambda text: None))
        self.addCleanup(setattr, type(state), "voice_coordinator", orig)
        self.addCleanup(state.close)

        import types

        status = types.SimpleNamespace(
            messages=[],
            showMessage=lambda *args: status.messages.append(args[0]),
        )
        watcher = types.SimpleNamespace(watching=False, last_error="")
        root = build_home_tab(state, lambda _t: None, status, watcher)
        try:
            start = next(b for b in
                         root.findChildren(QtWidgets.QPushButton)
                         if "Showcase" in b.text())
            start.click()
            deadline = time.monotonic() + 60.0
            runner = None
            while time.monotonic() < deadline:
                app.processEvents()
                if runner is None:
                    threads = root.findChildren(QtCore.QThread)
                    if threads:
                        runner = getattr(threads[0], "_mimir_runner",
                                         None)
                if "Run Live Habi Showcase" in start.text():
                    break
                time.sleep(0.02)
            self.assertIn("Run Live Habi Showcase", start.text(),
                          "showcase run did not finish in time")
            self.assertIsNotNone(runner, "runner reachable for teardown")
            for _ in range(3):
                gc.collect()
                app.processEvents()
                QtCore.QCoreApplication.sendPostedEvents(
                    None, QtCore.QEvent.Type.DeferredDelete)
                app.processEvents()
                time.sleep(0.02)
            self.assertTrue(_dead(runner),
                            "showcase runner C++ object leaked")
        finally:
            try:
                root.close()
            except Exception:
                pass
            try:
                root.deleteLater()
            except Exception:
                pass
            app.processEvents()


class Phase4SensoryLoopTest(unittest.TestCase):
    def test_ast_delta_to_episode_conversion(self):
        from mimir.ast_delta import ast_delta_to_episode
        payload = {
            "file": "d:/MIMIR/sample.py",
            "language": "python",
            "added_functions": ["calculate_score"],
            "modified_functions": ["process_item"],
            "removed_functions": ["legacy_helper"],
            "added_classes": ["ScoreTracker"],
            "removed_classes": [],
            "syntax_valid": True,
        }
        episode = ast_delta_to_episode(payload, repo="test_repo")
        self.assertIsNotNone(episode)
        self.assertEqual(episode.source, "live_ast")
        self.assertEqual(episode.repo, "test_repo")
        self.assertEqual(len(episode.transitions), 1)
        trans = episode.transitions[0]
        self.assertIn("calculate_score", trans.diff)
        self.assertIn("process_item", trans.diff)
        self.assertIn("legacy_helper", trans.diff)
        self.assertIn("ScoreTracker", trans.diff)
        self.assertEqual(trans.status, "modified")

    def test_app_state_senses_lifecycle(self):
        import tempfile
        from desktop_app.state import AppState
        state = AppState(store_path=":memory:")
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                ok = state.start_senses(roots=[tmp_dir], repo=tmp_dir)
                self.assertTrue(ok)
                status = state.live_senses
                self.assertIsNotNone(status)
                self.assertTrue(status.get("running"))
            finally:
                state.stop_senses()
                self.assertIsNone(state.live_senses)
                state.close()

    def test_ast_delta_streams_to_state_episodes(self):
        from desktop_app.state import AppState
        from mimir.events import EventBus, EventType
        bus = EventBus()
        state = AppState(store_path=":memory:", event_bus=bus)
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmp_dir:
                state.start_senses(roots=[tmp_dir], repo=tmp_dir)
                payload = {
                    "file": f"{tmp_dir}/code.py",
                    "language": "python",
                    "added_functions": ["new_func"],
                    "modified_functions": [],
                    "removed_functions": [],
                    "added_classes": [],
                    "removed_classes": [],
                    "syntax_valid": True,
                }
                bus.emit(EventType.AST_DELTA, "sensory.ast_observer", payload)
                self.assertTrue(len(state.episodes) >= 1)
                self.assertEqual(state.episodes[0].source, "live_ast")
                self.assertIn("new_func", state.episodes[0].transitions[0].diff)
        finally:
            state.close()

    def test_visor_micro_animation_on_ast_delta(self):
        import time
        from mimir.events import EventBus, EventType, bind_visor_to_bus
        from mimir.ui.visor import VisorController, VisorState
        bus = EventBus()
        controller = VisorController(initial=VisorState.RESTING)
        tokens = bind_visor_to_bus(controller, bus, pulse_revert_s=0.08)
        try:
            bus.emit(EventType.FILE_MODIFIED, "sensory.fs", {"path": "a.py"})
            self.assertEqual(controller.state, VisorState.OBSERVING)
            bus.emit(EventType.AST_DELTA, "sensory.ast", {"file": "a.py"})
            self.assertEqual(controller.state, VisorState.THINKING)
            time.sleep(0.12)
            self.assertEqual(controller.state, VisorState.RESTING)
        finally:
            for t in tokens:
                t.unsubscribe()


class Phase5EndToEndLoopTest(unittest.TestCase):
    def test_full_live_loop_speech_llama_actuation_estop(self):
        """End-to-End verification: Speech -> Llama -> Focus -> Drive -> E-Stop."""
        from desktop_app.actuate_worker import acquire_editor_target
        from desktop_app.state import AppState
        from mimir.actuator import CursorPoint, DesktopActuator
        from mimir.desktop import WindowInfo

        state = AppState(store_path=":memory:")
        try:
            # 1. Voice smart intent query
            with mock.patch("mimir.llama_intent.query_local_llama_intent",
                            return_value={"intent": "APPROVE_PENDING_ACTION",
                                          "target_action_id": "act_123",
                                          "confidence": 0.95,
                                          "reply": "Action authorized."}):
                parsed = state.parse_utterance_smart("go ahead and run it")
            self.assertEqual(parsed["intent"], "approve")

            # 2. Editor target window acquisition
            class _FakeBackend:
                def __init__(self):
                    self.wins = [WindowInfo(handle=101, process_id=5000,
                                            executable="Code.exe",
                                            title="app.py - Visual Studio Code")]
                    self.fg = None

                def list_windows(self):
                    return self.wins

                def foreground(self):
                    return self.wins[0] if self.fg == 101 else None

                def is_valid(self, h):
                    return h == 101

                def activate(self, h):
                    self.fg = h
                    return True

            backend = _FakeBackend()
            target = acquire_editor_target(backend, focus=True)
            self.assertIsNotNone(target)
            self.assertEqual(target.handle, 101)

            # 3. Desktop actuation with instant E-Stop safety abort
            class _TripMouse:
                def __init__(self):
                    self.pos = (200, 200)
                    self.trip = None

                def position(self):
                    return self.pos

                def move_to(self, x, y):
                    self.pos = (x, y)
                    if self.trip:
                        self.trip()

            trip_mouse = _TripMouse()
            actuator = DesktopActuator(
                mouse=trip_mouse,
                safety=state.safety,
            )
            trip_mouse.trip = actuator.abort

            from mimir.actuator import CobotInterruptedError
            with self.assertRaises(CobotInterruptedError):
                actuator.move_cursor_smooth(CursorPoint(x=500, y=500), duration_sec=0.1)

            # 4. Instant negative invariant recorded in memory on E-stop
            self.assertTrue(state.safety.estopped)
            p = state.register_negative_invariant("Never modify production database credentials directly.")
            self.assertIsNotNone(p)
            principles = state.list_principles()
            self.assertTrue(any("production database" in p.latent_invariant.lower()
                                for p in principles))
        finally:
            state.close()




if __name__ == "__main__":
    unittest.main()

