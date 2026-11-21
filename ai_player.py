"""Tkinter adapter and logs for the observation-only local search AI."""

from collections import Counter
import sys

import ai_backend
import game_core
from cards import (
    AlterFutureCard, AttackCard, BombCatCard, DefuseCard, DrawBottomCard,
    NopeCard, PersonalAttackCard, SeeFutureCard, ShuffleCard, SkipCard,
    SuperSkipCard, SwapCard,
)


_CARD_TYPES = {
    BombCatCard: "Bomb", DefuseCard: "Defuse", NopeCard: "Nope",
    AttackCard: "Attack", PersonalAttackCard: "PersonalAttack",
    SkipCard: "Skip", SuperSkipCard: "SuperSkip", ShuffleCard: "Shuffle",
    DrawBottomCard: "Bottom", SwapCard: "Swap",
}
_WIRE_CARD_TYPES = {key: card_type for card_type, key in _CARD_TYPES.items()}
_PUBLIC_INVENTORY = Counter(game_core.card_to_wire(card) for card in game_core.standard_deck())


def card_to_wire(card):
    if isinstance(card, SeeFutureCard):
        return f"See{card.depth}"
    if isinstance(card, AlterFutureCard):
        return f"Alter{card.depth}"
    return _CARD_TYPES[type(card)]


def _new_unknown_entry():
    return {"known": None}


def _new_known_entry(card):
    return {"known": card}


def init_ai_knowledge(game):
    game.ai_known = [_new_unknown_entry() for _ in range(len(game.deck.cards))]
    # The guaranteed opening defuse is public. No opponent cards are inspected.
    game.ai_known_opponent = ["Defuse"]


def _normalize_knowledge(game):
    game.ai_known = [
        entry if isinstance(entry, dict) and "known" in entry
        else _new_unknown_entry() if entry == "unknown"
        else _new_known_entry(entry)
        for entry in game.ai_known
    ]


def on_shuffle(game):
    game.ai_known = [_new_unknown_entry() for _ in range(len(game.deck.cards))]


def on_swap_top_bottom(game):
    _normalize_knowledge(game)
    if len(game.ai_known) > 1:
        game.ai_known[0], game.ai_known[-1] = game.ai_known[-1], game.ai_known[0]


def on_draw(game, from_bottom=False):
    """Called after removing the physical card, before resolving the draw."""
    _normalize_knowledge(game)
    if not game.ai_known:
        return
    known = game.ai_known.pop(0 if from_bottom else -1)["known"]
    if game.current_player is game.player and known is not None:
        if not isinstance(known, BombCatCard):
            game.ai_known_opponent.append(card_to_wire(known))


def on_card_played(game, player, card):
    if player is game.player:
        key = card_to_wire(card)
        if key in game.ai_known_opponent:
            game.ai_known_opponent.remove(key)


def on_insert_known(game, pos, card):
    _normalize_knowledge(game)
    game.ai_known.insert(pos, _new_known_entry(card))


def on_insert_unknown(game, pos):
    # The human's secret position must not shift the AI's memory precisely.
    del pos
    on_shuffle(game)


def on_see_future(game, top_cards):
    """The AI legitimately viewed these cards in top-to-bottom order."""
    _normalize_knowledge(game)
    for i, card in enumerate(top_cards):
        idx = len(game.ai_known) - 1 - i
        if idx >= 0:
            game.ai_known[idx] = _new_known_entry(card)


def on_remove_top(game, top_count):
    _normalize_knowledge(game)
    if top_count > 0:
        del game.ai_known[-top_count:]


def on_append_known(game, top_cards):
    """Append in physical deck order: lower cards first, top card last."""
    _normalize_knowledge(game)
    game.ai_known.extend(_new_known_entry(card) for card in top_cards)


def on_append_unknown(game, top_count):
    _normalize_knowledge(game)
    game.ai_known.extend(_new_unknown_entry() for _ in range(top_count))


def known_positions(game, card_cls):
    _normalize_knowledge(game)
    return [i for i, slot in enumerate(game.ai_known)
            if isinstance(slot["known"], card_cls)]


def card_probability_at(game, idx, card_cls):
    """Estimate from the public inventory and observed cards, never the deck."""
    _normalize_knowledge(game)
    if not game.ai_known:
        return 0.0
    slot = game.ai_known[idx % len(game.ai_known)]["known"]
    if slot is not None:
        return float(isinstance(slot, card_cls))
    unseen = _PUBLIC_INVENTORY.copy()
    unseen.subtract(card_to_wire(card) for card in game.ai.hand)
    unseen.subtract(card_to_wire(card) for card in game.deck.discard_pile)
    unseen.subtract(game.ai_known_opponent)
    unseen.subtract(card_to_wire(slot["known"]) for slot in game.ai_known
                    if slot["known"] is not None)
    unknown = sum(slot["known"] is None for slot in game.ai_known)
    bombs = max(0, unseen["Bomb"])
    if not unknown:
        return 0.0
    if card_cls is BombCatCard:
        return min(1.0, bombs / unknown)
    if card_cls is SeeFutureCard:
        count = unseen["See3"] + unseen["See5"]
    elif card_cls is AlterFutureCard:
        count = unseen["Alter3"] + unseen["Alter5"]
    else:
        count = unseen[_CARD_TYPES[card_cls]]
    non_bombs = sum(max(0, n) for key, n in unseen.items() if key != "Bomb")
    return (max(0, unknown - bombs) / unknown * max(0, count) / non_bombs
            if non_bombs else 0.0)


