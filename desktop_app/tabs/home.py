"""Home cockpit: serif greeting, status card, explore bar, KPIs (spec 5.1)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..presenters import greeting_for_hour
from ..state import AppState
from ._layout import (
    ClickableCard,
    CobotVisorWidget,
    actions_row,
    card,
    elevate,
    functionality_banner,
    overline,
    page,
)
from .observe import clean_observe_error
from ._qt import load_qt

__all__ = ["build_home_tab"]

CHIP_PROMPTS = (
    ("✦ Explain this code", "Explain this code: "),
    ("◫ Plan a feature", "Help me plan a feature: "),
    ("☼ Brainstorm ideas", "Brainstorm ideas for: "),
)


def build_home_tab(state: AppState, navigate: Callable[[str], None],
                   status: Any, watcher: Any) -> Any:
    _, QtCore, _, QtWidgets = load_qt()
    root, layout = page()

    top = QtWidgets.QHBoxLayout()
    top.setSpacing(24)
    hero = QtWidgets.QVBoxLayout()
    hero.setSpacing(6)
    greet = QtWidgets.QLabel("")
    greet.setObjectName("hero_overline")
    name = QtWidgets.QLabel("")
    name.setObjectName("hero_name")
    tagline = QtWidgets.QLabel("")
    tagline.setObjectName("lede")
    tagline.setWordWrap(True)
    hero.addWidget(greet)
    hero.addWidget(name)
    hero.addWidget(tagline)
    top.addLayout(hero, 1)

    # Co-bot Visor and Status Area (Unboxed, airy, and uncluttered)
    status_area = QtWidgets.QWidget()
    status_area.setObjectName("status_area")
    status_area.setStyleSheet("background: transparent; border: 0;")
    sc = QtWidgets.QVBoxLayout(status_area)
    sc.setContentsMargins(0, 0, 0, 0)
    sc.setSpacing(6)

    visor_row = QtWidgets.QHBoxLayout()
    visor_row.setSpacing(12)

    # Personified Cute 3D Spherical Co-bot Visor Face
    visor_face = CobotVisorWidget(width=58, height=48, on_click=lambda: on_watch())
    visor_face.setToolTip("MIMIR Co-bot Visor — Click to toggle observation")
    visor_row.addWidget(visor_face)

    status_text_col = QtWidgets.QVBoxLayout()
    status_text_col.setSpacing(1)
    state_line = QtWidgets.QLabel("")
    state_line.setObjectName("h2")
    context_line = QtWidgets.QLabel("")
    context_line.setObjectName("muted")
    status_text_col.addWidget(state_line)
    status_text_col.addWidget(context_line)
    visor_row.addLayout(status_text_col)
    sc.addLayout(visor_row)

    btn_row = QtWidgets.QHBoxLayout()
    btn_row.setSpacing(8)
    btn_row.addStretch(1)
    companion_btn = QtWidgets.QPushButton("✨ Habi Companion")
    companion_btn.setObjectName("soft")
    companion_btn.setToolTip("Show or hide the floating on-screen Habi companion")

    def on_toggle_companion() -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            visors = [w for w in app.topLevelWidgets() if hasattr(w, "set_follow_mouse")]
            if visors:
                now_vis = not visors[0].isVisible()
                for v in visors:
                    v.setVisible(now_vis)
                state.prefs.floating_cobot = now_vis
                try:
                    state.prefs.save()
                except Exception:
                    pass
                status.showMessage("Floating Habi " + ("active on screen" if now_vis else "hidden"), 3000)
            else:
                try:
                    from mimir.ui.visor import create_visor_widget
                    pill = create_visor_widget(
                        state.visor,
                        auto_roam=state.prefs.auto_roam,
                        follow_mouse=state.prefs.follow_mouse,
                    )
                    pill.show()
                    state.prefs.floating_cobot = True
                    try:
                        state.prefs.save()
                    except Exception:
                        pass
                    status.showMessage("Floating Habi active on screen", 3000)
                except Exception as exc:
                    status.showMessage(f"Could not launch Habi: {exc}", 5000)

    companion_btn.setFixedHeight(34)
    companion_btn.setStyleSheet("background: #FFFFFF; color: #0F172A; border: 1px solid #CBD5E1; border-radius: 8px; padding: 6px 14px; font-weight: 500; font-size: 12px;")
    companion_btn.clicked.connect(on_toggle_companion)
    btn_row.addWidget(companion_btn)
    watch_btn = QtWidgets.QPushButton("")
    watch_btn.setObjectName("start_obs_btn")
    watch_btn.setFixedHeight(34)
    btn_row.addWidget(watch_btn)
    sc.addLayout(btn_row)

    top.addWidget(status_area)
    layout.addLayout(top)

    home_error, home_error_lay = card()
    home_error.setMaximumWidth(700)
    home_error_title = QtWidgets.QLabel("Observation needs attention")
    home_error_title.setObjectName("h2")
    home_error_text = QtWidgets.QLabel("")
    home_error_text.setObjectName("muted")
    home_error_text.setWordWrap(True)
    open_observe_btn = QtWidgets.QPushButton("Open Observe")
    open_observe_btn.setObjectName("ink")
    open_observe_btn.clicked.connect(lambda: navigate("observe"))
    home_error_dismiss = QtWidgets.QPushButton("Dismiss")
    home_error_dismiss.setObjectName("soft")
    home_error_dismiss.clicked.connect(
        lambda: home_error.setVisible(False))
    home_error_lay.addWidget(home_error_title)
    home_error_lay.addWidget(home_error_text)
    home_error_lay.addLayout(
        actions_row(open_observe_btn, home_error_dismiss))
    home_error.setVisible(False)
    layout.addWidget(home_error)

    layout.addWidget(functionality_banner(
        "✦",
        "Habitous Intelligent Developer Companion",
        "Habitous continuously observes how you code, mines invariant behavioral standards into "
        "inspectable principles, and replicates your authentic style when generating new solutions.",
        pills=[("100% On-Device", "confirmed"), ("Continuous Telemetry", "learning"), ("Adaptive Style", "confirmed")],
        icon_cls="icon_box_purple",
    ))

    # 1-click live showcase: the 4 golden scenes on a background thread.
    showcase_row = QtWidgets.QHBoxLayout()
    showcase_row.setSpacing(12)
    showcase_btn = QtWidgets.QPushButton("▶ Run Live Habi Showcase")
    showcase_btn.setObjectName("generate_btn")
    showcase_btn.setFixedHeight(34)
    showcase_btn.setToolTip(
        "Run Habi's 4-scene live demonstration: observe, voice, drive, E-stop.")
    showcase_status = QtWidgets.QLabel(
        "Experience Habi observe, speak, drive, and learn live.")
    showcase_status.setObjectName("muted")
    showcase_row.addWidget(showcase_btn)
    showcase_row.addWidget(showcase_status)
    showcase_row.addStretch(1)
    layout.addLayout(showcase_row)

    showcase_log = QtWidgets.QPlainTextEdit()
    showcase_log.setReadOnly(True)
    showcase_log.setMaximumHeight(85)
    showcase_log.setMaximumWidth(700)
    showcase_log.setPlaceholderText("Live showcase progress appears here.")
    showcase_log.setVisible(False)
    layout.addWidget(showcase_log)

    showcase_progress = QtWidgets.QProgressBar()
    showcase_progress.setRange(0, 4)
    showcase_progress.setValue(0)
    showcase_progress.setTextVisible(False)
    showcase_progress.setFixedHeight(6)
    showcase_progress.setMaximumWidth(700)
    showcase_progress.setVisible(False)
    layout.addWidget(showcase_progress)

    SCENE_STEPS = {"1_observe": 1, "2_voice": 2, "3_drive": 3,
                   "4_estop": 4, "complete": 4}

    explore_pill = QtWidgets.QFrame()
    explore_pill.setObjectName("explore_pill")
    explore_pill.setMaximumWidth(700)
    explore_pill.setFixedHeight(46)
    pill_lay = QtWidgets.QHBoxLayout(explore_pill)
    pill_lay.setContentsMargins(16, 6, 8, 6)
    pill_lay.setSpacing(12)
    sparkle = QtWidgets.QLabel("✦")
    sparkle.setObjectName("faint")
    explore = QtWidgets.QLineEdit()
    explore.setObjectName("explore_input")
    explore.setPlaceholderText("What would you like to explore?")
    explore.setClearButtonEnabled(True)
    mic_btn = QtWidgets.QPushButton("🎙")
    mic_btn.setObjectName("mic_btn")
    mic_btn.setFixedSize(32, 32)
    mic_btn.setToolTip("Speak instead of typing (needs a microphone)")
    pill_lay.addWidget(sparkle)
    pill_lay.addWidget(explore, 1)
    pill_lay.addWidget(mic_btn)
    layout.addWidget(explore_pill)

    chips = QtWidgets.QHBoxLayout()
    chips.setSpacing(8)
    for label, seed in CHIP_PROMPTS:
        chip = QtWidgets.QPushButton(label)
        chip.setObjectName("chip")
        chip.clicked.connect(
            lambda _=False, s=seed: (explore.setText(s),
                                     explore.setFocus()))
        chips.addWidget(chip)
    more = QtWidgets.QPushButton("··· More")
    more.setObjectName("chip")
    more.clicked.connect(lambda: navigate("replicate"))
    chips.addWidget(more)
    chips.addStretch(1)
    ask_btn = QtWidgets.QPushButton("Ask →")
    ask_btn.setObjectName("ink")
    ask_btn.setFixedHeight(32)
    ask_btn.setToolTip("Ask Habi about the text above (Enter)")
    chips.addWidget(ask_btn)
    chips_wrap = QtWidgets.QWidget()
    chips_wrap.setMaximumWidth(700)
    cw_lay = QtWidgets.QHBoxLayout(chips_wrap)
    cw_lay.setContentsMargins(0, 0, 0, 0)
    cw_lay.addLayout(chips)
    layout.addWidget(chips_wrap)

    reply_box = QtWidgets.QFrame()
    reply_box.setObjectName("card")
    reply_box.setMaximumWidth(700)
    reply_box.setVisible(False)
    rl = QtWidgets.QHBoxLayout(reply_box)
    rl.setContentsMargins(14, 10, 14, 10)
    rl.setSpacing(10)
    reply_icon = QtWidgets.QLabel("✦")
    reply_icon.setObjectName("icon_box_purple")
    reply = QtWidgets.QLabel("")
    reply.setObjectName("subtle")
    reply.setWordWrap(True)
    reply_copy = QtWidgets.QPushButton("Copy reply")
    reply_copy.setObjectName("soft")
    reply_copy.setToolTip("Copy this reply to the clipboard")

    stop_speech_btn = QtWidgets.QPushButton("⏹ Stop voice")
    stop_speech_btn.setObjectName("soft")
    stop_speech_btn.setToolTip("Stop Habi from reading aloud")
    stop_speech_btn.setVisible(False)
    stop_speech_btn.clicked.connect(lambda: (state.stop_speaking(), stop_speech_btn.setVisible(False)))

    def on_copy_reply() -> None:
        if reply.text():
            QtWidgets.QApplication.clipboard().setText(reply.text())
            status.showMessage("Reply copied to clipboard.", 4000)

    reply_copy.clicked.connect(on_copy_reply)
    rl.addWidget(reply_icon)
    rl.addWidget(reply, 1)
    rl.addWidget(stop_speech_btn)
    rl.addWidget(reply_copy)
    layout.addWidget(reply_box)

    kpi_row = QtWidgets.QHBoxLayout()
    kpi_row.setSpacing(14)
    kpi_cards: list[Any] = []

    def kpi(icon: str, caption: str, target: str, icon_cls: str = "icon_box_purple") -> Any:
        card_widget = ClickableCard("kpi_card",
                                    on_click=lambda: navigate(target))
        card_widget.setFixedSize(210, 72)
        lay = QtWidgets.QHBoxLayout(card_widget)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)
        glyph = QtWidgets.QLabel(icon)
        glyph.setObjectName(icon_cls)
        text = QtWidgets.QVBoxLayout()
        text.setSpacing(2)
        number = QtWidgets.QLabel("0")
        number.setObjectName("kpi_number")
        cap = QtWidgets.QLabel(caption)
        cap.setObjectName("muted")
        text.addWidget(number)
        text.addWidget(cap)
        lay.addWidget(glyph)
        lay.addLayout(text, 1)
        kpi_cards.append(number)
        return card_widget

    layout.addWidget(overline("WORKSPACE OVERVIEW"))
    kpi_row.addWidget(kpi("📖", "Habits learned", "memory", "icon_box_purple"))
    kpi_row.addWidget(kpi("◉", "Sessions watched", "observe", "icon_box_blue"))
    kpi_row.addWidget(kpi("📈", "Confidence score", "memory", "icon_box_green"))
    kpi_row.addStretch(1)
    layout.addLayout(kpi_row)

    layout.addWidget(overline("WHAT WOULD YOU LIKE TO DO?"))
    dir_row = QtWidgets.QHBoxLayout()
    dir_row.setSpacing(12)

    def directory(icon: str, title: str, sub: str, target: str,
                 icon_cls: str = "icon_box_purple") -> Any:
        card_widget = ClickableCard("dir_card",
                                    on_click=lambda: navigate(target))
        card_widget.setMinimumHeight(84)
        lay = QtWidgets.QHBoxLayout(card_widget)
        lay.setContentsMargins(14, 10, 12, 10)
        lay.setSpacing(10)
        glyph = QtWidgets.QLabel(icon)
        glyph.setObjectName(icon_cls)
        text = QtWidgets.QVBoxLayout()
        text.setSpacing(2)
        head = QtWidgets.QLabel(title)
        head.setObjectName("h2")
        desc = QtWidgets.QLabel(sub)
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        text.addWidget(head)
        text.addWidget(desc)
        chevron = QtWidgets.QLabel(">")
        chevron.setObjectName("faint")
        lay.addWidget(glyph)
        lay.addLayout(text, 1)
        lay.addWidget(chevron)
        return card_widget

    dir_row.addWidget(directory("👁", "Observe",
                                "Watch repos, learn your habits.",
                                "observe", "icon_box_blue"))
    dir_row.addWidget(directory("📖", "Memory",
                                "Your standards, inspectable.",
                                "memory", "icon_box_purple"))
    dir_row.addWidget(directory("⧉", "Replicate",
                                "Apply your style to new tasks.",
                                "replicate", "icon_box_green"))
    dir_row.addWidget(directory("🛡", "Trust",
                                "Stays local, you're in control.",
                                "trust", "icon_box_amber"))
    layout.addLayout(dir_row)
    layout.addStretch(1)

    # Live worker refs (showcase + voice): kept alive for their lifetime.
    _workers: list[Any] = []
    _showcase: dict[str, Any] = {"thread": None, "runner": None}

    def refresh_content() -> None:
        greet.setText(greeting_for_hour(datetime.now().hour))
        name.setText(state.prefs.user_name or "there")
        tagline.setText(
            f"I'm {state.prefs.assistant_name}. I observe how you work, "
            "learn your style, and apply it when you need me.")
        if watcher.watching:
            state_line.setText("Observing")
            context_line.setText(
                f"Watching {Path(state.prefs.last_repo).name if state.prefs.last_repo else 'workspace'}")
            watch_btn.setText("⏹ Stop Observing")
            watch_btn.setStyleSheet(
                "background: #DC2626; color: white; border: 0; border-radius: 8px; "
                "padding: 6px 14px; font-weight: 600; font-size: 12px; min-height: 20px;")
            visor_face.set_state("observing")
        else:
            state_line.setText("Resting")
            context_line.setText("Ready to observe")
            watch_btn.setText("▷ Start Observing")
            watch_btn.setStyleSheet(
                "background: #4F46E5; color: white; border: 0; border-radius: 8px; "
                "padding: 6px 14px; font-weight: 600; font-size: 12px; min-height: 20px;")
            visor_face.set_state("resting")
        try:
            principles = state.list_principles()
        except Exception:
            principles = []
        stats = state.memory_stats() if principles else {
            "count": 0, "avg_confidence": 0.0}
        kpi_cards[0].setText(str(stats["count"]))
        kpi_cards[1].setText(str(len(state.episodes)))
        kpi_cards[2].setText(f"{stats['avg_confidence']:.2f}")
        try:
            watch_btn.updateGeometry()
        except Exception:
            pass
        try:
            app_inst = QtWidgets.QApplication.instance()
            pills = (app_inst.topLevelWidgets() if app_inst is not None
                     else [])
            floating = [w for w in pills
                        if hasattr(w, "set_follow_mouse")]
            shown = bool(floating) and floating[0].isVisible()
            companion_btn.setText("Hide Habi" if shown
                                  else "✨ Habi Companion")
        except Exception:
            pass

    def on_watch() -> None:
        if watcher.watching:
            watcher.stop()
            home_error.setVisible(False)
            refresh_content()
            status.showMessage("Observation paused. Habi is resting.", 4000)
            return
        repo = state.prefs.last_repo or str(Path.cwd().resolve())
        roots = list(state.prefs.active_roots(state.default_roots()))
        try:
            repo_resolved = str(Path(repo).resolve())
            if repo_resolved not in roots:
                roots.append(repo_resolved)
            if repo_resolved not in state.prefs.last_roots:
                state.prefs.last_roots = state.prefs.last_roots + (repo_resolved,)
                state.prefs.save()
        except Exception:
            if repo not in roots:
                roots.append(repo)
        # Prefer the non-blocking first pass (the UI never freezes
        # on a slow repo); stub watchers in tests only implement start().
        def _failed_start(message: str) -> None:
            home_error_text.setText(clean_observe_error(message))
            home_error.setVisible(True)
            status.showMessage(
                f"Couldn't start observing: {message}", 8000)

        start_async = getattr(watcher, "start_async", None)
        if start_async is None:
            ok, message = watcher.start(repo, roots)
            if not ok:
                _failed_start(message)
            else:
                home_error.setVisible(False)
                status.showMessage(
                    "Habitous active observation started for "
                    f"{Path(repo).name}.", 4000)
            refresh_content()
            return

        def _started(ok: bool, message: str) -> None:
            if not ok:
                _failed_start(message)
            else:
                home_error.setVisible(False)
                status.showMessage(
                    "Habitous active observation started for "
                    f"{Path(repo).name}.", 4000)
            watch_btn.setEnabled(True)
            refresh_content()

        watch_btn.setEnabled(False)
        watch_btn.setText("Starting…")
        try:
            watch_btn.updateGeometry()
        except Exception:
            pass
        try:
            visor_face.set_state("thinking")
        except Exception:
            pass
        status.showMessage("Starting observation…", 4000)
        start_async(repo, roots, 10, _started)

    def _speak_answer(answer: str) -> None:
        """Speak a companion reply aloud without blocking the UI."""
        state.stop_speaking()
        spoken = answer.split("[Extended Technical Breakdown]")[0].strip()
        spoken = spoken.replace("•", "").replace("✦", "").strip()
        if not spoken:
            return
        try:
            from ..voice_worker import create_speak_worker
        except ImportError:
            return
        try:
            worker = create_speak_worker(state.voice_coordinator(), spoken,
                                         parent=root)
        except (ValueError, Exception):
            return
        _workers.append(worker)
        state._active_speak_worker = worker

        stop_speech_btn.setVisible(True)

        def _started() -> None:
            try:
                visor_face.set_state("listening")
            except Exception:
                pass
            stop_speech_btn.setVisible(True)

        def _over() -> None:
            stop_speech_btn.setVisible(False)
            try:
                _workers.remove(worker)
            except ValueError:
                pass
            try:
                worker.deleteLater()
            except Exception:
                pass
            refresh_content()

        def _failed(message: str) -> None:
            stop_speech_btn.setVisible(False)
            status.showMessage(f"Speech unavailable: {message}", 6000)
            _over()

        worker.speak_started.connect(_started)
        worker.speak_finished.connect(_over)
        worker.speak_error.connect(_failed)
        worker.speak_cancelled.connect(_over)
        worker.start()

    def _render_answer(answer: str) -> None:
        state.stop_speaking()
        reply.setText(f"{state.prefs.assistant_name}:\n{answer}")
        reply_box.setVisible(True)
        status.showMessage("Habi answered.", 4000)
        _speak_answer(answer)

    def _memory_fallback(text: str) -> str:
        hits = state.search(text, top_k=2, min_confidence=0.0)
        if hits:
            habits_desc = "; ".join(h.name for h in hits)
            return f"Relevant habits in your memory: {habits_desc}. Head to the Replicate tab to apply them to this task."
        return f"Habi is active and learning from your workspace. Ask me to explain code, plan a feature, or run Replicate to draft solutions."

    def _answer(intent: str, text: str, llama_reply: Any = None) -> None:
        # respond() always runs: it owns the stop E-stop latch and the
        # approval binding. Llama's phrasing only rewords the terse
        # control replies (stop/sleep); knowledge and approval answers
        # keep the companion wording with their live outcomes.
        answer = state.respond(intent, text)
        if llama_reply and intent in ("stop", "sleep"):
            answer = str(llama_reply)
        _render_answer(answer)

    def on_ask() -> None:
        state.stop_speaking()
        text = explore.text().strip()
        if not text:
            status.showMessage("Type something to explore first.", 4000)
            explore.setFocus()
            return
        parsed = state.parse_utterance(text)
        if parsed.get("intent") and parsed["intent"] not in ("unknown", None):
            _answer(parsed["intent"], parsed["text"])
            return
        # Unknown to the keyword parser: consult the local Llama
        # intent parser off the UI thread, then answer or fall back
        # to the memory search.
        provider = (getattr(state.prefs, "model_provider", "") or "").strip().lower()
        if provider in ("offline", "", "none"):
            _render_answer(_memory_fallback(text))
            return
        try:
            from ..observe_worker import create_callable_worker
        except ImportError:
            _render_answer(_memory_fallback(text))
            return
        ask_btn.setEnabled(False)
        try:
            visor_face.set_state("thinking")
        except Exception:
            pass
        status.showMessage("Habi is thinking…", 4000)
        worker = create_callable_worker(
            state.parse_utterance_smart, (text,), {"timeout_s": 4.0},
            parent=root)
        _workers.append(worker)

        def _release_ask_worker() -> None:
            ask_btn.setEnabled(True)
            try:
                _workers.remove(worker)
            except ValueError:
                pass
            try:
                worker.deleteLater()
            except Exception:
                pass
            refresh_content()

        def _smart_done(smart: object) -> None:
            _release_ask_worker()
            data = smart if isinstance(smart, dict) else {}
            intent = data.get("intent") or "unknown"
            if intent not in ("unknown", None, ""):
                _answer(str(intent), str(data.get("text", text)),
                        data.get("reply"))
            else:
                _render_answer(_memory_fallback(text))

        def _smart_failed(message: str) -> None:
            _release_ask_worker()
            _render_answer(_memory_fallback(text))

        def _smart_cancelled() -> None:
            _release_ask_worker()
            status.showMessage("Question cancelled.", 4000)

        worker.callable_finished.connect(_smart_done)
        worker.callable_error.connect(_smart_failed)
        worker.callable_cancelled.connect(_smart_cancelled)
        worker.start()

    def on_mic() -> None:
        state.stop_speaking()
        if getattr(mic_btn, "_is_listening", False):
            worker = getattr(mic_btn, "_active_worker", None)
            if worker is not None:
                worker.cancel()
            _reset_mic()
            status.showMessage("Voice listening cancelled.", 3000)
            return

        mic_btn._is_listening = True
        mic_btn.setText("⏹")
        mic_btn.setStyleSheet("background-color: #EF4444; color: #FFFFFF; border-radius: 16px; font-weight: bold;")
        mic_btn.setToolTip("Listening... Click to stop")
        prev_placeholder = explore.placeholderText()
        explore.setPlaceholderText("🎙️ Listening to your voice... Speak now.")
        status.showMessage("Listening… speak now.", 6000)
        try:
            visor_face.set_state("listening")
        except Exception:
            pass

        def _reset_mic() -> None:
            mic_btn._is_listening = False
            mic_btn._active_worker = None
            mic_btn.setText("🎙")
            mic_btn.setStyleSheet("")
            mic_btn.setToolTip("Speak instead of typing (needs a microphone)")
            explore.setPlaceholderText(prev_placeholder)
            try:
                visor_face.set_state("observing")
            except Exception:
                pass

        try:
            from ..voice_worker import create_listen_worker
        except ImportError:
            ok, heard = state.try_listen(timeout_sec=6.0)
            _done(ok, heard)
            return

        worker = create_listen_worker(state.voice_coordinator(),
                                      timeout_sec=6.0, parent=root)
        mic_btn._active_worker = worker
        _workers.append(worker)

        def _done(ok: bool, heard: str) -> None:
            _reset_mic()
            if ok:
                explore.setText(heard)
                explore.setFocus()
                status.showMessage(f"Heard: '{heard}'", 4000)
                on_ask()
            else:
                status.showMessage(f"Microphone: {heard}", 8000)
            try:
                _workers.remove(worker)
            except ValueError:
                pass
            try:
                worker.deleteLater()
            except Exception:
                pass
            refresh_content()

        worker.listen_finished.connect(_done)
        worker.listen_cancelled.connect(_reset_mic)
        worker.start()

    def on_showcase_log(text: str) -> None:
        low = text.lower()
        # Filter out internal/debug warnings so user sees clean, high-value progress
        if any(ign in low for ign in (
            "tts unavailable", "speech note", "live backends unavailable",
            "simulated glide", "git status note", "no trip:", "observe note"
        )):
            return

        cleaned = text
        for tag, rep in [
            ("[1_observe] Silent observation — ingesting commits.", "👁️ Step 1 · Silent Observation — Ingesting workspace commits..."),
            ("[2_voice] Voice coordination — reporting learned habits.", "🎙️ Step 2 · Voice Coordination — Reporting learned coding style..."),
            ("[3_drive] Compliant driving — gliding and typing.", "⚡ Step 3 · Autopilot Driving — Demonstrating cursor glide and keyboard typing..."),
            ("[4_estop] E-stop drill — human override correction.", "🛡️ Step 4 · Safety Override — Testing emergency stop and learning from human correction..."),
            ("MIMIR:", "Habi:"),
            ("Showcase complete.", "✓ Showcase complete — New principles are now saved in Memory."),
        ]:
            cleaned = cleaned.replace(tag, rep)

        showcase_log.setVisible(True)
        showcase_log.appendPlainText(cleaned)

    def on_showcase_scene(scene: str, explanation: str) -> None:
        clean_exp = explanation.replace("MIMIR", "Habi")
        showcase_status.setText(clean_exp)
        status.showMessage(f"Showcase: {clean_exp}", 5000)
        step = SCENE_STEPS.get(scene)
        if step is not None:
            showcase_progress.setValue(step)

    def on_showcase_visor(state_name: str) -> None:
        try:
            visor_face.set_state(state_name)
        except Exception:
            pass

    def on_showcase_done(success: bool) -> None:
        # Break the thread → runner link deterministically so the
        # runner's teardown never depends on cyclic-GC timing.
        _done_thread = _showcase.get("thread")
        if _done_thread is not None:
            try:
                _done_thread._mimir_runner = None
            except Exception:
                pass
        showcase_btn.setEnabled(True)
        showcase_btn.setText("▶ Run Live Habi Showcase")
        try:
            showcase_btn.updateGeometry()
        except Exception:
            pass
        if success:
            showcase_progress.setValue(4)
        showcase_status.setText(
            "Showcase complete — Habi's new principles are in Memory."
            if success else "Showcase stopped early — see activity details.")
        refresh_content()
        status.showMessage(
            "Showcase complete — see Memory for new principles."
            if success else "Showcase stopped early — see log.", 8000)
        thread = _showcase.get("thread")
        if thread is not None:
            try:
                thread.quit()
                thread.wait(3000)
            except Exception:
                pass
        _showcase["thread"] = None
        _showcase["runner"] = None

    def on_showcase() -> None:
        runner = _showcase.get("runner")
        if _showcase.get("thread") is not None and runner is not None:
            try:
                runner.cancel()
            except Exception:
                pass
            showcase_btn.setEnabled(False)
            showcase_btn.setText("■ Stopping…")
            showcase_status.setText("Stopping the showcase…")
            status.showMessage("Stopping showcase…", 3000)
            return
        from ..showcase import ShowcaseRunner
        showcase_btn.setText("■ Stop showcase")
        try:
            showcase_btn.updateGeometry()
        except Exception:
            pass
        showcase_log.clear()
        showcase_log.setVisible(True)
        showcase_progress.setValue(0)
        showcase_progress.setVisible(True)
        showcase_status.setText("Running the 4 golden scenes…")
        runner = ShowcaseRunner(state, speak_live=True)
        thread = QtCore.QThread(root)
        thread._mimir_runner = runner  # found by MainWindow.shutdown
        # The runner deliberately keeps GUI-thread affinity: the scenes
        # already execute on the worker (via the started lambda below)
        # and its signals queue to the tab slots from any thread, while
        # moving it to the worker strands its C++ on a dead thread at
        # teardown (deleteLater never delivered → use-after-free in an
        # unrelated test's GC pass). Both deferred deletions below land
        # on the live GUI thread.
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(runner.deleteLater)
        thread.started.connect(lambda: runner.run_all())
        runner.scene_changed.connect(on_showcase_scene)
        runner.visor_state_requested.connect(on_showcase_visor)
        runner.log_message.connect(on_showcase_log)
        runner.showcase_completed.connect(on_showcase_done)
        _showcase["thread"] = thread
        _showcase["runner"] = runner
        thread.start()

    live_timer = QtCore.QTimer(root)
    live_timer.setInterval(3000)

    def _live_tick() -> None:
        if watcher.watching:
            refresh_content()

    live_timer.timeout.connect(_live_tick)
    live_timer.start()

    watch_btn.clicked.connect(on_watch)
    explore.returnPressed.connect(on_ask)
    ask_btn.clicked.connect(on_ask)
    mic_btn.clicked.connect(on_mic)
    showcase_btn.clicked.connect(on_showcase)
    root.refresh_content = refresh_content  # called by the shell on navigate
    refresh_content()
    return root
