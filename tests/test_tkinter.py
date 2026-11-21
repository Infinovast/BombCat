"""Headless regression tests: real game/controller code, no desktop automation."""

import ast
from collections import Counter
from contextlib import contextmanager
import json
from pathlib import Path
import random
import re
import unittest
from unittest.mock import patch

import ai_player
import cards
import main


ROOT = Path(__file__).resolve().parents[1]


class FakeWidget:
    def __init__(self, *args, **kwargs):
        self.settings = kwargs

    def config(self, **kwargs):
        self.settings.update(kwargs)

    configure = config

    def pack(self, *args, **kwargs):
        pass

    def grid(self, *args, **kwargs):
        pass

    def grid_columnconfigure(self, *args, **kwargs):
        pass


class FakeRoot:
    def __init__(self):
        self.callbacks = []
        self.grab = None
        self.destroyed = False

    def after(self, delay, callback, *args):
        handle = len(self.callbacks)
        self.callbacks.append((callback, args))
        return handle

    def after_cancel(self, handle):
        if isinstance(handle, int) and handle < len(self.callbacks):
            self.callbacks[handle] = (lambda: None, ())

    def after_idle(self, callback, *args):
        return self.after(0, callback, *args)

    def run_one(self):
        callback, args = self.callbacks.pop(0)
        callback(*args)

    def grab_current(self):
        return self.grab

    def update_idletasks(self):
        pass

    def winfo_x(self):
        return 0

    def winfo_y(self):
        return 0

    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 900

    def winfo_exists(self):
        return not self.destroyed

    def destroy(self):
        self.destroyed = True


class FakeGUI:
    def __init__(self):
        self.root = FakeRoot()
        self.debug_mode = False
        self.messages = []
        self.draw_button = FakeWidget()
        self.play_button = FakeWidget()
        self.start_button = FakeWidget()
        self.game = None
        self.ended = False

    def set_game(self, game):
        self.game = game

    def print(self, message, **kwargs):
        self.messages.append((message, kwargs))

    def update_gui(self):
        pass

    def schedule_ai_turn(self):
        game = self.game
        self.root.after(2000, game.ai_turn)

    def prompt_bomb_position(self, max_pos):
        return max_pos

    def game_end(self):
        self.ended = True


def new_game(seed=2026):
    random.seed(seed)
    gui = FakeGUI()
    game = main.Game(gui)
    game.game_running = True
    return game


def all_cards(game):
    return game.deck.cards + game.deck.discard_pile + game.player.hand + game.ai.hand


def give_card(game, player, card_type, *, depth=None):
    """Move an existing card into a scenario hand without creating extra cards."""
    for zone in (player.hand, game.deck.cards, game.get_other(player).hand):
        card = next((candidate for candidate in zone
                     if isinstance(candidate, card_type)
                     and (depth is None or candidate.depth == depth)), None)
        if card is not None:
            if zone is not player.hand:
                zone.remove(card)
                player.hand.append(card)
            return card
    raise AssertionError(f"Scenario has no {card_type.__name__} card")


class FakeBoolean:
    def __init__(self, value=False):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