def build_observation(game, kind="Play", cards=()):
    """Freeze only AI-visible data; the opponent hand is counted, not read."""
    if hasattr(game, "core"):
        view = game_core.observation_to_wire(game.core.observation(1))
        if kind != "Play":
            view["phase"] = {"kind": kind}
            if kind == "Arrange":
                view["phase"]["cards"] = [card_to_wire(card) for card in cards]
        return view
    _normalize_knowledge(game)
    phase = {"kind": kind}
    if kind == "Arrange":
        phase["cards"] = [card_to_wire(card) for card in cards]
    return {
        "player": 1,
        "current": 1 if game.current_player is game.ai else 0,
        "remaining": game.remaining_turns,
        "hand": sorted(card_to_wire(card) for card in game.ai.hand),
        "opponent_count": len(game.player.hand),
        "known_opponent": sorted(game.ai_known_opponent),
        "known_deck": [card_to_wire(slot["known"]) if slot["known"] else None
                       for slot in reversed(game.ai_known)],
        "discard": [card_to_wire(card) for card in game.deck.discard_pile],
        "phase": phase,
        "noped": (None if game.noped is None else 1 if game.noped is game.ai else 0),
        "winner": (0 if not game.ai.alive else 1 if not game.player.alive else None),
    }


def _short_wire_name(game, key):
    """Reuse the original UI's single source of card abbreviations."""
    if key in ("See3", "See5"):
        card = SeeFutureCard(depth=int(key[-1]))
    elif key in ("Alter3", "Alter5"):
        card = AlterFutureCard(depth=int(key[-1]))
    else:
        card = _WIRE_CARD_TYPES[key]()
    return game._card_short_name(card)


def _action_text(game, action):
    kind = action["kind"]
    if kind == "Draw":
        return "抽牌"
    if kind == "Play":
        return f"出{_short_wire_name(game, action['card'])}"
    if kind == "Replace":
        return f"放{_short_wire_name(game, 'Bomb')}→第{action['position'] + 1}位"
    return "重排[" + " ".join(_short_wire_name(game, key) for key in action["cards"]) + "]"


def _known_cards_text(game, cards):
    return "、".join(f"{_short_wire_name(game, key)}×{count}"
                    for key, count in Counter(cards).items()) or "无"


def _bomb_risk(view, index):
    """Use the same uniform unknown-position belief as the search, not the real deck."""
    deck = view["known_deck"]
    if not deck:
        return None
    if deck[index] is not None:
        return float(deck[index] == "Bomb")
    unseen = _PUBLIC_INVENTORY.copy()
    for cards in (view["hand"], view["discard"], view["known_opponent"]):
        unseen.subtract(cards)
    unseen.subtract(card for card in deck if card is not None)
    if view["phase"]["kind"] == "Replace":
        unseen["Bomb"] -= 1
    elif view["phase"]["kind"] == "Arrange":
        unseen.subtract(view["phase"]["cards"])
    return min(1.0, max(0, unseen["Bomb"]) / deck.count(None))


def _log_decision(game, view, result):
    """Show each decision field on its own line in debugging mode."""
    if not game.gui.debug_mode:
        return
    bomb = _short_wire_name(game, "Bomb")
    defuse = _short_wire_name(game, "Defuse")
    context = [f"余{view['remaining']}次", f"{defuse}{view['hand'].count('Defuse')}",
               f"对手{view['opponent_count']}张（已知{_known_cards_text(game, view['known_opponent'])}）"]
    if view["noped"] is not None:
        target = "AI" if view["noped"] == view["player"] else "玩家"
        context.append(f"{_short_wire_name(game, 'Nope')}待生效→{target}")
    phase = view["phase"]["kind"]
    if phase == "Play":
        for label, index in (("顶", 0), ("底", -1)):
            risk = _bomb_risk(view, index)
            if risk is not None:
                source = "记忆" if view["known_deck"][index] is not None else "推算"
                context.append(f"{label}{bomb}{risk:.1%}（{source}）")
    elif phase == "Arrange":
        context.append("待排[" + " ".join(_short_wire_name(game, key)
                                         for key in view["phase"]["cards"]) + "]（顶→底）")
    else:
        context.append("拆弹放回（位置从顶计）")

    iterations = result.get("iterations", 0)
    elapsed = result.get("elapsed_ms", 0)
    game.gui.print(f"AI 决策：{_action_text(game, result['action'])}", debug=True)
    game.gui.print(f"局面：{'；'.join(context)}", debug=True)
    search = f"{iterations}次/{elapsed}ms" + ("（启发式）" if not iterations else "")
    game.gui.print(f"搜索：{search}", debug=True)
    for index, candidate in enumerate(result.get("candidates", [])[:3], start=1):
        visits = candidate["visits"]
        value = candidate.get("value")
        estimate = f"值{value:.3f}" if visits and value is not None else "未评估"
        game.gui.print(
            f"候选{index}：{_action_text(game, candidate['action'])} | {visits}次/{estimate}",
            debug=True,
        )
    deck = view["known_deck"]
    memory = " ".join(_short_wire_name(game, key) if key is not None else "?" for key in deck)
    known = sum(key is not None for key in deck)
    game.gui.print(
        f"AI牌堆记忆（顶→底，已知{known}/{len(deck)}）：{memory or '(空)'}", debug=True,
    )


