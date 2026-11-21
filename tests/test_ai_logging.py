"""AI diagnostics use separate readable lines and only the frozen observation."""

from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

import ai_player
import cards
import game_core as core
import main
import ai_backend
from tests.test_controller_core import scenario
from tests.test_tkinter import new_game


WIRE_CARDS = {
    "Bomb": cards.BombCatCard, "Defuse": cards.DefuseCard,
    "Nope": cards.NopeCard, "Attack": cards.AttackCard,
    "PersonalAttack": cards.PersonalAttackCard, "Skip": cards.SkipCard,
    "SuperSkip": cards.SuperSkipCard, "Shuffle": cards.ShuffleCard,
    "See3": lambda: cards.SeeFutureCard(3), "See5": lambda: cards.SeeFutureCard(5),
    "Alter3": lambda: cards.AlterFutureCard(3), "Alter5": lambda: cards.AlterFutureCard(5),
    "Bottom": cards.DrawBottomCard, "Swap": cards.SwapCard,
}


def diagnostic_result(action=None, *, iterations=16):
    return {
        "action": action or {"kind": "Draw"}, "iterations": iterations,
        "elapsed_ms": 12,
        "selection": "most_visited" if iterations else "heuristic_fallback",
        "candidates": [
            {"action": action or {"kind": "Draw"}, "visits": iterations, "value": 0.75 if iterations else None},
            {"action": {"kind": "Play", "card": "Skip"}, "visits": 0, "value": None},
        ],
    }


def debug_lines(game):
    return [message for message, options in game.gui.messages if options.get("debug")]


