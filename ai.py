"""AI行为和牌堆认知模块"""

from dataclasses import dataclass
from collections import Counter
import random

from BombCat import (
    AlterFutureCard,
    AttackCard,
    BombCatCard,
    DefuseCard,
    DrawBottomCard,
    NopeCard,
    PersonalAttackCard,
    SeeFutureCard,
    ShuffleCard,
    SkipCard,
    SuperSkipCard,
    SwapCard,
)


LOOKAHEAD_DEPTH = 2
FUTURE_DISCOUNT = 0.65
LOW_RISK_BOMB_THRESHOLD = 0.20
HAND_LOW_THRESHOLD = 3
MULTI_PLAY_PENALTY = 2.5
NOPE_PLAY_BONUS = 10.0
NOPED_DRAW_BONUS = 12.0
NOPED_INVERT_FACTOR = 0.18


@dataclass
class ActionEval:
    action: tuple
    score: float
    reason: str


def _new_unknown_entry():
    return {"known": None}


def _new_known_entry(card):
    return {"known": card}


def init_ai_knowledge(game):
    """初始化AI的牌堆认知，初始时全部未知。"""
    game.ai_known = [_new_unknown_entry() for _ in range(len(game.deck.cards))]


def _normalize_knowledge(game):
    """将game.ai_known中的条目规范化为包含"known"键的字典形式，方便后续处理。"""
    normalized = []
    for entry in game.ai_known:
        if isinstance(entry, dict) and "known" in entry:
            normalized.append(entry)
        elif entry == "unknown":
            normalized.append(_new_unknown_entry())
        else:
            normalized.append(_new_known_entry(entry))
    game.ai_known = normalized


def on_shuffle(game):
    _normalize_knowledge(game)
    game.ai_known = [_new_unknown_entry() for _ in range(len(game.deck.cards))]


def on_swap_top_bottom(game):
    _normalize_knowledge(game)
    if len(game.ai_known) > 1:
        game.ai_known[0], game.ai_known[-1] = game.ai_known[-1], game.ai_known[0]


def on_draw(game, from_bottom=False):
    _normalize_knowledge(game)
    if not game.ai_known:
        return
    if from_bottom:
        game.ai_known.pop(0)
    else:
        game.ai_known.pop(-1)


def on_insert_known(game, pos, card):
    _normalize_knowledge(game)
    game.ai_known.insert(pos, _new_known_entry(card))


def on_insert_unknown(game, pos):
    _normalize_knowledge(game)
    game.ai_known.insert(pos, _new_unknown_entry())


def on_see_future(game, top_cards):
    """top_cards should be [top -> down]."""
    _normalize_knowledge(game)
    for i, card in enumerate(top_cards):
        idx = len(game.deck.cards) - 1 - i
        if 0 <= idx < len(game.ai_known):
            game.ai_known[idx] = _new_known_entry(card)


def on_remove_top(game, top_count):
    _normalize_knowledge(game)
    if top_count <= 0:
        return
    del game.ai_known[-top_count:]


def on_append_known(game, top_cards):
    """在洗牌或顶底互换等操作后，将已知的 top_cards 追加到 ai_known 中，保持与现有游戏行为一致。"""
    _normalize_knowledge(game)
    game.ai_known.extend(_new_known_entry(card) for card in top_cards)


def on_append_unknown(game, top_count):
    _normalize_knowledge(game)
    if top_count <= 0:
        return
    game.ai_known.extend(_new_unknown_entry() for _ in range(top_count))


def _remaining_type_counter(game):
    deck_counter = Counter(type(card) for card in game.deck.cards)
    known_counter = Counter()
    unknown_slots = 0

    for slot in game.ai_known:
        known = slot.get("known")
        if known is None:
            unknown_slots += 1
        else:
            known_counter[type(known)] += 1

    remaining = Counter()
    for cls, count in deck_counter.items():
        remaining[cls] = max(0, count - known_counter.get(cls, 0))

    return remaining, unknown_slots


