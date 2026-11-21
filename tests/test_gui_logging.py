"""GUI logging keeps Debug metadata and colors without visible prefixes."""

import queue
import unittest
from unittest.mock import Mock, patch

import ai_player
import game_core as core
import main
from tests.test_controller_core import scenario
from tests.test_tkinter import FakeRoot, FakeWidget, new_game


class FakeText:
    def __init__(self):
        self.insertions = []
        self.state = None
        self.scroll = None

    def config(self, **kwargs):
        self.state = kwargs.get("state", self.state)

    def delete(self, *args):
        self.insertions.clear()

    def insert(self, position, text, tag):
        self.insertions.append((text, tag))

    def see(self, position):
        self.scroll = position


def logging_gui(debug=True):
    gui = main.GUI.__new__(main.GUI)
    gui.debug_mode = debug
    gui.print_queue = queue.Queue()
    gui.root = FakeRoot()
    gui.game = None
    gui.max_turn_logs = 10
    gui.log_turns = []
    gui.current_turn_log = None
    gui.log_text = FakeText()
    return gui


def display_gui(game):
    """Prepare the real GUI update method using in-memory label/value substitutes."""
    gui = logging_gui()
    for name in ("player_cards", "ai_cards", "turn_label", "deck_label", "bomb_label",
                 "mode_label", "player_status", "ai_status", "draw_button", "play_button"):
        setattr(gui, name, FakeWidget())
    gui.player_cards_var = Mock()
    gui.ai_cards_var = Mock()
    gui.root.update = Mock()
    gui.game = game
    game.gui = gui
    return gui


class GuiLoggingTests(unittest.TestCase):
    def test_print_queues_debug_metadata_without_changing_visible_message(self):
        gui = logging_gui()
        gui.print("AI 决策：抽牌", debug=True)
        gui.print("玩家抽牌")
        self.assertEqual(("AI 决策：抽牌", True, "end", 0.2), gui.print_queue.get_nowait())
        self.assertEqual(("玩家抽牌", False, "end", 0.2), gui.print_queue.get_nowait())
        self.assertTrue(gui.print_queue.empty())

    def test_normal_mode_filters_debug_messages(self):
        gui = logging_gui(debug=False)
        gui.print("AI牌堆记忆：? 炸 ?", debug=True)
        gui.print("玩家抽牌")
        self.assertEqual(("玩家抽牌", False, "end", 0.2), gui.print_queue.get_nowait())
        self.assertTrue(gui.print_queue.empty())

    def test_debug_mode_console_notice_has_no_visible_prefix(self):
        gui = logging_gui(debug=False)
        gui.update_gui = lambda: None
        with patch("main.messagebox.showinfo") as notice, patch("builtins.print") as console:
            gui.toggle_debug_mode()
        self.assertTrue(gui.debug_mode)
        console.assert_called_once_with("Debug模式开启")
        notice.assert_called_once_with("Debug模式", "Debug模式开启")

    def test_ingestion_preserves_per_line_debug_metadata(self):
        gui = logging_gui()
        gui._ingest_log_message("AI 决策：抽牌\n搜索：16次/12ms", debug=True)
        gui._ingest_log_message("正常对局日志")
        lines = gui.current_turn_log["blocks"][-1]
        self.assertEqual(["AI 决策：抽牌", "搜索：16次/12ms", "正常对局日志"], lines)
        self.assertEqual([True, True, False], [getattr(line, "debug", False) for line in lines])
        self.assertTrue(all(isinstance(line, str) for line in lines))
        self.assertTrue(all("[Debug]" not in line for line in lines))

    def test_queue_processing_carries_debug_flag_into_rendered_style(self):
        gui = logging_gui()
        gui.print("AI 决策：抽牌", debug=True)
        gui.print("正常对局日志")
        gui._process_print_queue()
        self.assertTrue(gui.print_queue.empty())
        lines = gui.current_turn_log["blocks"][-1]
        self.assertEqual([True, False], [getattr(line, "debug", False) for line in lines])
        entries = gui.log_text.insertions
        self.assertIn(("  │ AI 决策：抽牌\n", "debug_body"), entries)
        self.assertIn(("  │ 正常对局日志\n", "system_body"), entries)
        self.assertEqual("disabled", gui.log_text.state)
        self.assertEqual("end", gui.log_text.scroll)
        self.assertTrue(gui.root.callbacks)
        self.assertTrue(all("[Debug]" not in text for text, _ in entries))

    def test_all_role_renderers_use_debug_metadata_and_keep_normal_colors(self):
        for role in ("system", "end", "player", "ai"):
            with self.subTest(role=role):
                gui = logging_gui()
                gui._start_turn_log(role, "回合标题")
                gui._ingest_log_message("搜索：16次/12ms", debug=True)
                gui._ingest_log_message("正常对局日志")
                gui._render_structured_logs()
                self.assertIn(("  │ 搜索：16次/12ms\n", "debug_body"), gui.log_text.insertions)
                self.assertIn(("  │ 正常对局日志\n", f"{role}_body"), gui.log_text.insertions)
                self.assertTrue(all("[Debug]" not in text for text, _ in gui.log_text.insertions))

    def test_ai_alter_pending_phase_hides_probability_even_when_deck_is_empty(self):
        C = core.Card
        for choice, depth in ((C.ALTER3, 3), (C.ALTER5, 5)):
            with self.subTest(depth=depth):
                state = scenario([C.DEFUSE], [C.DEFUSE, choice], top=[C.BOMB] * 4, current=1)
                state.discard.extend(state.deck[4:])
                state.deck = state.deck[:4]
                state.known = [[None] * 4, [None] * 4]
                state.check_invariants()
                game = new_game()
                game.core = state
                game._sync_from_core()
                gui = display_gui(game)
                gui.update_gui()
                self.assertEqual("💣 100.0%", gui.bomb_label.settings["text"])
                pending = []

                def capture(game, kind, visible, callback):
                    self.assertEqual("Arrange", kind)
                    game._ai_pending = True
                    pending.append(callback)

                card = next(card for card in game.ai.hand if ai_player.card_to_wire(card) == core.card_to_wire(choice))
                with patch("ai_player.begin_private_choice", capture):
                    self.assertTrue(game.play_card(game.ai, card))
                self.assertEqual("Arrange", game.core.phase)
                self.assertTrue(game._ai_pending)
                self.assertEqual(max(0, 4 - depth), len(game.core.deck))
                self.assertEqual("💣 —", gui.bomb_label.settings["text"])
                self.assertEqual("gray", gui.bomb_label.settings["foreground"])
                gui.root.update.assert_called()
                game.core.check_invariants()

                order = [core.card_to_wire(card) for card in game.core.phase_cards]
                game._ai_pending = False
                pending[0]({"kind": "Order", "cards": order})
                self.assertEqual("Play", game.core.phase)
                self.assertEqual(4, len(game.core.deck))
                self.assertEqual("💣 100.0%", gui.bomb_label.settings["text"])
                game.core.check_invariants()

    def test_empty_deck_gui_update_uses_placeholder_without_division(self):
        game = new_game()
        game.core.discard.extend(game.core.deck)
        game.core.deck.clear()
        game.core.known = [[], []]
        game.core.winner = 1
        game._sync_from_core()
        game.core.check_invariants()
        gui = display_gui(game)
        gui.update_gui()
        self.assertEqual("💣 —", gui.bomb_label.settings["text"])
        gui.root.update.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