class DiagnosticsFormatTests(unittest.TestCase):
    def test_all_fourteen_variants_reuse_original_short_name_helper(self):
        game = new_game()
        original = game._card_short_name
        game._card_short_name = Mock(side_effect=original)
        for key, factory in WIRE_CARDS.items():
            with self.subTest(card=key):
                self.assertEqual(original(factory()), ai_player._short_wire_name(game, key))
        self.assertEqual(14, game._card_short_name.call_count)
        self.assertEqual(list(WIRE_CARDS), [ai_player.card_to_wire(call.args[0])
                                          for call in game._card_short_name.call_args_list])

    def test_action_labels_preserve_private_order_and_top_based_positions(self):
        game = new_game()
        self.assertIn("抽牌", ai_player._action_text(game, {"kind": "Draw"}))
        self.assertIn("预5", ai_player._action_text(game, {"kind": "Play", "card": "See5"}))
        self.assertIn("1", ai_player._action_text(game, {"kind": "Replace", "position": 0}))
        self.assertIn("6", ai_player._action_text(game, {"kind": "Replace", "position": 5}))
        text = ai_player._action_text(game, {"kind": "Order", "cards": ["Bomb", "Defuse", "See5"]})
        self.assertLess(text.index("炸"), text.index("拆"))
        self.assertLess(text.index("拆"), text.index("预5"))

    def test_debug_disabled_exits_without_reading_view_or_printing(self):
        class Unreadable:
            def get(self, *args):
                raise AssertionError("Disabled diagnostics read their input")

            __getitem__ = get

        game = new_game()
        ai_player._log_decision(game, Unreadable(), Unreadable())
        self.assertEqual([], game.gui.messages)

    def test_decision_context_search_candidates_and_memory_use_individual_lines(self):
        game = new_game()
        game.gui.debug_mode = True
        view = ai_player.build_observation(game)
        view.update(remaining=3, hand=["Defuse", "Skip"], opponent_count=7,
                    known_opponent=["Defuse"], noped=1,
                    known_deck=["Bomb", None, "See5", None, "Defuse", None, "Alter3", None])
        ai_player._log_decision(game, view, diagnostic_result())
        self.assertEqual(6, len(game.gui.messages))
        self.assertTrue(all(options.get("debug") is True for _, options in game.gui.messages))
        lines = debug_lines(game)
        for line, prefix in zip(lines, ("AI 决策", "局面", "搜索", "候选1", "候选2", "AI牌堆记忆")):
            self.assertTrue(line.startswith(prefix), line)
            self.assertNotIn("\n", line)
            for unwanted in ("依据", "非真实胜率", "值为模拟价值", "[Debug]"):
                self.assertNotIn(unwanted, line)
        decision, context, search, candidate1, candidate2, memory = lines
        self.assertIn("AI牌堆记忆", memory)
        self.assertEqual(4, memory.count("?"))
        self.assertLess(memory.index("炸"), memory.index("预5"))
        self.assertLess(memory.index("预5"), memory.index("拆"))
        self.assertLess(memory.index("拆"), memory.index("改"))
        self.assertNotIn("...", memory)
        self.assertNotIn("…", memory)
        self.assertIn("16", search)
        self.assertIn("12", search)
        self.assertIn("3", context)
        self.assertIn("7", context)
        self.assertIn("0.750", candidate1)
        self.assertIn("未评估", candidate2)

    def test_memory_is_not_truncated_at_either_end(self):
        game = new_game()
        game.gui.debug_mode = True
        view = ai_player.build_observation(game)
        view["known_deck"] = ["Bomb"] + [None] * 30 + ["See5"]
        ai_player._log_decision(game, view, diagnostic_result())
        memory = debug_lines(game)[-1]
        self.assertEqual(30, memory.count("?"))
        self.assertIn("炸", memory)
        self.assertIn("预5", memory)
        self.assertLess(memory.index("炸"), memory.index("预5"))

    def test_diagnostics_read_only_frozen_view_even_if_live_state_is_unreadable(self):
        class Unreadable:
            def __iter__(self):
                raise AssertionError("Diagnostics inspected live hidden card contents")

            def __len__(self):
                raise AssertionError("Diagnostics inspected live state instead of the frozen view")

            def __getitem__(self, key):
                raise AssertionError("Diagnostics inspected live card data")

        game = new_game()
        game.gui.debug_mode = True
        view = ai_player.build_observation(game)
        view["known_deck"] = [None, "Skip", None, "Bomb", None]
        result = diagnostic_result()
        ai_player._log_decision(game, view, result)
        original = deepcopy(game.gui.messages)
        game.gui.messages.clear()
        game.deck.cards = Unreadable()
        game.deck.discard_pile = Unreadable()
        game.player.hand = Unreadable()
        game.ai.hand = Unreadable()
        game.core.known = Unreadable()
        game.core.known_opponent = Unreadable()
        game.remaining_turns = 999
        ai_player._log_decision(game, view, result)
        self.assertEqual(original, game.gui.messages)

    def test_zero_iterations_is_labelled_as_heuristic_without_invented_values(self):
        game = new_game()
        game.gui.debug_mode = True
        ai_player._log_decision(game, ai_player.build_observation(game), diagnostic_result(iterations=0))
        lines = debug_lines(game)
        self.assertIn("0次/", lines[2])
        self.assertIn("启发式", lines[2])
        self.assertIn("未评估", lines[3])
        for line in lines:
            self.assertNotIn("0.75", line)
            for unwanted in ("依据", "非真实胜率", "值为模拟价值", "[Debug]"):
                self.assertNotIn(unwanted, line)

    def test_missing_optional_diagnostics_remain_compatible(self):
        game = new_game()
        game.gui.debug_mode = True
        ai_player._log_decision(game, ai_player.build_observation(game), {"action": {"kind": "Draw"}})
        lines = debug_lines(game)
        self.assertEqual(4, len(lines))
        self.assertTrue(lines[-1].startswith("AI牌堆记忆"))

    def test_candidate_rows_are_limited_to_three(self):
        game = new_game()
        game.gui.debug_mode = True
        result = diagnostic_result()
        result["candidates"] *= 2
        ai_player._log_decision(game, ai_player.build_observation(game), result)
        lines = debug_lines(game)
        self.assertEqual(7, len(lines))
        self.assertEqual(3, sum(line.startswith("候选") for line in lines))
        self.assertTrue(lines[-1].startswith("AI牌堆记忆"))

    def test_private_phases_show_choice_without_ordinary_draw_risk_estimates(self):
        game = new_game()
        game.gui.debug_mode = True
        for phase, action in [
            ({"kind": "Replace"}, {"kind": "Replace", "position": 0}),
            ({"kind": "Arrange", "cards": ["Bomb", "See5", "Skip"]},
             {"kind": "Order", "cards": ["Skip", "Bomb", "See5"]}),
        ]:
            with self.subTest(phase=phase):
                game.gui.messages.clear()
                view = ai_player.build_observation(game)
                view["phase"] = phase
                ai_player._log_decision(game, view, diagnostic_result(action))
                lines = debug_lines(game)
                decision = lines[0]
                self.assertIn(ai_player._action_text(game, action), decision)
                self.assertNotIn("风险", lines[1])
                self.assertNotIn("%", lines[1])