def card_probability_at(game, idx, card_cls):
    """返回AI认知中牌堆索引idx处是card_cls类型的牌的概率。"""
    _normalize_knowledge(game)
    if not game.ai_known:
        return 0.0

    idx = idx % len(game.ai_known)
    slot = game.ai_known[idx]
    known = slot.get("known")
    if known is not None:
        return 1.0 if isinstance(known, card_cls) else 0.0

    remaining, unknown_slots = _remaining_type_counter(game)
    if unknown_slots <= 0:
        return 0.0
    return min(1.0, remaining.get(card_cls, 0) / unknown_slots)


def known_positions(game, card_cls):
    _normalize_knowledge(game)
    return [i for i, slot in enumerate(game.ai_known) if isinstance(slot.get("known"), card_cls)]


def _build_actions(game):
    actions = []
    if len(game.ai.hand) < game.ai.hand_limit:
        actions.append(("draw", None))

    playable = game.ai.get_specific_cards("playable")
    for card in playable:
        actions.append(("play", card))
    return actions


def _state_snapshot(game, played_this_turn=0):
    top_bomb = card_probability_at(game, -1, BombCatCard)
    top_defuse = card_probability_at(game, -1, DefuseCard)
    bottom_bomb = card_probability_at(game, 0, BombCatCard)
    bottom_defuse = card_probability_at(game, 0, DefuseCard)
    playable_scores = [
        _card_initial_score(c)
        for c in game.ai.get_specific_cards("playable")
    ]
    min_playable_score = min(playable_scores) if playable_scores else 0.0
    max_playable_score = max(playable_scores) if playable_scores else 0.0
    return {
        "has_defuse": game.ai.has_defuse(),
        "hand_size": len(game.ai.hand),
        "hand_limit": game.ai.hand_limit,
        "remaining_turns": game.remaining_turns,
        "top_bomb": top_bomb,
        "top_defuse": top_defuse,
        "bottom_bomb": bottom_bomb,
        "bottom_defuse": bottom_defuse,
        "played_this_turn": played_this_turn,
        "ai_is_noped": game.noped == game.ai,
        "can_play_nope": game.noped != game.player,
        "min_playable_score": min_playable_score,
        "max_playable_score": max_playable_score,
        "skip_count": len(game.ai.get_specific_cards(SkipCard)),
        "super_skip_count": len(game.ai.get_specific_cards(SuperSkipCard)),
        "shuffle_count": len(game.ai.get_specific_cards(ShuffleCard)),
    }


def _card_label(card):
    return getattr(card, "name", card.__class__.__name__)


def _card_initial_score(card):
    return float(getattr(card, "initial_score", 0.0))


