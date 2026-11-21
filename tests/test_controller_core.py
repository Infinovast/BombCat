"""The Tkinter controller and search simulations execute the same rules engine."""

import random
import unittest
from unittest.mock import Mock, patch

import ai_player
import game_core as core
from tests.test_tkinter import alter_dialog, new_game


def scenario(human, opponent, *, top=(), current=0, remaining=3, noped=None):
    pool = core.standard_deck()
    for card in [*human, *opponent, *top]:
        pool.remove(card)
    deck = [*top, *pool]
    known_opponent = [[core.Card.DEFUSE] if core.Card.DEFUSE in opponent else [],
                      [core.Card.DEFUSE] if core.Card.DEFUSE in human else []]
    state = core.Game(deck, [list(human), list(opponent)], [], current=current,
                      remaining=remaining, noped=noped,
                      known=[[None] * len(deck), [None] * len(deck)],
                      known_opponent=known_opponent)
    state.check_invariants()
    return state


class ControllerCoreTests(unittest.TestCase):
    def install(self, state, seed=513):
        game = new_game(seed)
        game.core = state.clone()
        game._rng = random.Random(seed)
        game._sync_from_core()
        game.game_running = True
        return game, state.clone(), random.Random(seed)

    def assert_matches(self, game, expected):
        self.assertEqual(expected, game.core)
        game.core.check_invariants()
        decode = lambda card: core.card_from_wire(ai_player.card_to_wire(card))
        self.assertEqual(expected.deck, [decode(card) for card in reversed(game.deck.cards)])
        self.assertEqual(expected.hands[0], [decode(card) for card in game.player.hand])
        self.assertEqual(expected.hands[1], [decode(card) for card in game.ai.hand])
        self.assertEqual(expected.discard, [decode(card) for card in game.deck.discard_pile])
        if expected.phase == "Play":
            self.assertEqual(expected.observation(1),
                             core.observation_from_wire(ai_player.build_observation(game)))

    def test_public_actions_call_shared_apply_and_match_direct_simulation(self):
        C = core.Card
        choices = [None, C.NOPE, C.ATTACK, C.PERSONAL_ATTACK, C.SKIP,
                   C.SUPER_SKIP, C.SHUFFLE, C.SEE3, C.SEE5, C.BOTTOM, C.SWAP]
        original_apply = core.Game.apply
        for choice in choices:
            with self.subTest(card=choice):
                hand = [C.DEFUSE] + ([] if choice is None else [choice])
                state = scenario(hand, [C.DEFUSE, C.ATTACK], top=[C.DEFUSE, C.SKIP])
                game, expected, rng = self.install(state)
                action = core.DRAW if choice is None else core.Action("Play", card=choice)
                expected.apply(action, rng)
                calls = []

                def observe_apply(instance, actual_action, actual_rng):
                    if instance is game.core:
                        calls.append(actual_action)
                    return original_apply(instance, actual_action, actual_rng)

                with patch.object(core.Game, "apply", new=observe_apply):
                    if choice is None:
                        accepted = game.draw_card(game.player)
                    else:
                        card = next(card for card in game.player.hand
                                    if ai_player.card_to_wire(card) == core.card_to_wire(choice))
                        accepted = game.play_card(game.player, card)
                self.assertTrue(accepted)
                self.assertEqual([action], calls)
                self.assert_matches(game, expected)

    def test_full_hand_bottom_draw_and_cancelled_card_match_shared_model(self):
        C = core.Card
        cases = [
            (scenario([C.DEFUSE, C.BOTTOM, C.NOPE, C.ATTACK, C.PERSONAL_ATTACK,
                       C.SKIP, C.SUPER_SKIP, C.SHUFFLE, C.SWAP], [C.DEFUSE], top=[C.SKIP]), C.BOTTOM),
            (scenario([C.DEFUSE, C.SKIP], [C.DEFUSE], top=[C.SKIP], noped=0), C.SKIP),
        ]
        for state, choice in cases:
            with self.subTest(card=choice):
                game, expected, rng = self.install(state)
                action = core.Action("Play", card=choice)
                expected.apply(action, rng)
                card = next(card for card in game.player.hand
                            if ai_player.card_to_wire(card) == core.card_to_wire(choice))
                self.assertTrue(game.play_card(game.player, card))
                self.assert_matches(game, expected)

    def test_controller_rejects_invalid_inputs_without_changing_core(self):
        C = core.Card
        state = scenario([C.DEFUSE, C.SKIP], [C.DEFUSE, C.ATTACK], top=[C.SKIP])
        game, expected, _ = self.install(state)
        self.assertFalse(game.draw_card(game.ai))
        self.assertFalse(game.play_card(game.ai, game.ai.hand[-1]))
        self.assertFalse(game.play_card(game.player, game.player.hand[0]))  # Passive defuse.
        self.assert_matches(game, expected)

    def test_ai_reorder_phase_and_completion_use_shared_core(self):
        C = core.Card
        state = scenario([C.DEFUSE, C.ATTACK], [C.DEFUSE, C.ALTER5],
                         top=[C.SKIP, C.BOMB, C.NOPE, C.BOMB, C.SWAP], current=1)
        game, expected, rng = self.install(state)
        card = next(card for card in game.ai.hand if ai_player.card_to_wire(card) == "Alter5")
        pending = []

        def capture(game, kind, visible, callback):
            self.assertEqual("Arrange", kind)
            self.assertEqual(expected.phase_cards,
                             tuple(core.card_from_wire(ai_player.card_to_wire(card)) for card in visible))
            self.assertEqual(expected.observation(1), core.observation_from_wire(
                ai_player.build_observation(game)))
            game._ai_pending = True
            pending.append(callback)

        expected.apply(core.Action("Play", card=C.ALTER5), rng)
        with patch("ai_player.begin_private_choice", capture):
            self.assertTrue(game.play_card(game.ai, card))
        self.assert_matches(game, expected)
        order = tuple(reversed(expected.phase_cards))
        action = core.Action("Order", cards=order)
        expected.apply(action, rng)
        game._ai_pending = False
        pending[0](core.action_to_wire(action))
        self.assert_matches(game, expected)

    def test_ai_defuse_private_phase_and_all_insertion_boundaries_match_core(self):
        C = core.Card
        state = scenario([C.DEFUSE, C.ATTACK], [C.DEFUSE, C.SKIP],
                         top=[C.BOMB, C.NOPE], current=1)
        for position in (0, 4, len(state.deck) - 1):
            with self.subTest(position=position):
                game, expected, rng = self.install(state)
                pending = []

                def capture(game, kind, visible, callback):
                    self.assertEqual("Replace", kind)
                    self.assertEqual(expected.observation(1), core.observation_from_wire(
                        ai_player.build_observation(game)))
                    game._ai_pending = True
                    pending.append(callback)

                expected.apply(core.DRAW, rng)
                with patch("ai_player.begin_private_choice", capture):
                    self.assertTrue(game.draw_card(game.ai))
                self.assert_matches(game, expected)
                action = core.Action("Replace", position=position)
                expected.apply(action, rng)
                game._ai_pending = False
                pending[0](core.action_to_wire(action))
                self.assert_matches(game, expected)

    def test_human_reorder_confirm_cancel_and_close_match_direct_core(self):
        C = core.Card
        for mode in ("confirm", "cancel", "close"):
            with self.subTest(mode=mode):
                state = scenario([C.DEFUSE, C.ALTER3], [C.DEFUSE, C.ATTACK],
                                 top=[C.SKIP, C.BOMB, C.NOPE])
                game, expected, rng = self.install(state)
                card = next(card for card in game.player.hand if ai_player.card_to_wire(card) == "Alter3")
                expected.apply(core.Action("Play", card=C.ALTER3), rng)
                order = list(expected.phase_cards)
                if mode == "confirm":
                    order[0], order[1] = order[1], order[0]
                expected.apply(core.Action("Order", cards=tuple(order)), rng)
                with alter_dialog(mode, swap=True):
                    self.assertTrue(game.play_card(game.player, card))
                self.assert_matches(game, expected)

    def test_human_defuse_from_draw_or_bottom_schedules_next_turn_once(self):
        C = core.Card
        for bottom in (False, True):
            with self.subTest(from_bottom=bottom):
                state = scenario([C.DEFUSE, C.BOTTOM] if bottom else [C.DEFUSE, C.SKIP],
                                 [C.DEFUSE, C.ATTACK], top=[C.BOMB, C.NOPE], remaining=3)
                if bottom:
                    state.deck.remove(C.BOMB)
                    state.deck.append(C.BOMB)
                state.check_invariants()
                game, expected, rng = self.install(state)
                game.gui.schedule_ai_turn = Mock()
                game.gui.prompt_bomb_position = Mock(side_effect=lambda max_pos: max_pos)
                action = core.Action("Play", card=C.BOTTOM) if bottom else core.DRAW
                expected.apply(action, rng)
                self.assertEqual("Replace", expected.phase)
                expected.apply(core.Action("Replace", position=0), rng)

                if bottom:
                    card = next(card for card in game.player.hand if ai_player.card_to_wire(card) == "Bottom")
                    self.assertTrue(game.play_card(game.player, card))
                else:
                    self.assertTrue(game.draw_card(game.player))

                self.assert_matches(game, expected)
                self.assertEqual(1, game.core.turn_revision)
                self.assertEqual(1, game.turn_progress)
                self.assertIs(game.ai, game.turn_owner)
                self.assertIs(game.ai, game.current_player)
                self.assertEqual("1/1", game.get_turn_counter_text())
                game.gui.schedule_ai_turn.assert_called_once_with()
                game.gui.prompt_bomb_position.assert_called_once()
                self.assertEqual(1, sum("AI回合" in message for message, _ in game.gui.messages))


if __name__ == "__main__":
    unittest.main()