def _play_card_for_action(game, action):
    return next((card for card in game.ai.hand
                 if card_to_wire(card) == action.get("card")), None)


def _validate_action(game, action, kind, cards):
    if not isinstance(action, dict):
        raise RuntimeError("AI response does not contain an action")
    action_kind = action.get("kind")
    if kind == "Play":
        if action_kind == "Draw":
            if len(game.ai.hand) < game.ai.hand_limit and len(game.deck.cards) > 0:
                return
        elif action_kind == "Play":
            card = _play_card_for_action(game, action)
            if card is not None and not isinstance(card, (BombCatCard, DefuseCard)):
                if not (isinstance(card, NopeCard) and game.noped is game.player):
                    return
    elif kind == "Replace" and action_kind == "Replace":
        pos = action.get("position")
        if type(pos) is int and 0 <= pos <= len(game.deck.cards):
            return
    elif kind == "Arrange" and action_kind == "Order":
        order = action.get("cards")
        if isinstance(order, list) and Counter(order) == Counter(map(card_to_wire, cards)):
            return
    raise RuntimeError("AI returned an illegal action")


def ai_control(game, *, iterations=700, time_limit_ms=650, seed=None):
    """Synchronous observation-only entry point for scripted tests/tools."""
    view = build_observation(game)
    result = ai_backend.search(view, iterations=iterations,
                            time_limit_ms=time_limit_ms, seed=seed)
    action = result["action"]
    _validate_action(game, action, "Play", ())
    _log_decision(game, view, result)
    return ("draw", None) if action["kind"] == "Draw" else (
        "play", _play_card_for_action(game, action))


def _is_active(game):
    return (getattr(game.gui, "game", None) is game and game.game_running
            and game.ai.alive and game.player.alive and game.current_player is game.ai)


def cancel_search(game):
    task = getattr(game, "_ai_task", None)
    if task is not None:
        task.cancel()
    game._ai_task = None
    game._ai_pending = False


def _start_choice(game, kind, cards, callback):
    if not _is_active(game) or getattr(game, "_ai_pending", False):
        return
    cards = tuple(cards)
    view = build_observation(game, kind, cards)
    revision = getattr(game, "_turn_revision", 0)
    task = ai_backend.SearchTask(view)
    game._ai_task = task
    game._ai_pending = True

    def poll():
        if getattr(game, "_ai_task", None) is not task:
            task.cancel()
            return
        if (not _is_active(game) or getattr(game, "_turn_revision", 0) != revision
                or build_observation(game, kind, cards) != view):
            cancel_search(game)
            return
        # Results cannot advance the game behind an original Tk modal dialog.
        grab_current = getattr(game.gui.root, "grab_current", None)
        if (getattr(game.gui, "_ai_paused", False)
                or callable(grab_current) and grab_current() is not None):
            game.gui.root.after(25, poll)
            return
        done, result, error = task.poll()
        if not done:
            game.gui.root.after(25, poll)
            return
        game._ai_task = None
        game._ai_pending = False
        if error is not None:
            print(f"BombCat AI: {error}", file=sys.stderr)
            game.gui.print("AI 无法执行操作", debug=True)
            return
        try:
            action = result["action"]
            _validate_action(game, action, kind, cards)
        except (KeyError, TypeError, RuntimeError) as exc:
            print(f"BombCat AI: {exc}", file=sys.stderr)
            game.gui.print("AI 无法执行操作", debug=True)
            return
        _log_decision(game, view, result)
        callback(action)

    game.gui.root.after(25, poll)


def begin_private_choice(game, kind, cards, callback):
    """Search an AI-owned reinsertion or reorder; apply on the Tk thread."""
    if kind not in ("Replace", "Arrange"):
        raise ValueError("Expected an AI private-choice phase")
    _start_choice(game, kind, cards, callback)


def ai_turn(game):
    """Search one action in a worker, then continue only the current game."""
    if not _is_active(game) or getattr(game, "_ai_pending", False):
        return

    def apply(action):
        revision = getattr(game, "_turn_revision", 0)
        if action["kind"] == "Draw":
            game.gui.print("🖐 AI 选择抽牌")
            ok = game.draw_card(game.ai)
        else:
            ok = game.play_card(game.ai, _play_card_for_action(game, action))
        if not ok:
            game.gui.print("一次出牌失败", debug=True)
            return
        if (_is_active(game) and not getattr(game, "_ai_pending", False)
                and getattr(game, "_turn_revision", 0) == revision):
            game.gui.root.after(150, lambda: ai_turn(game))

    _start_choice(game, "Play", (), apply)