class DiagnosticsDeliveryTests(unittest.TestCase):
    class Task:
        result = diagnostic_result()
        instances = []

        def __init__(self, view, **kwargs):
            self.view = deepcopy(view)
            self.cancelled = False
            self.__class__.instances.append(self)

        def poll(self):
            return True, deepcopy(self.result), None

        def cancel(self):
            self.cancelled = True

    def setUp(self):
        self.Task.result = diagnostic_result()
        self.Task.instances = []
        patcher = patch("ai_player.ai_backend.SearchTask", self.Task)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sync_control_logs_only_after_action_validation(self):
        game = new_game()
        game.current_player = game.ai
        result = diagnostic_result()
        with patch("ai_player.ai_backend.search", return_value=result), patch("ai_player._log_decision") as log:
            self.assertEqual(("draw", None), ai_player.ai_control(game))
            log.assert_called_once()
            self.assertIs(game, log.call_args.args[0])
            self.assertEqual(ai_player.build_observation(game), log.call_args.args[1])
            self.assertIs(result, log.call_args.args[2])
        with patch("ai_player.ai_backend.search", return_value=diagnostic_result({"kind": "Play", "card": "Bomb"})), \
                patch("ai_player._log_decision") as log:
            with self.assertRaises(RuntimeError):
                ai_player.ai_control(game)
            log.assert_not_called()

    def test_async_log_occurs_immediately_before_validated_callback(self):
        game = new_game()
        game.core = scenario([core.Card.DEFUSE], [core.Card.DEFUSE], top=[core.Card.BOMB], current=1)
        game.core.apply(core.DRAW, game._rng)
        game._sync_from_core()
        events = []
        self.Task.result = diagnostic_result({"kind": "Replace", "position": 0})
        with patch("ai_player._log_decision", side_effect=lambda *args: events.append("log")):
            ai_player.begin_private_choice(game, "Replace", [], lambda action: events.append("apply"))
            self.assertEqual([], events)
            game.gui.root.run_one()
        self.assertEqual(["log", "apply"], events)

    def test_modal_pause_and_stale_search_never_emit_decision_logs(self):
        for invalidation in ("grab", "native_pause", "changed_view", "replacement_game"):
            with self.subTest(invalidation=invalidation):
                game = new_game()
                game.current_player = game.ai
                with patch("ai_player._log_decision") as log:
                    ai_player.ai_turn(game)
                    if invalidation == "grab":
                        game.gui.root.grab = object()
                    elif invalidation == "native_pause":
                        game.gui._ai_paused = True
                    elif invalidation == "changed_view":
                        game.remaining_turns += 1
                    else:
                        main.Game(game.gui)
                    game.gui.root.run_one()
                    log.assert_not_called()
                    ai_player.cancel_search(game)

    def test_async_private_order_logs_with_frozen_visible_cards(self):
        game = new_game()
        game.core = scenario([core.Card.DEFUSE], [core.Card.ALTER3],
                             top=[core.Card.BOMB, core.Card.SEE5, core.Card.SKIP], current=1)
        game.core.apply(core.Action("Play", card=core.Card.ALTER3), game._rng)
        game._sync_from_core()
        visible = game._held_cards[:]
        self.Task.result = diagnostic_result({"kind": "Order", "cards": ["Skip", "Bomb", "See5"]})
        callback = Mock()
        with patch("ai_player._log_decision") as log:
            ai_player.begin_private_choice(game, "Arrange", visible, callback)
            game.gui.root.run_one()
            log.assert_called_once()
            self.assertEqual({"kind": "Arrange", "cards": ["Bomb", "See5", "Skip"]},
                             log.call_args.args[1]["phase"])
        callback.assert_called_once_with(self.Task.result["action"])


class RealWorkerDiagnosticsTests(unittest.TestCase):
    def test_worker_candidates_are_bounded_and_unvisited_values_are_null(self):
        game = new_game()
        game.current_player = game.ai
        view = ai_player.build_observation(game)
        searched = ai_backend.search(view, iterations=16, time_limit_ms=5000, seed=91)
        self.assertEqual("most_visited", searched["selection"])
        self.assertGreater(len(searched["candidates"]), 0)
        self.assertLessEqual(len(searched["candidates"]), 3)
        self.assertEqual(searched["action"], searched["candidates"][0]["action"])
        for candidate in searched["candidates"]:
            self.assertGreaterEqual(candidate["visits"], 0)
            if candidate["visits"] == 0:
                self.assertIsNone(candidate["value"])
            else:
                self.assertGreaterEqual(candidate["value"], 0.0)
                self.assertLessEqual(candidate["value"], 1.0)
        fallback = ai_backend.search(view, iterations=0, time_limit_ms=5000, seed=91)
        self.assertEqual("heuristic_fallback", fallback["selection"])
        self.assertEqual(0, fallback["iterations"])
        for candidate in fallback["candidates"]:
            self.assertEqual(0, candidate["visits"])
            self.assertIsNone(candidate["value"])


if __name__ == "__main__":
    unittest.main()
