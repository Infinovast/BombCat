"""Headless search, diagnostics and JSON-line protocol regression tests."""

from copy import deepcopy
import json
import random
import subprocess
import sys
import threading
import unittest

import ai_worker
from arena import benchmark
from game_core import (Action, Card, Game, Observation, action_from_wire,
                       observation_to_wire, standard_deck)
from search_ai import choose, move_key, scored_actions


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.new(random.Random(73))
        self.view = self.game.observation(self.game.current)

    def test_search_is_deterministic_legal_and_reports_actual_counts(self):
        first = choose(self.view, iterations=35, time_limit_ms=None, seed=42, rollout_limit=80)
        second = choose(self.view, iterations=35, time_limit_ms=None, seed=42, rollout_limit=80)
        self.assertEqual(first["action"], second["action"])
        self.assertEqual(first["candidates"], second["candidates"])
        self.assertEqual(35, first["iterations"])
        self.assertTrue(self.game.is_legal(action_from_wire(first["action"])))
        self.assertEqual("most_visited", first["selection"])
        visits = sum(item["visits"] for item in first["candidates"])
        self.assertGreater(visits, 0)
        self.assertLessEqual(visits, first["iterations"])
        self.assertEqual(first["action"], first["candidates"][0]["action"])
        for candidate in first["candidates"]:
            self.assertEqual({"action", "visits", "value"}, set(candidate))
            if candidate["visits"]:
                self.assertLessEqual(0.0, candidate["value"])
                self.assertLessEqual(candidate["value"], 1.0)
            else:
                self.assertIsNone(candidate["value"])

    def test_pre_cancelled_and_zero_time_keep_a_legal_heuristic_fallback(self):
        cancellation = threading.Event()
        cancellation.set()
        for options in ({"cancel": cancellation}, {"time_limit_ms": 0}, {"iterations": 0}):
            with self.subTest(options=options):
                result = choose(self.view, seed=9, **options)
                self.assertEqual(0, result["iterations"])
                self.assertEqual("heuristic_fallback", result["selection"])
                self.assertTrue(self.game.is_legal(action_from_wire(result["action"])))
                self.assertTrue(all(item["value"] is None for item in result["candidates"]))

    def test_cancellation_is_checked_between_iterations(self):
        calls = 0

        def cancel():
            nonlocal calls
            calls += 1
            return calls > 3

        result = choose(self.view, iterations=100, time_limit_ms=None, seed=42, cancel=cancel)
        self.assertEqual(3, result["iterations"])

    def test_private_moves_collapse_only_for_the_other_observer(self):
        first = Action("Replace", position=0)
        second = Action("Replace", position=8)
        self.assertEqual(move_key(first, 1, 0), move_key(second, 1, 0))
        self.assertNotEqual(move_key(first, 1, 1), move_key(second, 1, 1))
        first = Action("Order", cards=(Card.BOMB, Card.SKIP))
        second = Action("Order", cards=(Card.SKIP, Card.BOMB))
        self.assertEqual(move_key(first, 1, 0), move_key(second, 1, 0))
        self.assertNotEqual(move_key(first, 1, 1), move_key(second, 1, 1))
        self.assertNotEqual(move_key(Action("Play", card=Card.SKIP), 1, 0),
                            move_key(Action("Play", card=Card.ATTACK), 1, 0))

    def test_search_rejects_authoritative_game(self):
        with self.assertRaises(TypeError):
            choose(self.game)

    def test_different_hidden_worlds_have_identical_search_diagnostics(self):
        other = self.game.clone()
        hand_index = next(index for index, card in enumerate(other.hands[1])
                          if card != Card.DEFUSE)
        deck_index = next(index for index, card in enumerate(other.deck)
                          if card != Card.BOMB and card != other.hands[1][hand_index])
        other.deck[deck_index], other.hands[1][hand_index] = (
            other.hands[1][hand_index], other.deck[deck_index])
        other.check_invariants()
        self.assertNotEqual(self.game.hands[1], other.hands[1])
        self.assertEqual(self.view, other.observation(0))
        first = choose(self.view, iterations=20, time_limit_ms=None, seed=99)
        second = choose(other.observation(0), iterations=20, time_limit_ms=None, seed=99)
        for field in ("action", "candidates", "selection", "iterations"):
            self.assertEqual(first[field], second[field])

    def test_known_fatal_draw_is_removed_when_escape_exists(self):
        game = self.game
        bomb = game.deck.index(Card.BOMB)
        game.deck[0], game.deck[bomb] = game.deck[bomb], game.deck[0]
        game.known[0][0] = Card.BOMB
        while Card.DEFUSE in game.hands[0]:
            game.hands[0].remove(Card.DEFUSE)
            game.deck.append(Card.DEFUSE)
            for memory in game.known:
                memory.append(None)
        if Card.SKIP not in game.hands[0]:
            index = game.deck.index(Card.SKIP)
            game.hands[0].append(game.deck.pop(index))
            for memory in game.known:
                memory.pop(index)
        game.known_opponent = [[], []]
        game.check_invariants()
        choices = scored_actions(game.observation(0))
        self.assertTrue(choices)
        self.assertFalse(any(action.kind == "Draw" for action, _ in choices))

    def test_all_fatal_choices_still_return_a_legal_action(self):
        discard = [card for card in standard_deck() if card != Card.BOMB]
        discard.remove(Card.BOTTOM)
        view = Observation(0, 0, 1, (Card.BOTTOM,), 0, (), (Card.BOMB,) * 4,
                           tuple(discard))
        result = choose(view, iterations=0, seed=1)
        game = view.sample(random.Random(1))
        game.apply(action_from_wire(result["action"]), random.Random(1))
        self.assertEqual(1, game.winner)

    def test_single_legal_action_accumulates_all_visits(self):
        game = self.game
        game.deck.extend(game.hands[0])
        game.hands[0].clear()
        for memory in game.known:
            memory.extend([None] * (len(game.deck) - len(memory)))
        game.known_opponent[1].clear()
        game.check_invariants()
        result = choose(game.observation(0), iterations=15, time_limit_ms=None, seed=13)
        self.assertEqual(1, len(result["candidates"]))
        self.assertEqual(15, result["candidates"][0]["visits"])

    def test_reorder_candidates_are_pruned_to_eight(self):
        game = self.game
        cards = tuple(game.deck[:5])
        del game.deck[:5]
        for memory in game.known:
            del memory[:5]
        game.phase = "Arrange"
        game.phase_player = 0
        game.phase_cards = cards
        view = game.observation(0)
        choices = scored_actions(view)
        self.assertLessEqual(len(choices), 8)
        result = choose(view, iterations=12, time_limit_ms=None, seed=14)
        self.assertEqual("Order", result["action"]["kind"])
        self.assertEqual(sorted(cards), sorted(action_from_wire(result["action"]).cards))


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        game = Game.new(random.Random(3))
        self.request = {"version": 1, "id": 73, "iterations": 15, "time_limit_ms": 5000,
                        "seed": 21, "observation": observation_to_wire(game.observation(0))}

    def response(self, request):
        return json.loads(ai_worker.process_line(json.dumps(request)))

    def test_diagnostics_and_canonical_hand_match_after_permutation(self):
        first = self.response(self.request)
        self.request["observation"]["hand"].reverse()
        second = self.response(self.request)
        self.assertNotIn("error", first)
        self.assertEqual(73, first["id"])
        self.assertEqual(15, first["iterations"])
        self.assertEqual(7, len(first))
        for field in ("action", "candidates", "iterations", "selection"):
            self.assertEqual(first[field], second[field])

    def test_hidden_state_and_unknown_fields_are_rejected(self):
        for field in ("deck", "hands", "opponent_hand"):
            request = deepcopy(self.request)
            request["observation"][field] = []
            self.assertIn("error", self.response(request))
        request = deepcopy(self.request)
        request["actual_game"] = {}
        self.assertIn("error", self.response(request))

    def test_malformed_and_invalid_semantics_do_not_escape_protocol(self):
        for line in ("not JSON", "[]", "null", "NaN", "{" + " " * 65536):
            result = json.loads(ai_worker.process_line(line))
            self.assertIn("error", result)
        for field, value in (
            ("player", 2), ("current", 1), ("remaining", 0), ("remaining", 1001),
            ("remaining", True), ("opponent_count", 10), ("noped", 3), ("winner", 0),
            ("hand", ["Bomb"]), ("discard", ["Defuse"] * 5), ("discard", ["Bomb"]),
            ("known_deck", [None]), ("phase", {"kind": "Arrange", "cards": []}),
            ("phase", {"kind": "Play", "cards": []}),
        ):
            with self.subTest(field=field, value=value):
                request = deepcopy(self.request)
                request["observation"][field] = value
                result = self.response(request)
                self.assertIn("error", result)
                self.assertEqual(73, result["id"])
        for field, value in (("version", 2), ("id", True), ("seed", -1),
                             ("iterations", -1), ("time_limit_ms", 1.5)):
            request = deepcopy(self.request)
            request[field] = value
            self.assertIn("error", self.response(request))

    def test_zero_budget_diagnostics_have_null_unvisited_values(self):
        self.request["iterations"] = 0
        result = self.response(self.request)
        self.assertEqual("heuristic_fallback", result["selection"])
        self.assertEqual(result["action"], result["candidates"][0]["action"])
        self.assertTrue(all(item["visits"] == 0 and item["value"] is None
                            for item in result["candidates"]))

    def test_private_choice_protocol_keeps_legal_position_and_multiset(self):
        game = Game.new(random.Random(7))
        index = game.deck.index(Card.BOMB)
        game.deck.pop(index)
        for memory in game.known:
            memory.pop(index)
        game.phase, game.phase_player = "Replace", 0
        request = dict(self.request, observation=observation_to_wire(game.observation(0)))
        response = self.response(request)
        self.assertNotIn("error", response)
        self.assertEqual("Replace", response["action"]["kind"])
        self.assertTrue(0 <= response["action"]["position"] <= len(game.deck))
        game.apply(action_from_wire(response["action"]), random.Random(7))
        actor = game.current
        cards = tuple(game.deck[:5])
        del game.deck[:5]
        for memory in game.known:
            del memory[:5]
        game.phase, game.phase_player, game.phase_cards = "Arrange", actor, cards
        request["observation"] = observation_to_wire(game.observation(actor))
        response = self.response(request)
        self.assertNotIn("error", response)
        self.assertEqual("Order", response["action"]["kind"])
        for candidate in response["candidates"]:
            self.assertEqual(sorted(cards), sorted(action_from_wire(candidate["action"]).cards))

    def test_worker_stream_recovers_after_bad_request(self):
        self.request["iterations"] = 1
        completed = subprocess.run(
            [sys.executable, "-m", "ai_worker"],
            input="not JSON\n\n" + json.dumps(self.request) + "\n",
            text=True, encoding="utf-8", capture_output=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(2, len(responses))
        self.assertIn("error", responses[0])
        self.assertEqual(73, responses[1]["id"])
        self.assertIn("action", responses[1])

    def test_python_arena_finishes_both_seats(self):
        lines = []
        result = benchmark(pairs=1, iterations=4, seed=2026, emit=lines.append)
        self.assertEqual(2, result["completed"])
        self.assertEqual(0, result["unfinished"])
        self.assertGreater(result["searches"], 0)
        self.assertIn("paired_seeds=1", lines[-1])


if __name__ == "__main__":
    unittest.main()
