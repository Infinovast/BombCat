"""Observation-only single-observer information-set Monte Carlo tree search."""

from functools import lru_cache
from math import log, sqrt
from random import Random
from time import perf_counter

from game_core import Action, Card, Observation, action_to_wire, card_value


def move_key(action, actor, observer):
    """Hide an opponent's private order/position while preserving public actions."""
    if action.kind == "Play":
        return "Play", action.card
    if action.kind == "Replace":
        return "Replace", action.position if actor == observer else None
    if action.kind == "Order":
        return "Order", action.cards if actor == observer else None
    return ("Draw",)


@lru_cache(maxsize=8192)
def scored_actions(view: Observation):
    """Knowledge-based scores shared by search priors and rollout policy."""
    top = view.probability(0, Card.BOMB)
    bottom = view.probability(max(0, len(view.known_deck) - 1), Card.BOMB)
    defuses = view.hand.count(Card.DEFUSE)
    danger = 125.0 if defuses == 0 else 43.0 / defuses
    average = ((3.0 if view.phase == "Replace" else 4.0) / len(view.known_deck)
               if view.known_deck else 1.0)
    attack = Card.ATTACK in view.hand
    actions = []
    for action in view.actions():
        if action.kind == "Draw":
            score = 12.0 + max(0.0, 4.0 - len(view.hand)) * 3.0 - danger * top
        elif action.kind == "Play":
            card = action.card
            value = card_value(card)
            if view.noped == view.player:
                score = 1.0 - value * 0.6
            elif card == Card.ATTACK:
                score = danger * top + 6.0 + (view.remaining - 1.0) * 5.0 - value * 0.7
            elif card == Card.SKIP:
                score = danger * top - value * 0.7
            elif card == Card.SUPER_SKIP:
                score = danger * top + (view.remaining - 1.0) * 9.0 - value * 0.8
            elif card == Card.PERSONAL_ATTACK:
                score = 12.0 + top * 8.0 if attack else -15.0 - danger * top
            elif card == Card.NOPE:
                score = 2.0 + (1.0 - top) * 2.0 - value * 0.6
            elif card == Card.BOTTOM:
                score = 8.0 - danger * bottom - value * 0.6
            elif card == Card.SWAP:
                score = danger * (top - bottom) - value * 0.6
            elif card == Card.SHUFFLE:
                score = danger * (top - average) - value * 0.8
            elif card in (Card.SEE3, Card.SEE5):
                depth = 5 if card == Card.SEE5 else 3
                unknown = view.known_deck[:depth].count(None)
                score = 2.0 + unknown * 2.0 + top * 4.0 if unknown else -20.0
            elif card in (Card.ALTER3, Card.ALTER5):
                score = 3.0 + top * 20.0 - value * 0.2
            else:
                score = -1000.0
        elif action.kind == "Replace":
            pos = action.position
            score = 14.0 if pos == 0 else 5.0 if pos == 1 else 2.0 if pos == 2 else -pos * 0.3
        else:
            score = 0.0
            for i, card in enumerate(action.cards):
                own_draw = i < view.remaining or (i - view.remaining) % 2 == 1
                if card == Card.BOMB:
                    score += -80.0 if own_draw else 65.0
                else:
                    score += card_value(card) * (0.7 if own_draw else -0.25)
        actions.append((action, score))
    actions.sort(key=lambda item: item[1], reverse=True)
    if view.phase == "Arrange":
        del actions[8:]
    if defuses == 0 and view.noped != view.player and len(actions) > 1:
        def fatal(item):
            action = item[0]
            return (action.kind == "Draw" and top >= 1.0
                    or action.kind == "Play" and action.card == Card.BOTTOM and bottom >= 1.0)
        if any(not fatal(item) for item in actions):
            actions = [item for item in actions if not fatal(item)]
    return tuple(actions)


def rollout_action(view, rng):
    actions = scored_actions(view)
    if not actions:
        return None
    if rng.random() < 0.10:
        return actions[rng.randrange(len(actions))][0]
    best_action = None
    best_score = float("-inf")
    for action, prior in actions:
        score = prior + rng.uniform(-4.0, 4.0)
        if score >= best_score:
            best_action, best_score = action, score
    return best_action


