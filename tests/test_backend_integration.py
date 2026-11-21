"""Scripted Tkinter-controller/local-AI integration without desktop windows."""

import json
import random
import subprocess
import sys
import unittest
from unittest.mock import patch

import ai_backend
import ai_player
import cards
from tests.test_tkinter import ROOT, all_cards, alter_dialog, new_game


class BackendIntegrationTests(unittest.TestCase):
    def test_real_engine_decision_is_legal_and_seed_reproducible(self):
        game = new_game()
        game.current_player = game.ai
        view = ai_player.build_observation(game)
        first = ai_backend.search(view, iterations=20, time_limit_ms=5000, seed=7)
        second = ai_backend.search(view, iterations=20, time_limit_ms=5000, seed=7)
        self.assertEqual(first["action"], second["action"])
        self.assertEqual(20, first["iterations"])
        action = first["action"]
        self.assertIn(action["kind"], ("Draw", "Play"))
        if action["kind"] == "Play":
            self.assertIn(action["card"], [ai_player.card_to_wire(card) for card in game.ai.hand])
            self.assertNotIn(action["card"], ("Bomb", "Defuse"))

    def test_actual_cli_survives_malformed_request_then_valid_request(self):
        game = new_game()
        game.current_player = game.ai
        request = {"version": 1, "id": 81, "observation": ai_player.build_observation(game),
                   "iterations": 1, "time_limit_ms": 5000, "seed": 7}
        completed = subprocess.run([sys.executable, "-m", "ai_worker"], cwd=ROOT,
                                   input="not json\n" + json.dumps(request) + "\n",
                                   text=True, encoding="utf-8", capture_output=True, timeout=15,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(0, completed.returncode, completed.stderr)
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(2, len(responses))
        self.assertIn("error", responses[0])
        self.assertEqual(81, responses[1]["id"])
        self.assertIn("action", responses[1])

    def test_two_seeded_complete_games_through_original_controller(self):
        searches = 0

        def private_choice(game, kind, visible, callback):
            nonlocal searches
            response = ai_backend.search(ai_player.build_observation(game, kind, visible),
                                         iterations=8, time_limit_ms=5000, seed=searches + 200)
            searches += 1
            callback(response["action"])

        for seed in (17, 208):
            game = new_game(seed)
            game.ai_turn = lambda: None  # The script drives turns instead of a Tk scheduler.
            rng = random.Random(seed)
            original_ids = {id(card) for card in all_cards(game)}
            with patch("ai_player.begin_private_choice", private_choice):
                for step in range(400):
                    if not game.game_running:
                        break
                    actor = game.current_player
                    if actor.is_ai:
                        action, card = ai_player.ai_control(game, iterations=8,
                                                            time_limit_ms=5000, seed=step + seed)
                        searches += 1
                    else:
                        playable = actor.get_specific_cards("playable")
                        playable = [card for card in playable
                                    if not (isinstance(card, cards.NopeCard)
                                            and game.noped is game.ai)]
                        draw = len(actor.hand) < actor.hand_limit and (not playable or rng.random() < 0.6)
                        action, card = ("draw", None) if draw else ("play", rng.choice(playable))
                    if action == "draw":
                        self.assertTrue(game.draw_card(actor), (seed, step))
                    else:
                        with alter_dialog("confirm"):
                            self.assertTrue(game.play_card(actor, card), (seed, step, card.name))
                    self.assertEqual(original_ids, {id(card) for card in all_cards(game)}, (seed, step))
                    self.assertEqual(34, len(all_cards(game)), (seed, step))
                    self.assertEqual(len(game.deck.cards), len(game.ai_known), (seed, step))
                    for slot, actual in zip(game.ai_known, game.deck.cards):
                        self.assertTrue(slot["known"] is None or slot["known"] is actual, (seed, step))
                    game.core.check_invariants()
                else:
                    self.fail(f"seed={seed} did not finish within400 actions")
            self.assertTrue(game.gui.ended)
            self.assertFalse(game.ai.alive and game.player.alive)
        self.assertGreater(searches, 10)


if __name__ == "__main__":
    unittest.main()
