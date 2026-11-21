"""Window-free BombCat rules shared by the actual game and local AI simulations.

Deck positions are always measured from the top, starting at index zero.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from itertools import chain


HAND_LIMIT = 9


class Card(IntEnum):
    BOMB = 0
    DEFUSE = 1
    NOPE = 2
    ATTACK = 3
    PERSONAL_ATTACK = 4
    SKIP = 5
    SUPER_SKIP = 6
    SHUFFLE = 7
    SEE3 = 8
    SEE5 = 9
    ALTER3 = 10
    ALTER5 = 11
    BOTTOM = 12
    SWAP = 13


_CARDS = tuple(Card)
_COUNTS = (4, 4, 3, 4, 3, 3, 2, 2, 1, 1, 2, 1, 2, 2)
_VALUES = (-100.0, 30.0, 6.0, 13.0, 2.0, 10.0, 15.0, 7.0,
           6.0, 8.0, 10.0, 12.0, 8.0, 6.0)
_WIRE_NAMES = ("Bomb", "Defuse", "Nope", "Attack", "PersonalAttack", "Skip",
               "SuperSkip", "Shuffle", "See3", "See5", "Alter3", "Alter5", "Bottom", "Swap")
_FROM_WIRE = dict(zip(_WIRE_NAMES, _CARDS))
_STANDARD_DECK = tuple(card for card, count in zip(_CARDS, _COUNTS) for _ in range(count))


def standard_deck():
    return list(_STANDARD_DECK)


def card_value(card):
    return _VALUES[card]


def card_to_wire(card):
    if not isinstance(card, Card):
        raise ValueError("Expected a Card")
    return _WIRE_NAMES[card]


def card_from_wire(value):
    try:
        return _FROM_WIRE[value]
    except (KeyError, TypeError):
        raise ValueError(f"Unknown card: {value!r}") from None


@dataclass(frozen=True, slots=True)
class Action:
    kind: str
    card: Card | None = None
    position: int | None = None
    cards: tuple[Card, ...] = ()


DRAW = Action("Draw")


def permutations(cards):
    """Unique permutations in the same canonical order as the rules model."""
    def visit(prefix, rest):
        if not rest:
            yield tuple(prefix)
            return
        for index, card in enumerate(rest):
            if index and card == rest[index - 1]:
                continue
            prefix.append(card)
            yield from visit(prefix, rest[:index] + rest[index + 1:])
            prefix.pop()

    return list(visit([], sorted(cards)))


@dataclass(frozen=True, slots=True)
class Observation:
    player: int
    current: int
    remaining: int
    hand: tuple[Card, ...]
    opponent_count: int
    known_opponent: tuple[Card, ...]
    known_deck: tuple[Card | None, ...]
    discard: tuple[Card, ...]
    phase: str = "Play"
    phase_cards: tuple[Card, ...] = ()
    noped: int | None = None
    winner: int | None = None
    _counts: tuple[int, ...] | None = field(default=None, init=False, repr=False,
                                          compare=False, hash=False)
    _unknown: int = field(default=-1, init=False, repr=False, compare=False, hash=False)

    def _unseen_counts(self):
        if self._counts is not None:
            return self._counts
        if self.phase == "Waiting":
            raise ValueError("Cannot sample during another player's private choice")
        counts = list(_COUNTS)
        visible = chain(self.hand, self.discard, self.known_opponent,
                        (card for card in self.known_deck if card is not None),
                        (Card.BOMB,) if self.phase == "Replace" else self.phase_cards)
        for card in visible:
            if not isinstance(card, Card) or counts[card] <= 0:
                raise ValueError(f"Inconsistent observation: {card!r}")
            counts[card] -= 1
        result = tuple(counts)
        object.__setattr__(self, "_counts", result)
        object.__setattr__(self, "_unknown", self.known_deck.count(None))
        return result

    def probability(self, index, card):
        if not 0 <= index < len(self.known_deck):
            return 0.0
        slot = self.known_deck[index]
        if slot is not None:
            return float(slot == card)
        try:
            counts = self._unseen_counts()
        except ValueError:
            return 0.0
        unknown = self._unknown
        if not unknown:
            return 0.0
        bombs = counts[Card.BOMB]
        if card == Card.BOMB:
            return min(1.0, max(0.0, bombs / unknown))
        non_bombs = sum(counts) - bombs
        if not non_bombs:
            return 0.0
        return min(1.0, max(0.0, (unknown - bombs) / unknown * counts[card] / non_bombs))

    def sample(self, rng):
        if self.player not in (0, 1) or self.current not in (0, 1):
            raise ValueError("Player numbers must be 0 or 1")
        if len(self.known_opponent) > self.opponent_count:
            raise ValueError("Known opponent cards exceed their hand size")
        counts = self._unseen_counts()
        pool = [card for card, count in zip(_CARDS, counts) for _ in range(count)]
        rng.shuffle(pool)
        opponent = list(self.known_opponent)
        for _ in range(self.opponent_count - len(opponent)):
            index = next((i for i, card in enumerate(pool) if card != Card.BOMB), None)
            if index is None:
                raise ValueError("Not enough non-bomb cards for the opponent")
            opponent.append(pool.pop(index))
        rng.shuffle(pool)
        deck = []
        for card in self.known_deck:
            if card is None:
                if not pool:
                    raise ValueError("Missing deck card")
                card = pool.pop()
            deck.append(card)
        if pool:
            raise ValueError("Unassigned cards in observation")
        hands = [[], []]
        hands[self.player] = list(self.hand)
        hands[1 - self.player] = opponent
        known = [[None] * len(deck), [None] * len(deck)]
        known[self.player] = list(self.known_deck)
        known_opponent = [[], []]
        known_opponent[self.player] = list(self.known_opponent)
        return Game(deck, hands, list(self.discard), self.current, self.remaining,
                    self.phase, self.player if self.phase != "Play" else None,
                    self.phase_cards, self.noped, self.winner, known, known_opponent)

    def actions(self):
        if self.winner is not None or self.current != self.player:
            return []
        if self.phase == "Play":
            cards = sorted(set(card for card in self.hand
                               if card not in (Card.BOMB, Card.DEFUSE)
                               and not (card == Card.NOPE and self.noped == 1 - self.player)))
            actions = [Action("Play", card=card) for card in cards]
            if len(self.hand) < HAND_LIMIT and self.known_deck:
                actions.append(DRAW)
            return actions
        if self.phase == "Replace":
            return [Action("Replace", position=pos) for pos in range(len(self.known_deck) + 1)]
        if self.phase == "Arrange":
            return [Action("Order", cards=order) for order in permutations(self.phase_cards)]
        return []


@dataclass(slots=True)
class Game:
    deck: list[Card]
    hands: list[list[Card]]
    discard: list[Card]
    current: int = 0
    remaining: int = 1
    phase: str = "Play"
    phase_player: int | None = None
    phase_cards: tuple[Card, ...] = ()
    noped: int | None = None
    winner: int | None = None
    known: list[list[Card | None]] = field(default_factory=lambda: [[], []])
    known_opponent: list[list[Card]] = field(default_factory=lambda: [[], []])
    revision: int = 0
    turn_revision: int = 0

    @classmethod
    def new(cls, rng):
        deck = standard_deck()
        hands = [[Card.DEFUSE], [Card.DEFUSE]]
        deck.remove(Card.DEFUSE)
        deck.remove(Card.DEFUSE)
        rng.shuffle(deck)
        for hand in hands:
            for _ in range(5):
                index = next(i for i, card in enumerate(deck) if card != Card.BOMB)
                hand.append(deck.pop(index))
        rng.shuffle(deck)
        return cls(deck, hands, [], known=[[None] * len(deck), [None] * len(deck)],
                   known_opponent=[[Card.DEFUSE], [Card.DEFUSE]])

    def clone(self):
        return Game(self.deck.copy(), [hand.copy() for hand in self.hands], self.discard.copy(),
                    self.current, self.remaining, self.phase, self.phase_player,
                    self.phase_cards, self.noped, self.winner,
                    [memory.copy() for memory in self.known],
                    [cards.copy() for cards in self.known_opponent],
                    self.revision, self.turn_revision)

    def observation(self, player):
        if player not in (0, 1):
            raise ValueError("Player number must be 0 or 1")
        visible = self.phase == "Play" or self.phase_player == player
        return Observation(player, self.current, self.remaining,
                           tuple(sorted(self.hands[player])), len(self.hands[1 - player]),
                           tuple(sorted(self.known_opponent[player])), tuple(self.known[player]),
                           tuple(self.discard), self.phase if visible else "Waiting",
                           self.phase_cards if visible and self.phase == "Arrange" else (),
                           self.noped, self.winner)

    def legal_actions(self):
        return self.observation(self.current).actions()

    def is_legal(self, action):
        if self.winner is not None or not isinstance(action, Action):
            return False
        if action.kind != "Play" and action.card is not None:
            return False
        if action.kind != "Replace" and action.position is not None:
            return False
        if not isinstance(action.cards, tuple) or (action.kind != "Order" and action.cards):
            return False
        if self.phase == "Play":
            if action.kind == "Draw":
                return len(self.hands[self.current]) < HAND_LIMIT and bool(self.deck)
            if action.kind == "Play":
                return (isinstance(action.card, Card)
                        and action.card not in (Card.BOMB, Card.DEFUSE)
                        and action.card in self.hands[self.current]
                        and not (action.card == Card.NOPE and self.noped == 1 - self.current)
                        and (action.card != Card.BOTTOM or bool(self.deck)))
        elif self.phase == "Replace" and action.kind == "Replace":
            return (self.phase_player == self.current and type(action.position) is int
                    and 0 <= action.position <= len(self.deck))
        elif self.phase == "Arrange" and action.kind == "Order":
            return (self.phase_player == self.current
                    and all(isinstance(card, Card) for card in action.cards)
                    and sorted(action.cards) == sorted(self.phase_cards))
        return False

    def apply(self, action, rng):
        if not self.is_legal(action):
            raise ValueError(f"Illegal action: {action!r}")
        actor = self.current
        self.revision += 1
        kind = action.kind
        if kind == "Draw":
            self._draw(False)
        elif kind == "Replace":
            self.deck.insert(action.position, Card.BOMB)
            self.known[actor].insert(action.position, Card.BOMB)
            self.known[1 - actor] = [None] * len(self.deck)
            self.phase, self.phase_player, self.phase_cards = "Play", None, ()
            self._finish(True)
        elif kind == "Order":
            self.deck[:0] = action.cards
            self.known[actor][:0] = action.cards
            self.known[1 - actor][:0] = [None] * len(action.cards)
            self.phase, self.phase_player, self.phase_cards = "Play", None, ()
        else:
            card = action.card
            self._consume(actor, card)
            if self.noped == actor:
                self.noped = None
                return
            if card == Card.NOPE:
                self.noped = 1 - actor
            elif card == Card.ATTACK:
                self.remaining += 1
                self.current = 1 - actor
                self.turn_revision += 1
            elif card == Card.PERSONAL_ATTACK:
                self.remaining += 2
            elif card == Card.SKIP:
                self._finish(False)
            elif card == Card.SUPER_SKIP:
                self._finish(True)
            elif card == Card.SHUFFLE:
                rng.shuffle(self.deck)
                self.known = [[None] * len(self.deck), [None] * len(self.deck)]
            elif card == Card.SWAP:
                if len(self.deck) >= 2:
                    self.deck[0], self.deck[-1] = self.deck[-1], self.deck[0]
                    for memory in self.known:
                        memory[0], memory[-1] = memory[-1], memory[0]
            elif card == Card.BOTTOM:
                self._draw(True)
            elif card in (Card.SEE3, Card.SEE5):
                count = min(5 if card == Card.SEE5 else 3, len(self.deck))
                self.known[actor][:count] = self.deck[:count]
            elif card in (Card.ALTER3, Card.ALTER5):
                count = min(5 if card == Card.ALTER5 else 3, len(self.deck))
                self.phase_cards = tuple(self.deck[:count])
                del self.deck[:count]
                for memory in self.known:
                    del memory[:count]
                self.phase, self.phase_player = "Arrange", actor

    def _consume(self, owner, card):
        self.hands[owner].remove(card)
        self.discard.append(card)
        known = self.known_opponent[1 - owner]
        if card in known:
            known.remove(card)

    def _draw(self, bottom):
        actor = self.current
        index = -1 if bottom else 0
        seen = self.known[1 - actor][index]
        card = self.deck.pop(index)
        for memory in self.known:
            memory.pop(index)
        if card == Card.BOMB:
            if Card.DEFUSE in self.hands[actor]:
                self._consume(actor, Card.DEFUSE)
                self.phase, self.phase_player = "Replace", actor
            else:
                self.discard.append(card)
                self.winner = 1 - actor
        else:
            self.hands[actor].append(card)
            if seen is not None:
                self.known_opponent[1 - actor].append(seen)
            self._finish(False)

    def _finish(self, all_actions):
        self.turn_revision += 1
        if all_actions or self.remaining <= 1:
            self.current = 1 - self.current
            self.remaining = 1
        else:
            self.remaining -= 1

    def check_invariants(self):
        if self.current not in (0, 1) or self.remaining <= 0:
            raise ValueError("Invalid current player or remaining action count")
        if self.noped not in (None, 0, 1) or self.winner not in (None, 0, 1):
            raise ValueError("Invalid player marker")
        if len(self.hands) != 2 or len(self.known) != 2 or len(self.known_opponent) != 2:
            raise ValueError("Expected exactly two players")
        cards = list(chain(self.deck, *self.hands, self.discard))
        if self.phase == "Replace":
            cards.append(Card.BOMB)
        elif self.phase == "Arrange":
            cards.extend(self.phase_cards)
        elif self.phase != "Play":
            raise ValueError("Invalid game phase")
        if self.phase != "Play" and self.phase_player != self.current:
            raise ValueError("Private choice does not belong to the current player")
        if sorted(cards) != sorted(_STANDARD_DECK):
            raise ValueError("Card inventory is not conserved")
        for player in (0, 1):
            if len(self.hands[player]) > HAND_LIMIT or Card.BOMB in self.hands[player]:
                raise ValueError("Invalid hand")
            if len(self.known[player]) != len(self.deck):
                raise ValueError("Memory length differs from deck")
            if any(known is not None and known != actual
                   for known, actual in zip(self.known[player], self.deck)):
                raise ValueError("Stale positional memory")
            unseen_hand = self.hands[1 - player].copy()
            for card in self.known_opponent[player]:
                if card not in unseen_hand:
                    raise ValueError("Stale opponent memory")
                unseen_hand.remove(card)


def action_to_wire(action):
    if action.kind == "Draw":
        return {"kind": "Draw"}
    if action.kind == "Play":
        return {"kind": "Play", "card": card_to_wire(action.card)}
    if action.kind == "Replace":
        return {"kind": "Replace", "position": action.position}
    if action.kind == "Order":
        return {"kind": "Order", "cards": [card_to_wire(card) for card in action.cards]}
    raise ValueError("Unknown action kind")


def action_from_wire(value):
    if not isinstance(value, dict):
        raise ValueError("Action must be an object")
    kind = value.get("kind")
    expected = {"Draw": {"kind"}, "Play": {"kind", "card"},
                "Replace": {"kind", "position"}, "Order": {"kind", "cards"}}
    if kind not in expected or set(value) != expected[kind]:
        raise ValueError("Invalid action fields")
    if kind == "Draw":
        return DRAW
    if kind == "Play":
        return Action(kind, card=card_from_wire(value["card"]))
    if kind == "Replace":
        if type(value["position"]) is not int or value["position"] < 0:
            raise ValueError("Invalid replacement position")
        return Action(kind, position=value["position"])
    if not isinstance(value["cards"], list):
        raise ValueError("Order cards must be an array")
    return Action(kind, cards=tuple(card_from_wire(card) for card in value["cards"]))


def observation_to_wire(view):
    phase = {"kind": view.phase}
    if view.phase == "Arrange":
        phase["cards"] = [card_to_wire(card) for card in view.phase_cards]
    return {
        "player": view.player, "current": view.current, "remaining": view.remaining,
        "hand": [card_to_wire(card) for card in view.hand], "opponent_count": view.opponent_count,
        "known_opponent": [card_to_wire(card) for card in view.known_opponent],
        "known_deck": [None if card is None else card_to_wire(card) for card in view.known_deck],
        "discard": [card_to_wire(card) for card in view.discard], "phase": phase,
        "noped": view.noped, "winner": view.winner,
    }


def observation_from_wire(value):
    fields = {"player", "current", "remaining", "hand", "opponent_count", "known_opponent",
              "known_deck", "discard", "phase", "noped", "winner"}
    required = fields - {"noped", "winner"}
    if not isinstance(value, dict) or not required <= set(value) <= fields:
        raise ValueError("Invalid observation fields")
    for field_name in ("player", "current", "remaining", "opponent_count"):
        if type(value[field_name]) is not int:
            raise ValueError(f"{field_name} must be an integer")
    if value["player"] not in (0, 1) or value["current"] not in (0, 1):
        raise ValueError("Player numbers must be 0 or 1")
    if not 1 <= value["remaining"] <= 1000 or not 0 <= value["opponent_count"] <= HAND_LIMIT:
        raise ValueError("Invalid action or hand count")
    for field_name in ("noped", "winner"):
        marker = value.get(field_name)
        if marker is not None and (type(marker) is not int or marker not in (0, 1)):
            raise ValueError(f"Invalid {field_name} marker")
    arrays = ("hand", "known_opponent", "known_deck", "discard")
    if any(not isinstance(value[name], list) for name in arrays):
        raise ValueError("Card collections must be arrays")
    if (len(value["hand"]) > HAND_LIMIT or len(value["known_deck"]) > 34
            or len(value["discard"]) > 34
            or len(value["known_opponent"]) > value["opponent_count"]):
        raise ValueError("Card counts exceed the game limits")
    phase = value["phase"]
    if not isinstance(phase, dict) or phase.get("kind") not in ("Play", "Replace", "Arrange", "Waiting"):
        raise ValueError("Invalid observation phase")
    arranging = phase["kind"] == "Arrange"
    if set(phase) != ({"kind", "cards"} if arranging else {"kind"}):
        raise ValueError("Invalid phase fields")
    phase_cards = ()
    if arranging:
        if not isinstance(phase["cards"], list) or not 1 <= len(phase["cards"]) <= 5:
            raise ValueError("Arrange requires between 1 and 5 cards")
        phase_cards = tuple(card_from_wire(card) for card in phase["cards"])
    return Observation(value["player"], value["current"], value["remaining"],
                       tuple(sorted(card_from_wire(card) for card in value["hand"])),
                       value["opponent_count"],
                       tuple(sorted(card_from_wire(card) for card in value["known_opponent"])),
                       tuple(None if card is None else card_from_wire(card) for card in value["known_deck"]),
                       tuple(card_from_wire(card) for card in value["discard"]),
                       phase["kind"], phase_cards, value.get("noped"), value.get("winner"))
