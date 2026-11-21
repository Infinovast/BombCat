"""Tkinter-facing views and presentation around the shared, window-free rules."""

from collections import Counter
import random

import ai_player as ai_behavior
import game_core
from cards import (
    AlterFutureCard, AttackCard, BombCatCard, DefuseCard, DrawBottomCard,
    NopeCard, PersonalAttackCard, SeeFutureCard, ShuffleCard, SkipCard,
    SuperSkipCard, SwapCard, prompt_card_order,
)


_FACTORIES = {
    game_core.Card.BOMB: BombCatCard, game_core.Card.DEFUSE: DefuseCard,
    game_core.Card.NOPE: NopeCard, game_core.Card.ATTACK: AttackCard,
    game_core.Card.PERSONAL_ATTACK: PersonalAttackCard, game_core.Card.SKIP: SkipCard,
    game_core.Card.SUPER_SKIP: SuperSkipCard, game_core.Card.SHUFFLE: ShuffleCard,
    game_core.Card.SEE3: lambda: SeeFutureCard(3), game_core.Card.SEE5: lambda: SeeFutureCard(5),
    game_core.Card.ALTER3: lambda: AlterFutureCard(3), game_core.Card.ALTER5: lambda: AlterFutureCard(5),
    game_core.Card.BOTTOM: DrawBottomCard, game_core.Card.SWAP: SwapCard,
}


def _code(card):
    return game_core.card_from_wire(ai_behavior.card_to_wire(card))


class Deck:
    """Display projection; all card movement is performed by game_core.Game."""

    def __init__(self):
        self.cards = []
        self.discard_pile = []
        self.amounts = Counter(type(_FACTORIES[card]()) for card in game_core.standard_deck())


class Player:
    def __init__(self, name, is_ai=False):
        self.name = name
        self.hand = []
        self.hand_limit = game_core.HAND_LIMIT
        self.init_limit = 6
        self.is_ai = is_ai
        self.alive = True

    def has_defuse(self):
        return any(isinstance(card, DefuseCard) for card in self.hand)

    def get_specific_cards(self, card_type):
        if card_type == "playable":
            return [card for card in self.hand if not isinstance(card, (DefuseCard, BombCatCard))]
        if card_type == "defensive":
            card_type = (SkipCard, AttackCard, ShuffleCard, DrawBottomCard, SwapCard, AlterFutureCard)
        elif card_type == "escape":
            card_type = (SkipCard, SuperSkipCard, AttackCard)
        return [card for card in self.hand if isinstance(card, card_type)] if isinstance(card_type, (type, tuple)) else []

    def hand_text(self):
        counts = Counter(card.name for card in self.hand)
        ordered = sorted(counts.items(), key=lambda item: (item[0] != DefuseCard().name, item[0]))
        return " | ".join(f"{name} ×{count}" for name, count in ordered)


