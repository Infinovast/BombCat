"""Pure Python rules regressions. These tests never create a Tk window."""

from dataclasses import replace
import random
import unittest

from game_core import (
    Action, Card, DRAW, Game, action_from_wire, action_to_wire, card_from_wire,
    card_to_wire, card_value, observation_from_wire, observation_to_wire,
    permutations, standard_deck,
)


def fixture(hands, top=(), remaining=1):
    pool = standard_deck()
    for card in [*hands[0], *hands[1], *top]:
        pool.remove(card)
    deck = [*top, *pool]
    return Game(deck, [list(hand) for hand in hands], [], remaining=remaining,
                known=[[None] * len(deck), [None] * len(deck)])


class GameCoreTests(unittest.TestCase):
    def test_starting_deal_conserves_34_cards(self):
        for seed in range(100):
            game = Game.new(random.Random(seed))
            self.assertEqual(22, len(game.deck))
            for hand in game.hands:
                self.assertEqual(6, len(hand))
                self.assertIn(Card.DEFUSE, hand)
                self.assertNotIn(Card.BOMB, hand)
            game.check_invariants()
            for player in (0, 1):
                game.observation(player).sample(random.Random(seed + 1)).check_invariants()

    def test_filtered_dealing_does_not_bias_the_top_of_remaining_deck(self):
        bombs = sum(Game.new(random.Random(seed)).deck[0] == Card.BOMB for seed in range(2000))
        self.assertTrue(270 <= bombs < 460, bombs)

    def test_attack_transfers_remaining_pressure_plus_one(self):
        game = fixture([[Card.ATTACK], []], remaining=3)
        game.apply(Action("Play", card=Card.ATTACK), random.Random(1))
        self.assertEqual((1, 4), (game.current, game.remaining))
        game.check_invariants()

    def test_personal_attack_can_chain_into_attack(self):
        game = fixture([[Card.PERSONAL_ATTACK, Card.ATTACK], []])
        rng = random.Random(1)
        game.apply(Action("Play", card=Card.PERSONAL_ATTACK), rng)
        self.assertEqual((0, 3), (game.current, game.remaining))
        game.apply(Action("Play", card=Card.ATTACK), rng)
        self.assertEqual((1, 4), (game.current, game.remaining))

    def test_skip_and_super_skip_have_distinct_turn_effects(self):
        game = fixture([[Card.SKIP, Card.SUPER_SKIP], []], remaining=3)
        rng = random.Random(1)
        game.apply(Action("Play", card=Card.SKIP), rng)
        self.assertEqual((0, 2), (game.current, game.remaining))
        game.apply(Action("Play", card=Card.SUPER_SKIP), rng)
        self.assertEqual((1, 1), (game.current, game.remaining))

    def test_bomb_choice_is_atomic_and_ends_all_remaining_actions(self):
        game = fixture([[Card.DEFUSE, Card.SKIP], []], [Card.BOMB], 4)
        rng = random.Random(2)
        game.apply(DRAW, rng)
        self.assertEqual(("Replace", 0), (game.phase, game.phase_player))
        self.assertFalse(game.is_legal(Action("Play", card=Card.SKIP)))
        self.assertEqual(0, game.current)
        game.check_invariants()
        game.observation(0).sample(rng).check_invariants()
        game.apply(Action("Replace", position=0), rng)
        self.assertEqual((1, 1), (game.current, game.remaining))
        self.assertEqual(Card.BOMB, game.deck[0])
        self.assertEqual(Card.BOMB, game.known[0][0])
        self.assertTrue(all(card is None for card in game.known[1]))
        self.assertEqual(("Play", None, ()), (game.phase, game.phase_player, game.phase_cards))
        game.check_invariants()

    def test_fatal_bomb_finishes_game_and_rejects_further_moves(self):
        game = fixture([[Card.SKIP], []], [Card.BOMB])
        rng = random.Random(1)
        game.apply(DRAW, rng)
        self.assertEqual(1, game.winner)
        self.assertFalse(game.legal_actions())
        before = game.clone()
        with self.assertRaises(ValueError):
            game.apply(Action("Play", card=Card.SKIP), rng)
        self.assertEqual(before, game)
        game.check_invariants()

    def test_full_hand_blocks_draw_but_bottom_card_frees_a_slot(self):
        hand = [Card.BOTTOM, Card.SKIP, Card.SKIP, Card.ATTACK, Card.ATTACK,
                Card.DEFUSE, Card.DEFUSE, Card.SEE3, Card.SHUFFLE]
        game = fixture([hand, []])
        safe = game.deck.index(Card.NOPE)
        game.deck[-1], game.deck[safe] = game.deck[safe], game.deck[-1]
        self.assertFalse(game.is_legal(DRAW))
        game.apply(Action("Play", card=Card.BOTTOM), random.Random(4))
        self.assertEqual(9, len(game.hands[0]))
        self.assertEqual(1, game.current)
        self.assertIn(Card.BOTTOM, game.discard)
        game.check_invariants()

    def test_future_is_private_and_reordering_preserves_cards(self):
        game = fixture([[Card.SEE3, Card.ALTER3], []],
                       [Card.BOMB, Card.SKIP, Card.DEFUSE])
        rng = random.Random(5)
        game.apply(Action("Play", card=Card.SEE3), rng)
        self.assertEqual(Card.BOMB, game.known[0][0])
        self.assertIsNone(game.known[1][0])
        game.apply(Action("Play", card=Card.ALTER3), rng)
        game.check_invariants()
        game.observation(0).sample(rng).check_invariants()
        waiting = game.observation(1)
        self.assertEqual(("Waiting", ()), (waiting.phase, waiting.phase_cards))
        with self.assertRaises(ValueError):
            waiting.sample(rng)
        reordered = (Card.SKIP, Card.BOMB, Card.DEFUSE)
        game.apply(Action("Order", cards=reordered), rng)
        self.assertEqual(list(reordered), game.deck[:3])
        self.assertEqual([None] * 3, game.known[1][:3])
        self.assertEqual(reordered, tuple(game.known[0][:3]))
        game.check_invariants()

    def test_keeping_original_future_never_duplicates_lower_cards(self):
        top = (Card.BOMB, Card.SKIP, Card.DEFUSE)
        game = fixture([[Card.ALTER3], []], top)
        rng = random.Random(1)
        before = game.deck.copy()
        game.apply(Action("Play", card=Card.ALTER3), rng)
        game.apply(Action("Order", cards=top), rng)
        self.assertEqual(before, game.deck)
        game.check_invariants()

    def test_malformed_order_and_out_of_range_placement_do_not_mutate(self):
        game = fixture([[Card.ALTER3], []], [Card.BOMB, Card.SKIP, Card.DEFUSE])
        rng = random.Random(1)
        game.apply(Action("Play", card=Card.ALTER3), rng)
        before = game.clone()
        for action in (Action("Order", cards=(Card.DEFUSE,) * 3),
                       Action("Order", cards=None), Action("Draw")):
            with self.assertRaises(ValueError):
                game.apply(action, rng)
            self.assertEqual(before, game)
        game.check_invariants()
        game = fixture([[Card.DEFUSE], []], [Card.BOMB])
        game.apply(DRAW, rng)
        before = game.clone()
        for position in (-1, len(game.deck) + 1, True, None):
            with self.assertRaises(ValueError):
                game.apply(Action("Replace", position=position), rng)
            self.assertEqual(before, game)
        game.check_invariants()

    def test_nope_cancels_function_card_but_not_drawing_or_defusing(self):
        game = fixture([[Card.NOPE, Card.SKIP], [Card.DEFUSE, Card.ATTACK]], [Card.BOMB])
        rng = random.Random(8)
        game.apply(Action("Play", card=Card.NOPE), rng)
        game.apply(Action("Play", card=Card.SKIP), rng)
        game.apply(Action("Play", card=Card.ATTACK), rng)
        self.assertIsNone(game.noped)
        self.assertEqual(1, game.current)
        self.assertIn(Card.ATTACK, game.discard)
        game.noped = 1
        game.apply(DRAW, rng)
        self.assertEqual(("Replace", 1), (game.phase, game.phase_player))
        self.assertEqual(1, game.noped)
        game.check_invariants()

    def test_shuffle_invalidates_memory_and_swap_moves_it(self):
        game = fixture([[Card.SEE5, Card.SWAP, Card.SHUFFLE], []])
        rng = random.Random(1)
        game.apply(Action("Play", card=Card.SEE5), rng)
        top = game.known[0][0]
        game.apply(Action("Play", card=Card.SWAP), rng)
        self.assertEqual(top, game.known[0][-1])
        game.apply(Action("Play", card=Card.SHUFFLE), rng)
        self.assertTrue(all(card is None for memory in game.known for card in memory))
        game.check_invariants()

    def test_known_draw_tracks_opponent_hand_until_publicly_played(self):
        game = fixture([[Card.SEE3, Card.SKIP], []], [Card.ATTACK, Card.NOPE])
        rng = random.Random(1)
        game.apply(Action("Play", card=Card.SEE3), rng)
        game.apply(Action("Play", card=Card.SKIP), rng)
        game.apply(DRAW, rng)
        self.assertIn(Card.ATTACK, game.known_opponent[0])
        game.apply(DRAW, rng)
        game.apply(Action("Play", card=Card.ATTACK), rng)
        self.assertNotIn(Card.ATTACK, game.known_opponent[0])
        game.check_invariants()

    def test_identical_observations_do_not_leak_hidden_deck_or_hand(self):
        game = Game.new(random.Random(20))
        view = game.observation(0)
        changed = game.clone()
        changed.deck.reverse()
        hand_index = next(i for i, card in enumerate(changed.hands[1]) if card != Card.DEFUSE)
        deck_index = next(i for i, card in enumerate(changed.deck) if card != Card.BOMB)
        changed.hands[1][hand_index], changed.deck[deck_index] = (
            changed.deck[deck_index], changed.hands[1][hand_index])
        changed.check_invariants()
        self.assertEqual(view, changed.observation(0))
        self.assertEqual(view.probability(0, Card.BOMB),
                         changed.observation(0).probability(0, Card.BOMB))

    def test_unknown_insertion_does_not_expose_index_through_memory(self):
        game = fixture([[Card.DEFUSE], []], [Card.BOMB])
        game.known[1] = game.deck.copy()
        rng = random.Random(1)
        game.apply(DRAW, rng)
        other = game.clone()
        game.apply(Action("Replace", position=0), rng)
        other.apply(Action("Replace", position=len(other.deck)), rng)
        self.assertEqual(game.observation(1), other.observation(1))
        self.assertNotEqual(game.observation(0), other.observation(0))

    def test_probability_distribution_sums_to_one(self):
        game = Game.new(random.Random(33))
        view = game.observation(0)
        self.assertAlmostEqual(1.0, sum(view.probability(0, card) for card in Card))
        self.assertAlmostEqual(4 / 22, view.probability(0, Card.BOMB))
        before = hash(view)
        counts = view._counts
        view.probability(1, Card.DEFUSE)
        self.assertIs(counts, view._counts)
        self.assertEqual(before, hash(view))

    def test_random_games_preserve_invariants_and_actor_sampling(self):
        finished = 0
        for seed in range(150):
            rng = random.Random(seed)
            game = Game.new(rng)
            for _ in range(250):
                game.check_invariants()
                if game.winner is not None:
                    finished += 1
                    break
                view = game.observation(game.current)
                view.sample(rng).check_invariants()
                actions = game.legal_actions()
                self.assertTrue(actions)
                game.apply(rng.choice(actions), rng)
        self.assertEqual(150, finished)

    def test_duplicate_cards_do_not_duplicate_reorder_actions(self):
        self.assertEqual(3, len(permutations([Card.BOMB, Card.BOMB, Card.SKIP])))
        self.assertEqual(120, len(permutations(
            [Card.ATTACK, Card.DEFUSE, Card.BOMB, Card.SKIP, Card.NOPE])))

    def test_clone_and_sample_lists_are_independent(self):
        game = Game.new(random.Random(53))
        before = game.clone()
        clone = game.clone()
        clone.deck.reverse()
        clone.hands[0].clear()
        clone.discard.append(Card.BOMB)
        clone.known[0].clear()
        clone.known_opponent[0].clear()
        self.assertEqual(before, game)
        sampled = game.observation(0).sample(random.Random(7))
        sampled.hands[0].clear()
        sampled.known[0].clear()
        self.assertEqual(before, game)

    def test_turn_revision_changes_only_when_an_action_is_finished(self):
        game = fixture([[Card.PERSONAL_ATTACK, Card.SEE3, Card.ALTER3,
                         Card.DEFUSE, Card.ATTACK], []], [Card.BOMB])
        rng = random.Random(5)
        for card in (Card.PERSONAL_ATTACK, Card.SEE3, Card.ALTER3):
            game.apply(Action("Play", card=card), rng)
            self.assertEqual(0, game.turn_revision)
        game.apply(Action("Order", cards=game.phase_cards), rng)
        self.assertEqual(0, game.turn_revision)
        game.apply(DRAW, rng)
        self.assertEqual(("Replace", 0), (game.phase, game.turn_revision))
        game.apply(Action("Replace", position=0), rng)
        self.assertEqual(1, game.turn_revision)
        self.assertEqual(1, game.clone().turn_revision)
        game.current = 0
        game.apply(Action("Play", card=Card.ATTACK), rng)
        self.assertEqual(2, game.turn_revision)

    def test_wire_helpers_preserve_all_variants_and_private_phases(self):
        for card in Card:
            self.assertEqual(card, card_from_wire(card_to_wire(card)))
            self.assertIsInstance(card_value(card), float)
        actions = [DRAW, Action("Play", card=Card.SEE5), Action("Replace", position=7),
                   Action("Order", cards=(Card.BOMB, Card.ALTER5, Card.DEFUSE))]
        for action in actions:
            self.assertEqual(action, action_from_wire(action_to_wire(action)))
        game = fixture([[Card.ALTER5], []])
        game.apply(Action("Play", card=Card.ALTER5), random.Random(1))
        for player in (0, 1):
            view = game.observation(player)
            self.assertEqual(view, observation_from_wire(observation_to_wire(view)))
        wire = observation_to_wire(Game.new(random.Random(2)).observation(0))
        wire["deck"] = []
        with self.assertRaises(ValueError):
            observation_from_wire(wire)
        for action in ({"kind": "Draw", "card": "Bomb"},
                       {"kind": "Replace", "position": True},
                       {"kind": "Play", "card": "NotACard"}):
            with self.assertRaises(ValueError):
                action_from_wire(action)

    def test_inconsistent_observation_cannot_sample_a_hidden_world(self):
        view = Game.new(random.Random(5)).observation(0)
        for changed in (replace(view, known_opponent=(Card.DEFUSE,) * 5),
                        replace(view, known_deck=(None,)),
                        replace(view, hand=(Card.DEFUSE,) * 5)):
            with self.assertRaises(ValueError):
                changed.sample(random.Random(1))


if __name__ == "__main__":
    unittest.main()