def rollout(game, root, limit, rng):
    for _ in range(limit):
        if game.winner is not None:
            return float(game.winner == root)
        action = rollout_action(game.observation(game.current), rng)
        if action is None:
            break
        game.apply(action, rng)
    if game.winner is not None:
        return float(game.winner == root)
    own = sum(map(card_value, game.hands[root]))
    opponent = sum(map(card_value, game.hands[1 - root]))
    return min(0.95, max(0.05, 0.5 + (own - opponent) / 160.0))


def _cancelled(cancel):
    if cancel is None:
        return False
    return bool(cancel() if callable(cancel) else cancel.is_set())


def choose(view: Observation, *, iterations=700, time_limit_ms=650, seed=None,
           cancel=None, rollout_limit=120):
    """Choose from sampled hidden worlds; accept only an immutable observation."""
    if not isinstance(view, Observation):
        raise TypeError("Search accepts Observation, not authoritative Game")
    if type(iterations) is not int or iterations < 0:
        raise ValueError("iterations must be a nonnegative integer")
    if type(rollout_limit) is not int or rollout_limit < 0:
        raise ValueError("rollout_limit must be a nonnegative integer")
    if time_limit_ms is not None and (type(time_limit_ms) not in (int, float) or time_limit_ms < 0):
        raise ValueError("time_limit_ms must be nonnegative or None")
    started = perf_counter()
    deadline = None if time_limit_ms is None else started + time_limit_ms / 1000.0
    root_actions = scored_actions(view)
    if not root_actions:
        raise ValueError("No legal action")
    fallback = root_actions[0][0]
    rng = Random(seed)
    tree = {}
    completed = 0
    root_player = view.player
    for _ in range(iterations):
        if _cancelled(cancel) or deadline is not None and perf_counter() >= deadline:
            break
        game = view.sample(rng)
        path = []
        for _ in range(32):
            if game.winner is not None:
                break
            actor = game.current
            choices = scored_actions(game.observation(actor))
            if not choices:
                break
            info = game.observation(root_player)
            node = tree.setdefault(info, {})
            available = []
            seen = set()
            for action, prior in choices:
                key = move_key(action, actor, root_player)
                if key in seen:
                    continue
                seen.add(key)
                # Edge fields: visits, availability, root-player reward sum.
                edge = node.setdefault(key, [0, 0, 0.0])
                edge[1] += 1
                available.append((edge, action, prior))
            best = None
            best_score = float("-inf")
            for edge, action, prior in available:
                visits = edge[0]
                if visits == 0:
                    score = 1000.0 + prior / 150.0
                else:
                    mean = edge[2] / visits
                    exploitation = mean if actor == root_player else 1.0 - mean
                    score = (exploitation + 0.75 * sqrt(log(edge[1]) / visits)
                             + 0.15 * min(1.0, max(-1.0, prior / 100.0)) / (visits + 1.0))
                if score >= best_score:
                    best, best_score = (edge, action), score
            edge, action = best
            expanded = edge[0] == 0
            path.append(edge)
            game.apply(action, rng)
            if expanded:
                break
        reward = rollout(game, root_player, rollout_limit, rng)
        for edge in path:
            edge[0] += 1
            edge[2] += reward
        completed += 1
    root = tree.get(view, {})
    candidates = []
    for action, _ in root_actions:
        edge = root.get(move_key(action, root_player, root_player))
        visits = edge[0] if edge is not None else 0
        value = edge[2] / visits if visits else None
        candidates.append({"action": action_to_wire(action), "visits": visits, "value": value})
    candidates.sort(key=lambda item: (item["visits"], item["value"] if item["value"] is not None else 0.5),
                    reverse=True)
    action = candidates[0]["action"] if completed else action_to_wire(fallback)
    return {
        "action": action, "iterations": completed,
        "elapsed_ms": int((perf_counter() - started) * 1000),
        "selection": "most_visited" if completed else "heuristic_fallback",
        "candidates": candidates[:3],
    }