class Game:
    def __init__(self, gui):
        self.gui = gui
        self._rng = random.Random(random.getrandbits(64))
        self.core = game_core.Game.new(self._rng)
        self.deck = Deck()
        self.player = Player("玩家")
        self.ai = Player("AI", is_ai=True)
        self._view_cards = [_FACTORIES[card]() for card in game_core.standard_deck()]
        self._held_cards = []
        self._ai_pending = False
        self._ai_task = None
        self.game_running = False
        self.end_turn = self.end_all_turn = False
        self.turn_owner = self.player
        self.turn_progress = self.turn_total = 1
        self.ai_known = []
        self.ai_known_opponent = []
        self._sync_from_core()
        gui.set_game(self)

    @property
    def current_player(self):
        return self.ai if self.core.current else self.player

    @current_player.setter
    def current_player(self, player):
        self.core.current = int(player is self.ai)

    @property
    def remaining_turns(self):
        return self.core.remaining

    @remaining_turns.setter
    def remaining_turns(self, value):
        self.core.remaining = value

    @property
    def noped(self):
        return None if self.core.noped is None else self.ai if self.core.noped else self.player

    @noped.setter
    def noped(self, player):
        self.core.noped = None if player is None else int(player is self.ai)

    @property
    def _turn_revision(self):
        return self.core.turn_revision

    def _sync_from_core(self, *, extra_discard=(), drawn=None, held=None, deck_fixed=None):
        """Project enum zones back to stable card objects used by existing widgets."""
        used = set()
        deck_fixed = deck_fixed or {}
        reserved = {id(card) for card in deck_fixed.values()}

        def assign(codes, preferred):
            result = []
            for code in codes:
                card = next((card for card in preferred
                             if id(card) not in used and id(card) not in reserved and _code(card) == code), None)
                if card is None:
                    card = next(card for card in self._view_cards
                                if id(card) not in used and id(card) not in reserved and _code(card) == code)
                used.add(id(card))
                result.append(card)
            return result

        self.deck.discard_pile = assign(self.core.discard, [*self.deck.discard_pile, *extra_discard])
        for index, player in enumerate((self.player, self.ai)):
            preferred = player.hand + ([drawn] if drawn is not None and self.core.phase != "Replace"
                                       and index == self._last_actor else [])
            player.hand = assign(self.core.hands[index], preferred)
            player.alive = self.core.winner is None or self.core.winner == index
        held_codes = (game_core.Card.BOMB,) if self.core.phase == "Replace" else self.core.phase_cards
        self._held_cards = assign(held_codes, list(held if held is not None else self._held_cards))
        top_first = []
        old_deck = list(reversed(self.deck.cards))
        for index, code in enumerate(self.core.deck):
            if index in deck_fixed:
                card = deck_fixed[index]
                if _code(card) != code:
                    raise ValueError("Card projection does not match the rules state")
                used.add(id(card))
                top_first.append(card)
            else:
                top_first.extend(assign((code,), old_deck))
        self.deck.cards = list(reversed(top_first))
        self.ai_known = [{"known": top_first[index] if card is not None else None}
                         for index, card in reversed(list(enumerate(self.core.known[1])))]
        self.ai_known_opponent = [game_core.card_to_wire(card) for card in self.core.known_opponent[1]]

    def _sync_to_core(self):
        """Import explicitly arranged view fixtures; normal play only writes through core.apply."""
        self.core.deck = [_code(card) for card in reversed(self.deck.cards)]
        self.core.hands = [[_code(card) for card in player.hand] for player in (self.player, self.ai)]
        self.core.discard = [_code(card) for card in self.deck.discard_pile]
        self.core.known[1] = [_code(slot["known"]) if slot["known"] is not None else None
                              for slot in reversed(self.ai_known)]
        if len(self.core.known[1]) != len(self.core.deck):
            self.core.known[1] = [None] * len(self.core.deck)
        self.core.known[0] = [None] * len(self.core.deck)
        self.core.known_opponent[1] = [game_core.card_from_wire(card) for card in self.ai_known_opponent]
        for observer in (0, 1):
            available = Counter(self.core.hands[1 - observer])
            kept = []
            for card in self.core.known_opponent[observer]:
                if available[card]:
                    kept.append(card)
                    available[card] -= 1
            self.core.known_opponent[observer] = kept

    def _apply(self, action, *, played=None):
        before = self.core.clone()
        self._last_actor = before.current
        drawn = None
        if action.kind == "Draw" or (action.kind == "Play" and action.card == game_core.Card.BOTTOM
                                     and before.noped != before.current):
            drawn = self.deck.cards[0 if action.kind == "Play" else -1]
        held = self._held_cards[:]
        extra_discard = [played] if played is not None else []
        if drawn is not None and isinstance(drawn, BombCatCard):
            defuse = next((card for card in (self.ai if before.current else self.player).hand
                           if isinstance(card, DefuseCard)), None)
            extra_discard.append(defuse if defuse is not None else drawn)
            held = [drawn]
        if action.kind == "Play" and action.card in (game_core.Card.ALTER3, game_core.Card.ALTER5):
            depth = 5 if action.card == game_core.Card.ALTER5 else 3
            held = list(reversed(self.deck.cards[-depth:]))
        fixed = {}
        if action.kind == "Replace":
            fixed[action.position] = self._held_cards[0]
        elif action.kind == "Order":
            remaining = held.copy()
            for index, code in enumerate(action.cards):
                card = next(card for card in remaining if _code(card) == code)
                remaining.remove(card)
                fixed[index] = card
        self.core.apply(action, self._rng)
        self._sync_from_core(extra_discard=extra_discard, drawn=drawn, held=held, deck_fixed=fixed)
        return before, drawn

    def _active(self):
        return self.gui.game is self and self.game_running and self.core.winner is None

    def play_card(self, player, card):
        if isinstance(card, list):
            card = card[0] if card else None
        if (not self._active() or player is not self.current_player or self._ai_pending
                or card not in player.hand):
            return False
        action = game_core.Action("Play", card=_code(card))
        if not self.core.is_legal(action):
            if isinstance(card, NopeCard) and self.noped is self.get_other(player):
                self.gui.print(f"❌ 已存在 {'AI' if player.is_ai else '玩家'} 打出的拒绝卡，请勿重复打出")
            return False
        blocked = self.noped is player
        previous, drawn = self._apply(action, played=card)
        turn_finished = self._turn_revision != previous.turn_revision
        if blocked:
            self.gui.print(f"🚫 {player.name} 打出的 {card.name} 被 {self.get_other(player).name} 的拒绝卡阻止")
        else:
            self.gui.print(f"🎴 {player.name} 使用了 {card.name}")
            self._present_card(card, player, previous, drawn)
        if self.gui.game is not self:
            return True
        if not self._ai_pending and self.core.phase == "Play":
            if turn_finished:
                self._next_turn()
            elif (self._turn_revision == previous.turn_revision
                  and not (isinstance(card, NopeCard) and player.is_ai)):
                self.gui.print("───────/───────")
        self.check_game_end()
        self.gui.update_gui()
        return True

    def draw_card(self, player, from_bottom=False):
        if not self._active() or player is not self.current_player or self._ai_pending:
            return False
        if len(player.hand) >= player.hand_limit:
            self.gui.print(f"🈵 {player.name}手牌已满 (上限为{self.player.hand_limit}张)，请先出牌！")
            return False
        if from_bottom:
            return False  # Bottom draws are part of the card action, never a second rule operation.
        if not self.core.is_legal(game_core.DRAW):
            return False
        previous, card = self._apply(game_core.DRAW)
        turn_finished = self._turn_revision != previous.turn_revision
        self._present_draw(player, card, previous)
        if self.gui.game is self and self.core.phase == "Play" and turn_finished:
            self._next_turn()
        self.check_game_end()
        self.gui.update_gui()
        return True

    def _present_card(self, card, player, previous, drawn):
        target = self.get_other(player)
        if isinstance(card, NopeCard):
            self.gui.print(f"🚫 {'AI' if player.is_ai else '玩家'} 打出拒绝，{'玩家' if player.is_ai else 'AI'} 下次出牌将失效", debug=player.is_ai)
        elif isinstance(card, AttackCard):
            self.gui.print(f"🔥 {player.name} 发动攻击！{target.name} 将要连续行动 {self.remaining_turns} 回合")
        elif isinstance(card, PersonalAttackCard):
            self.gui.print(f"🔥 {player.name} 发动自我攻击，将连续行动 {self.remaining_turns} 回合")
        elif isinstance(card, SuperSkipCard):
            self.gui.print(f"🚀 {player.name} 跳过了剩余所有回合")
        elif isinstance(card, SkipCard):
            self.gui.print(f"⏭️ {player.name} 跳过了回合")
        elif isinstance(card, ShuffleCard):
            self.gui.print("🔀 牌堆被重新洗牌！")
        elif isinstance(card, SwapCard):
            self.gui.print(f"🔄 {player.name} 交换了牌堆顶部和底部的牌" if len(self.deck.cards) > 1 else "😔 牌堆中牌不足，无法进行顶底互换")
        elif isinstance(card, DrawBottomCard):
            self.gui.print(f"👇 {player.name} 从牌堆底部抽牌")
            self._present_draw(player, drawn, previous)
        elif isinstance(card, SeeFutureCard):
            top = list(reversed(self.deck.cards[-card.depth:]))
            self.gui.print(f"🔮 {player.name} 查看了牌堆顶的{len(top)}张牌")
            if player.is_ai:
                self.gui.print(f"🤖 AI 记录了牌堆顶{len(top)}张牌的信息")
                self.gui.print("🔽 AI 看到的牌堆顶（从上到下）:", debug=True)
            else:
                self.gui.print("🔽 牌堆顶的牌（从上到下）:")
            for index, value in enumerate(top):
                self.gui.print(f"{index + 1}. {value.name}", debug=player.is_ai)
        elif isinstance(card, AlterFutureCard):
            self._arrange(player, card.depth)

    def _present_draw(self, player, card, previous):
        if isinstance(card, BombCatCard):
            self.gui.print(f"💣 {player.name} 抽到了炸弹猫！")
            if self.core.phase == "Replace":
                self.gui.print(f"🛠 {player.name} 使用拆除卡...")
                self._replace(player, previous.remaining)
            else:
                self.gui.print(f"💥 {player.name} 没有拆除卡！爆炸了！")
        elif player.is_ai and not self.gui.debug_mode:
            self.gui.print("🤖 AI 完成抽牌")
        else:
            self.gui.print(f"🖐 {player.name} 抽到了 {card.name}")

    def _replace(self, player, remaining):
        def complete(action):
            if not self._active():
                return
            self._apply(game_core.action_from_wire(action))
            if player.is_ai:
                if self.gui.debug_mode:
                    self.gui.print(f"AI 将{self._card_short_name(BombCatCard())}放回第{action['position'] + 1}位（从顶部计）", debug=True)
                else:
                    self.gui.print("🤖 AI 将炸弹猫放回牌堆某个位置")
            if remaining >= 2:
                self.gui.print(f"💣⏭️ {player.name} 剩余的 {remaining - 1} 个回合立即结束")
            self._next_turn()

        if player.is_ai:
            ai_behavior.begin_private_choice(self, "Replace", [], complete)
        else:
            pos = self.gui.prompt_bomb_position(len(self.deck.cards))
            if not self._active():
                return
            if pos is None:
                pos = self._rng.randint(0, len(self.deck.cards))
                rank = len(self.deck.cards) - pos + 1
                self.gui.print(f"📌 随机将{self._card_short_name(BombCatCard())}放回第{rank}位（从顶部计）")
            complete({"kind": "Replace", "position": len(self.deck.cards) - pos})

    def _arrange(self, player, depth):
        original = self._held_cards[:]
        self.gui.print(f"🔄 {player.name} 正在重新排列牌堆顶的{len(original)}张牌")

        def complete(action):
            if not self._active():
                return
            self._apply(game_core.action_from_wire(action))
            if player.is_ai:
                self.gui.print("🤖 AI 重新排列了牌堆顶的牌")
                self.gui.print("🔽 AI 改变未来前（从上到下）:", debug=True)
                for index, card in enumerate(original):
                    self.gui.print(f"{index + 1}. {card.name}", debug=True)
                self.gui.print("🔽 AI 改变未来后（从上到下）:", debug=True)
                for index, card in enumerate(reversed(self.deck.cards[-len(original):])):
                    self.gui.print(f"{index + 1}. {card.name}", debug=True)
                self.gui.print("───────/───────")
                self.gui.update_gui()
                if self._active():
                    self.gui.root.after(50, self.ai_turn)

        if player.is_ai:
            ai_behavior.begin_private_choice(self, "Arrange", original, complete)
        else:
            order = prompt_card_order(self, depth, original)
            if order is not None and self._active():
                complete({"kind": "Order", "cards": [ai_behavior.card_to_wire(card) for card in order]})

    def _next_turn(self):
        if not self._active():
            return
        self._advance_turn_counter(self.turn_owner is not self.current_player)
        self.gui.update_gui()
        if not self._active():
            return
        if self.current_player.is_ai:
            self.gui.draw_button.config(state="disabled")
            self.gui.play_button.config(state="disabled")
            self.gui.print(f"\n────────── 🤖 AI回合 {self.get_turn_counter_text()} ──────────\n💡 AI 正在思考...")
            self.print_debug_deck_snapshot()
            self.gui.schedule_ai_turn()
        else:
            self.gui.print(f"\n────────── 👤 玩家回合 {self.get_turn_counter_text()} ──────────\n🧠 请出牌或抽牌...")
            self.print_debug_deck_snapshot()
            self.gui.draw_button.config(state="normal")
            self.gui.play_button.config(state="normal")

    def check_game_end(self):
        if self.core.winner is not None and self.game_running and self.gui.game is self:
            self.game_running = False
            ai_behavior.cancel_search(self)
            self.gui.game_end()
            return True
        return False

    def _sync_turn_counter(self):
        if self.turn_owner is not self.current_player:
            self.turn_owner = self.current_player
            self.turn_progress = 1
            self.turn_total = max(1, self.remaining_turns)
        else:
            self.turn_total = max(self.turn_total, self.remaining_turns, self.turn_progress)

    def _advance_turn_counter(self, switched_player):
        if switched_player or self.turn_owner is not self.current_player:
            self.turn_owner = self.current_player
            self.turn_progress = 1
            self.turn_total = max(1, self.remaining_turns)
        else:
            self.turn_progress += 1
            self.turn_total = max(self.turn_total, self.remaining_turns, self.turn_progress)

    def get_turn_counter_text(self):
        self._sync_turn_counter()
        progress = max(1, self.turn_progress)
        return f"{progress}/{max(progress, self.turn_total)}"

    def get_other(self, player):
        return self.ai if player is self.player else self.player

    def ai_control(self):
        return ai_behavior.ai_control(self)

    def ai_turn(self):
        ai_behavior.ai_turn(self)

    def ai_on_shuffle(self):
        ai_behavior.on_shuffle(self)

    def ai_on_see_future(self, cards):
        ai_behavior.on_see_future(self, cards)

    def ai_on_insert_known(self, pos, card):
        ai_behavior.on_insert_known(self, pos, card)

    def ai_on_insert_unknown(self, pos):
        ai_behavior.on_insert_unknown(self, pos)

    @staticmethod
    def _card_short_name(card):
        if isinstance(card, SeeFutureCard):
            return "预5" if card.depth == 5 else "预"
        if isinstance(card, AlterFutureCard):
            return "改5" if card.depth == 5 else "改"
        return {BombCatCard: "炸", DefuseCard: "拆", NopeCard: "阻", AttackCard: "攻",
                PersonalAttackCard: "自", SkipCard: "跳", SuperSkipCard: "超",
                ShuffleCard: "洗", SwapCard: "换", DrawBottomCard: "底"}.get(type(card), "?")

    def print_debug_deck_snapshot(self, top_n=6, bottom_n=3):
        if not self.gui.debug_mode:
            return
        cards = self.deck.cards
        if not cards:
            self.gui.print("真实牌堆（调试）：(空)", debug=True)
            return
        top_count, bottom_count = min(top_n, len(cards)), min(bottom_n, len(cards))
        top = " ".join(self._card_short_name(card) for card in reversed(cards[-top_count:]))
        bottom = " ".join(self._card_short_name(card) for card in reversed(cards[:bottom_count]))
        separator = "..." if top_count + bottom_count < len(cards) else " "
        self.gui.print(f"真实牌堆（调试）：{top}{separator}{bottom}", debug=True)