def _simulate_action(state, action):
    """One-step abstract simulator for short-horizon search."""
    kind, card = action
    next_state = dict(state)
    reason_parts = []
    end_turn = False
    score = 0.0
    top_bomb = state["top_bomb"]
    hand_size = state["hand_size"]
    hand_is_low = hand_size <= HAND_LOW_THRESHOLD
    hand_low_gap = max(0, HAND_LOW_THRESHOLD + 1 - hand_size) if hand_is_low else 0
    low_risk_factor = max(0.0, (LOW_RISK_BOMB_THRESHOLD - top_bomb) / LOW_RISK_BOMB_THRESHOLD)

    if kind == "draw":
        p_bomb = state["top_bomb"]
        p_def = state["top_defuse"]
        death_prob = p_bomb if not state["has_defuse"] else 0.0
        score += (1.0 - p_bomb) * 18.0
        score += p_def * 12.0
        score -= death_prob * 90.0
        if state.get("ai_is_noped", False):
            score += NOPED_DRAW_BONUS
            reason_parts.append("当前被阻止，优先抽牌")
        score += 9.0 * hand_low_gap
        score += 6.0 * low_risk_factor
        if low_risk_factor > 0:
            reason_parts.append("低风险倾向补牌")
        if hand_is_low:
            if hand_size == 0:
                reason_parts.append("没手牌了")
            else:
                reason_parts.append(f"手牌少({state['hand_size']}/{state['hand_limit']})")
        reason_parts.append(f"堆顶炸弹概率={p_bomb:.1%}")
        reason_parts.append(f"堆顶拆除概率={p_def:.1%}")
        end_turn = True
        next_state["hand_size"] = min(state["hand_limit"], state["hand_size"] + 1)
        next_state["played_this_turn"] = 0
        return score, "；".join(reason_parts), next_state, end_turn

    # play card
    next_state["hand_size"] = max(0, state["hand_size"] - 1)
    plays_before = state.get("played_this_turn", 0)
    next_state["played_this_turn"] = plays_before + 1
    bottom_bomb = state["bottom_bomb"]
    remaining_turns = state["remaining_turns"]
    card_score = _card_initial_score(card)
    if state.get("ai_is_noped", False):
        min_s = state.get("min_playable_score", card_score)
        max_s = state.get("max_playable_score", card_score)
        inverted_score = min_s + max_s - card_score
        score += NOPED_INVERT_FACTOR * inverted_score
        reason_parts.append("被阻止态：低分牌优先消耗")

    if isinstance(card, DrawBottomCard):
        p_bomb = state["bottom_bomb"]
        p_def = state["bottom_defuse"]
        death_prob = p_bomb if not state["has_defuse"] else 0.0
        score += (1.0 - p_bomb) * 16.0
        score += p_def * 10.0
        score -= death_prob * 85.0
        reason_parts.append(f"堆底炸弹概率={p_bomb:.1%}")
        reason_parts.append(f"堆底拆除概率={p_def:.1%}")
        end_turn = True
    elif isinstance(card, SkipCard):
        score += 14.0 + 26.0 * top_bomb
        reason_parts.append("跳过可规避本次抽牌")
        reason_parts.append(f"顶牌炸弹风险={top_bomb:.1%}")
        end_turn = True
        # 需要跳过时，倾向消耗较低价值的跳过类卡。
        score -= 0.10 * card_score
    elif isinstance(card, SuperSkipCard):
        score += 18.0 + 22.0 * top_bomb + 4.0 * max(0, remaining_turns - 1)
        reason_parts.append("超级跳过可结束剩余抽牌")
        end_turn = True
        # 超级跳过通常价值更高，非极端风险时应更谨慎使用。
        score -= 0.15 * card_score * (1.0 - top_bomb)
        if low_risk_factor > 0 and state.get("super_skip_count", 0) <= 1:
            score -= 14.0 * low_risk_factor
            reason_parts.append("低风险且仅剩1张超级跳过，优先保留")
    elif isinstance(card, AttackCard):
        score += 16.0 + 24.0 * top_bomb
        reason_parts.append("攻击可转移抽牌压力")
        end_turn = True
    elif isinstance(card, ShuffleCard):
        # 抽象上只保留炸弹密度，清空位置信息
        avg_bomb = max(top_bomb, bottom_bomb)
        next_state["top_bomb"] = avg_bomb
        next_state["bottom_bomb"] = avg_bomb
        score += 6.0 + 18.0 * top_bomb
        reason_parts.append("洗牌重置高风险已知位置")
        if low_risk_factor > 0:
            score -= 12.0 * low_risk_factor
            # reason_parts.append("低风险不应无必要洗牌")
    elif isinstance(card, SwapCard):
        next_state["top_bomb"], next_state["bottom_bomb"] = bottom_bomb, top_bomb
        next_state["top_defuse"], next_state["bottom_defuse"] = state["bottom_defuse"], state["top_defuse"]
        score += 5.0 + 20.0 * (top_bomb - bottom_bomb)
        reason_parts.append("顶底互换转移顶牌风险")
    elif isinstance(card, SeeFutureCard):
        score += 8.0 + 8.0 * top_bomb
        reason_parts.append("预见未来提升信息优势")
    elif isinstance(card, AlterFutureCard):
        score += 10.0 + 12.0 * top_bomb
        reason_parts.append("改变未来可主动规避炸弹")
    elif isinstance(card, PersonalAttackCard):
        score += -6.0 + 10.0 * (1.0 - top_bomb)
        reason_parts.append("自我攻击倾向在低风险时使用")
    elif isinstance(card, NopeCard):
        if state.get("can_play_nope", True):
            score += NOPE_PLAY_BONUS
            reason_parts.append("提高拒绝卡使用倾向")
        else:
            score -= 80.0
            reason_parts.append("拒绝卡不能重复打出")
    else:
        score += 1.0
        reason_parts.append(f"出牌 {_card_label(card)}")

    # 低风险时降低主动消耗后备牌的倾向；手牌少(<=3)时优先保留后备牌。
    play_consumption_penalty = (8.0 * low_risk_factor) + (6.0 * hand_low_gap * (0.5 + 0.5 * low_risk_factor))
    if play_consumption_penalty > 0:
        score -= play_consumption_penalty

    # 将卡牌初始分纳入“保留成本”：低风险时高分牌更不应被消耗。
    preserve_weight = 0.08 + 0.16 * low_risk_factor
    score -= card_score * preserve_weight
    if low_risk_factor > 0 and card_score >= 30:
        reason_parts.append(f"尝试保留高分牌({_card_label(card)}={card_score:.0f})")

    # 单回合内连打多张牌轻微加罚：第二张开始逐步扣分。
    if plays_before > 0:
        multi_penalty = MULTI_PLAY_PENALTY * plays_before
        score -= multi_penalty
        reason_parts.append(f"连打{plays_before + 1}张牌轻罚={multi_penalty:.1f}")

    return score, "；".join(reason_parts), next_state, end_turn