@contextmanager
def alter_dialog(mode="confirm", swap=False):
    """Exercise original dialog callbacks through fake widgets, without a Tk root."""
    buttons = []
    dialogs = []

    class Dialog(FakeWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.protocols = {}
            self.destroyed = False
            dialogs.append(self)

        def title(self, *args):
            pass

        def geometry(self, *args):
            pass

        def transient(self, *args):
            pass

        def grab_set(self):
            pass

        def protocol(self, name, callback):
            self.protocols[name] = callback

        def bind(self, *args):
            pass

        def destroy(self):
            self.destroyed = True

        def wait_window(self):
            card_buttons = [button for button in buttons if button.settings.get("text", "")[:1].isdigit()]
            if swap and len(card_buttons) >= 2:
                card_buttons[0].settings["command"]()
                card_buttons[1].settings["command"]()
            if mode == "close":
                self.protocols["WM_DELETE_WINDOW"]()
            else:
                label = "确认" if mode == "confirm" else "取消"
                next(button for button in buttons if button.settings.get("text") == label).settings["command"]()

    class Button(FakeWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            buttons.append(self)

    with patch.multiple(cards.tk, Toplevel=Dialog, Label=FakeWidget, Frame=FakeWidget,
                        Button=Button, BooleanVar=FakeBoolean):
        yield dialogs


class OriginalInterfaceTests(unittest.TestCase):
    def test_original_gui_text_and_card_descriptions_are_retained(self):
        baseline = json.loads((ROOT / "tests" / "original_ui_text.json").read_text(encoding="utf-8"))
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8-sig"))
        gui = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GUI")
        actual = Counter(node.value for node in ast.walk(gui)
                         if isinstance(node, ast.Constant) and isinstance(node.value, str))
        # Additional internal callback/event names are allowed; every original string remains.
        missing = Counter(baseline["gui_strings"]) - actual
        self.assertEqual({}, dict(missing))
        for key, expected in baseline["cards"].items():
            name, _, depth = key.partition(":")
            card = getattr(cards, name)(depth=int(depth)) if depth else getattr(cards, name)()
            self.assertEqual(expected, [card.name, card.description], key)

    def test_interface_uses_original_tkinter_widgets(self):
        self.assertIs(cards.tk, main.tk)
        self.assertEqual("tkinter", main.tk.__name__)
        self.assertEqual("tkinter.ttk", main.ttk.__name__)

    def test_short_bomb_replacement_log_keeps_defuse_block_title(self):
        gui = main.GUI.__new__(main.GUI)
        block = ["💣 AI 抽到了炸弹猫！", "🛠 AI 使用拆除卡...", "AI 将炸放回第5位（从顶部计）"]
        self.assertEqual("拆弹", gui._get_block_title(block))


class TkRulesTests(unittest.TestCase):
    def assert_inventory(self, game):
        inventory = all_cards(game)
        self.assertEqual(34, len(inventory))
        self.assertEqual(34, len({id(card) for card in inventory}))
        self.assertEqual(4, sum(isinstance(card, cards.DefuseCard) for card in inventory))
        self.assertEqual(4, sum(isinstance(card, cards.BombCatCard) for card in inventory))
        self.assertEqual(len(game.deck.cards), len(game.ai_known))
        for known, actual in zip(game.ai_known, game.deck.cards):
            self.assertTrue(known["known"] is None or known["known"] is actual)

    def _bomb_draw_with_thirteen_remaining(self, *, ai=True, debug=True):
        game = new_game()
        game.current_player = game.ai if ai else game.player
        game.remaining_turns = 3
        game.gui.debug_mode = debug
        bomb = next(card for card in game.deck.cards if isinstance(card, cards.BombCatCard))
        game.deck.cards.remove(bomb)
        # Keep the public34-card inventory intact while producing the reported13-card case.
        while len(game.deck.cards) > 13:
            card = next(card for card in game.deck.cards if not isinstance(card, cards.BombCatCard))
            game.deck.cards.remove(card)
            game.deck.discard_pile.append(card)
        game.deck.cards.append(bomb)
        game.ai_on_shuffle()
        game._sync_to_core()
        self.assertEqual(14, len(game.deck.cards))
        self.assert_inventory(game)
        return game, bomb

    def test_opening_inventory_and_fixed_depths_match_ai_simulator(self):
        for seed in range(25):
            game = new_game(seed)
            self.assert_inventory(game)
            self.assertEqual([6, 6], [len(game.player.hand), len(game.ai.hand)])
            self.assertEqual(22, len(game.deck.cards))
            self.assertTrue(game.player.has_defuse())
            self.assertTrue(game.ai.has_defuse())
            self.assertFalse(any(isinstance(card, cards.BombCatCard)
                                 for card in game.player.hand + game.ai.hand))
            inventory = all_cards(game)
            self.assertEqual([3, 5], sorted(card.depth for card in inventory if isinstance(card, cards.SeeFutureCard)))
            self.assertEqual([3, 3, 5], sorted(card.depth for card in inventory if isinstance(card, cards.AlterFutureCard)))

    def test_human_alter_confirm_cancel_and_window_close_conserve_cards(self):
        for mode in ("confirm", "cancel", "close"):
            for depth in (3, 5):
                game = new_game(depth)
                card = give_card(game, game.player, cards.AlterFutureCard, depth=depth)
                game.ai_on_shuffle()
                original = game.deck.cards[:]
                game.ai_on_see_future(list(reversed(game.deck.cards[-depth:])))
                game._sync_to_core()
                with alter_dialog(mode, swap=True):
                    self.assertTrue(game.play_card(game.player, card))
                expected = original[:]
                if mode == "confirm":
                    expected[-1], expected[-2] = expected[-2], expected[-1]
                self.assertEqual(expected, game.deck.cards, (mode, depth))
                self.assertTrue(all(slot["known"] is None for slot in game.ai_known[-depth:]))
                self.assert_inventory(game)

    def test_known_card_draw_records_only_publicly_deducible_opponent_card(self):
        game = new_game()
        known = next(card for card in game.deck.cards if not isinstance(card, cards.BombCatCard))
        game.deck.cards.remove(known)
        game.deck.cards.append(known)
        game.ai_on_shuffle()
        game.ai_on_see_future([known])
        game._sync_to_core()
        before = Counter(game.ai_known_opponent)
        game.draw_card(game.player)
        after = Counter(game.ai_known_opponent)
        self.assertEqual(before + Counter([ai_player.card_to_wire(known)]), after)
        self.assert_inventory(game)

    def test_bottom_draw_advances_exactly_one_action(self):
        game = new_game()
        bottom = next(card for card in game.deck.cards if not isinstance(card, cards.BombCatCard))
        game.deck.cards.remove(bottom)
        game.deck.cards.insert(0, bottom)
        game.ai_on_shuffle()
        card = give_card(game, game.player, cards.DrawBottomCard)
        game.ai_on_shuffle()
        revision = game._turn_revision
        game.remaining_turns = 3
        game._sync_to_core()
        self.assertTrue(game.play_card(game.player, card))
        self.assertEqual(revision + 1, game._turn_revision)
        self.assertEqual(2, game.remaining_turns)
        self.assertIs(game.player, game.current_player)
        self.assertIn(bottom, game.player.hand)
        self.assert_inventory(game)

    def test_restart_during_gui_refresh_does_not_advance_old_turn(self):
        game = new_game()
        safe = next(card for card in game.deck.cards if not isinstance(card, cards.BombCatCard))
        game.deck.cards.remove(safe)
        game.deck.cards.append(safe)
        game.ai_on_shuffle()
        game._sync_to_core()
        gui = game.gui
        replacement = []

        def replace_during_refresh():
            if not replacement:
                replacement.append(main.Game(gui))

        gui.update_gui = replace_during_refresh
        self.assertTrue(game.draw_card(game.player))
        self.assertIs(replacement[0], gui.game)
        self.assertEqual(1, game._turn_revision)
        self.assertEqual(22, len(gui.game.deck.cards))
        self.assertEqual(0, gui.game._turn_revision)
        self.assertIs(gui.game.player, gui.game.current_player)
        replacement_state = gui.game.core.clone()
        while gui.root.callbacks:
            gui.root.run_one()
        self.assertEqual(replacement_state, gui.game.core)

    def test_ai_reorder_uses_search_choice_and_retains_private_memory(self):
        game = next(candidate for seed in range(50)
                    if (candidate := new_game(seed))
                    and any(isinstance(card, cards.AlterFutureCard) for card in candidate.ai.hand))
        game.current_player = game.ai
        card = next(card for card in game.ai.hand if isinstance(card, cards.AlterFutureCard))
        top_first = list(reversed(game.deck.cards[-card.depth:]))
        pending = []

        def capture(game, kind, visible, callback):
            self.assertEqual("Arrange", kind)
            self.assertEqual(top_first, visible)
            self.assertIn(card, game.deck.discard_pile)
            self.assertNotIn(card, game.ai.hand)
            game._ai_pending = True
            pending.append(callback)

        with patch("ai_player.begin_private_choice", capture):
            self.assertTrue(game.play_card(game.ai, card))
        game._ai_pending = False
        order = list(reversed(top_first))
        pending[0]({"kind": "Order", "cards": [ai_player.card_to_wire(value) for value in order]})
        self.assertEqual(order, list(reversed(game.deck.cards[-card.depth:])))
        self.assertEqual(order, [slot["known"] for slot in reversed(game.ai_known[-card.depth:])])
        self.assert_inventory(game)

    def test_ai_bomb_replacement_maps_top_index_and_ends_all_actions(self):
        game = new_game()
        game.current_player = game.ai
        game.remaining_turns = 3
        bomb = next(card for card in game.deck.cards if isinstance(card, cards.BombCatCard))
        game.deck.cards.remove(bomb)
        game.deck.cards.append(bomb)
        game.ai_on_shuffle()
        game._sync_to_core()
        pending = []

        def capture(game, kind, visible, callback):
            self.assertEqual("Replace", kind)
            self.assertEqual([], visible)
            game._ai_pending = True
            pending.append(callback)

        with patch("ai_player.begin_private_choice", capture):
            self.assertTrue(game.draw_card(game.ai))
        self.assertEqual(3, game.remaining_turns)
        self.assertIs(game.ai, game.current_player)
        game._ai_pending = False
        pending[0]({"kind": "Replace", "position": 0})
        self.assertIs(bomb, game.deck.cards[-1])
        self.assertIs(bomb, game.ai_known[-1]["known"])
        self.assertIs(game.player, game.current_player)
        self.assertEqual(1, game.remaining_turns)
        self.assert_inventory(game)

    def test_ai_replacement_decision_completion_and_memory_use_same_top_rank(self):
        for position in (0, 4, 13):
            with self.subTest(top_based_position=position):
                game, bomb = self._bomb_draw_with_thirteen_remaining()
                pending = []

                def capture(game, kind, visible, callback):
                    self.assertEqual("Replace", kind)
                    game._ai_pending = True
                    pending.append(callback)

                with patch("ai_player.begin_private_choice", capture):
                    self.assertTrue(game.draw_card(game.ai))
                before = game.deck.cards[:]
                self.assertEqual(13, len(before))
                action = {"kind": "Replace", "position": position}
                view = ai_player.build_observation(game, "Replace")
                ai_player._log_decision(game, view, {
                    "action": action, "iterations": 1, "elapsed_ms": 1,
                    "selection": "most_visited", "candidates": [],
                })
                game._ai_pending = False
                pending[0](action)

                decision = next(message for message, _ in game.gui.messages
                                if message.startswith("AI 决策"))
                completion, options = next((message, options) for message, options in game.gui.messages
                                           if message.startswith("AI 将") and "放回" in message)
                rank = position + 1
                self.assertEqual(rank, int(re.search(r"第\s*(\d+)\s*位", decision).group(1)))
                self.assertEqual(rank, int(re.search(r"第\s*(\d+)\s*位", completion).group(1)))
                self.assertIn("从顶部计", completion)
                self.assertIn(game._card_short_name(bomb), completion)
                self.assertTrue(options.get("debug"))
                self.assertNotIn("(0~", completion)

                internal_index = 13 - position
                expected = before[:]
                expected.insert(internal_index, bomb)
                self.assertEqual(expected, game.deck.cards)
                self.assertIs(bomb, game.deck.cards[internal_index])
                self.assertIs(bomb, game.ai_known[internal_index]["known"])
                self.assertEqual("Bomb", ai_player.build_observation(game)["known_deck"][position])
                if position == 4:
                    self.assertEqual(9, internal_index)
                    self.assertIn("第5位", completion)
                self.assertIs(game.player, game.current_player)
                self.assertEqual(1, game.remaining_turns)
                self.assert_inventory(game)

    def test_normal_mode_ai_replacement_does_not_disclose_rank(self):
        game, bomb = self._bomb_draw_with_thirteen_remaining(debug=False)
        pending = []

        def capture(game, kind, visible, callback):
            game._ai_pending = True
            pending.append(callback)

        with patch("ai_player.begin_private_choice", capture):
            self.assertTrue(game.draw_card(game.ai))
        game._ai_pending = False
        pending[0]({"kind": "Replace", "position": 4})
        visible = [message for message, options in game.gui.messages if not options.get("debug")]
        completion = next(message for message in visible if "AI" in message and "放回" in message)
        self.assertIn("某个位置", completion)
        self.assertNotRegex(completion, r"第\s*\d+\s*位")
        self.assertIs(bomb, game.deck.cards[9])
        self.assert_inventory(game)

    def test_human_random_replacement_log_converts_internal_index_to_top_rank(self):
        game, bomb = self._bomb_draw_with_thirteen_remaining(ai=False, debug=False)
        game.gui.prompt_bomb_position = lambda max_pos: None
        with patch.object(game._rng, "randint", return_value=9) as random_position:
            self.assertTrue(game.draw_card(game.player))
        random_position.assert_called_once_with(0, 13)
        completion = next(message for message, _ in game.gui.messages if "随机将" in message and "放回" in message)
        self.assertEqual(5, int(re.search(r"第\s*(\d+)\s*位", completion).group(1)))
        self.assertIn("从顶部计", completion)
        self.assertNotIn("(0~", completion)
        self.assertIs(bomb, game.deck.cards[9])
        self.assertTrue(all(slot["known"] is None for slot in game.ai_known))
        self.assert_inventory(game)


class ObservationBoundaryTests(unittest.TestCase):
    def test_build_observation_cannot_read_hidden_cards(self):
        class CountOnly:
            def __init__(self, count):
                self.count = count

            def __len__(self):
                return self.count

            def __iter__(self):
                raise AssertionError("AI attempted to inspect a hidden card collection")

            def __getitem__(self, index):
                raise AssertionError("AI attempted to read a hidden card")

        game = new_game()
        game.deck.cards = CountOnly(len(game.deck.cards))
        game.player.hand = CountOnly(len(game.player.hand))
        observation = ai_player.build_observation(game)
        self.assertEqual(6, observation["opponent_count"])
        self.assertEqual(22, len(observation["known_deck"]))

    def test_hidden_state_permutations_produce_identical_observations(self):
        game = new_game()
        game.current_player = game.ai
        first = ai_player.build_observation(game)
        random.shuffle(game.deck.cards)
        unknown_hand = [card for card in game.player.hand if not isinstance(card, cards.DefuseCard)]
        replacement = next(card for card in game.deck.cards if not isinstance(card, cards.BombCatCard))
        if unknown_hand:
            old = unknown_hand[0]
            game.player.hand.remove(old)
            game.deck.cards.remove(replacement)
            game.player.hand.append(replacement)
            game.deck.cards.append(old)
        game._sync_to_core()
        self.assertEqual(first, ai_player.build_observation(game))
        self.assertEqual(set(first), {"player", "current", "remaining", "hand", "opponent_count",
                                     "known_opponent", "known_deck", "discard", "phase", "noped", "winner"})
        self.assertEqual([None] * len(game.deck.cards), first["known_deck"])
        self.assertEqual(["Defuse"], first["known_opponent"])

    def test_known_deck_is_serialized_top_first(self):
        game = new_game()
        visible = list(reversed(game.deck.cards[-3:]))
        game.ai_on_see_future(visible)
        game._sync_to_core()
        observation = ai_player.build_observation(game)
        self.assertEqual([ai_player.card_to_wire(card) for card in visible], observation["known_deck"][:3])
        self.assertEqual([None] * (len(game.deck.cards) - 3), observation["known_deck"][3:])

    def test_secret_human_insertion_does_not_leak_position(self):
        game = new_game()
        game.ai_on_see_future(list(reversed(game.deck.cards[-3:])))
        game.deck.cards.insert(2, cards.BombCatCard())
        game.ai_on_insert_unknown(2)
        self.assertEqual([{"known": None}] * len(game.deck.cards), game.ai_known)

    def test_own_insertion_preserves_own_information(self):
        game = new_game()
        game.ai_on_see_future(list(reversed(game.deck.cards[-3:])))
        known = game.ai_known[:]
        bomb = cards.BombCatCard()
        game.deck.cards.insert(2, bomb)
        game.ai_on_insert_known(2, bomb)
        self.assertIs(bomb, game.ai_known[2]["known"])
        self.assertEqual(known, game.ai_known[:2] + game.ai_known[3:])


class AsyncSearchTests(unittest.TestCase):
    class Task:
        instances = []

        def __init__(self, observation, **kwargs):
            self.observation = observation
            self.cancelled = False
            self.result = {"action": {"kind": "Draw"}}
            self.__class__.instances.append(self)

        def poll(self):
            return True, self.result, None

        def cancel(self):
            self.cancelled = True

    def setUp(self):
        self.Task.instances = []
        self.patcher = patch("ai_player.ai_backend.SearchTask", self.Task)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_restarted_game_ignores_and_cancels_stale_search(self):
        game = new_game()
        game.current_player = game.ai
        original = all_cards(game)[:]
        ai_player.ai_turn(game)
        task = self.Task.instances[-1]
        main.Game(game.gui)  # The replacement GUI game invalidates old callbacks.
        game.gui.root.run_one()
        self.assertTrue(task.cancelled)
        self.assertEqual(original, all_cards(game))

    def test_modal_defers_result_until_closed(self):
        game = new_game()
        game.current_player = game.ai
        # Make the draw deterministic and safe, so only scheduling is under test.
        safe = next(card for card in game.deck.cards if not isinstance(card, cards.BombCatCard))
        game.deck.cards.remove(safe)
        game.deck.cards.append(safe)
        game.ai_on_shuffle()
        game._sync_to_core()
        ai_player.ai_turn(game)
        count = len(game.deck.cards)
        game.gui.root.grab = object()
        game.gui.root.run_one()
        self.assertEqual(count, len(game.deck.cards))
        game.gui.root.grab = None
        game.gui.root.run_one()
        self.assertEqual(count - 1, len(game.deck.cards))

    def test_native_messagebox_pause_defers_result(self):
        game = new_game()
        game.current_player = game.ai
        safe = next(card for card in game.deck.cards if not isinstance(card, cards.BombCatCard))
        game.deck.cards.remove(safe)
        game.deck.cards.append(safe)
        game.ai_on_shuffle()
        game._sync_to_core()
        ai_player.ai_turn(game)
        count = len(game.deck.cards)
        game.gui._ai_paused = True
        game.gui.root.run_one()
        self.assertEqual(count, len(game.deck.cards))
        game.gui._ai_paused = False
        game.gui.root.run_one()
        self.assertEqual(count - 1, len(game.deck.cards))

    def test_observation_drift_cancels_search_before_applying_result(self):
        game = new_game()
        game.current_player = game.ai
        ai_player.ai_turn(game)
        task = self.Task.instances[-1]
        count = len(game.deck.cards)
        game.remaining_turns += 1
        game.gui.root.run_one()
        self.assertTrue(task.cancelled)
        self.assertEqual(count, len(game.deck.cards))
        self.assertFalse(game._ai_pending)

    def test_cancel_search_terminates_task(self):
        game = new_game()
        game.current_player = game.ai
        ai_player.ai_turn(game)
        task = self.Task.instances[-1]
        ai_player.cancel_search(game)
        self.assertTrue(task.cancelled)
        self.assertFalse(game._ai_pending)


if __name__ == "__main__":
    unittest.main()