def _action_value(state, action, remaining_cards, depth):
    base_score, reason, next_state, end_turn = _simulate_action(state, action)

    if depth <= 0 or end_turn:
        return base_score, reason

    # 抽象短期视野预测：假设我们可以选择一个更好的行动。
    future_scores = []
    for card in remaining_cards:
        future_scores.append(_simulate_action(next_state, ("play", card))[0])
    if next_state["hand_size"] < next_state["hand_limit"]:
        future_scores.append(_simulate_action(next_state, ("draw", None))[0])

    if future_scores:
        lookahead = max(future_scores)
        total = base_score + FUTURE_DISCOUNT * lookahead
        return total, f"{reason}；短视野评估={lookahead:.2f}"

    return base_score, reason


def ai_control(game, played_this_turn=0):
    """Score-driven AI action selection with probabilistic cognition."""
    _normalize_knowledge(game)
    actions = _build_actions(game)
    if not actions:
        return "draw", None

    state = _state_snapshot(game, played_this_turn=played_this_turn)
    state["ai_known"] = game.ai_known

    evals = []
    playable = game.ai.get_specific_cards("playable")
    for action in actions:
        # 如果当前行动是出牌，则从未来候选中移除一张同类型的牌，以模拟手牌消耗后的情况。
        remaining_cards = playable.copy()
        if action[0] == "play" and action[1] in remaining_cards:
            remaining_cards.remove(action[1])

        score, reason = _action_value(state, action, remaining_cards, depth=LOOKAHEAD_DEPTH - 1)
        evals.append(ActionEval(action=action, score=score, reason=reason))

    evals.sort(key=lambda x: x.score, reverse=True)
    best = evals[0]

    if game.gui and game.gui.debug_mode:
        game.gui.print(
            f"AI 决策: {best.action[0]} {'抽牌' if best.action[0] == 'draw' else _card_label(best.action[1])} | 评分={best.score:.2f}",
            debug=True,
        )
        game.gui.print(f"理由: {best.reason}", debug=True)
        for idx, item in enumerate(evals[1:3], start=2):
            label = "抽牌" if item.action[0] == "draw" else _card_label(item.action[1])
            game.gui.print(f"候选{idx}: {item.action[0]} {label} | 评分={item.score:.2f}", debug=True)

    return best.action


def ai_turn(game):
    """Execute one AI turn loop."""
    played_this_turn = 0
    while game.current_player.is_ai and game.ai.alive:
        action, _card = ai_control(game, played_this_turn=played_this_turn)
        if action == "play" and _card:
            while not game.play_card(game.ai, _card):
                game.gui.print("一次出牌失败", debug=True)
                playable = game.ai.get_specific_cards("playable")
                if not playable:
                    action, _card = "draw", None
                    break
                action, _card = "play", random.choice(playable)

            if action == "draw":
                game.gui.print("🖐 AI 选择抽牌", debug=True)
                if game.draw_card(game.ai):
                    break

            played_this_turn += 1

            if game.end_turn or game.end_all_turn:
                break
        elif action == "draw":
            game.gui.print("🖐 AI 选择抽牌")
            game.draw_card(game.ai)
            break
        else:
            game.gui.print("AI 无法执行操作", debug=True)
            break

    game.gui.update_gui()

if __name__ == "__main__":
    import BombCatGUI
    BombCatGUI.main()