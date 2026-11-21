"""Version-1 JSON-lines interface to the local Python information-set AI."""

import json
import random
import secrets
import sys

from game_core import Card, HAND_LIMIT, observation_from_wire
from search_ai import choose


VERSION = 1
MAX_REQUEST_BYTES = 65536
_REQUEST_FIELDS = {"version", "id", "observation", "iterations", "time_limit_ms", "seed"}
_OBSERVATION_FIELDS = {
    "player", "current", "remaining", "hand", "opponent_count", "known_opponent",
    "known_deck", "discard", "phase", "noped", "winner",
}


def _integer(value, label, low=0, high=2**64 - 1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer between {low} and {high}")
    return value


def _object(value, allowed, required, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if set(value) - allowed:
        raise ValueError(f"Unknown {label} fields: {', '.join(sorted(set(value) - allowed))}")
    if required - set(value):
        raise ValueError(f"Missing {label} fields: {', '.join(sorted(required - set(value)))}")


def validate_observation(value):
    _object(value, _OBSERVATION_FIELDS, _OBSERVATION_FIELDS - {"noped", "winner"}, "observation")
    player = _integer(value["player"], "player", high=1)
    current = _integer(value["current"], "current", high=1)
    if player != current:
        raise ValueError("Only the current player's observation can request an action")
    _integer(value["remaining"], "remaining", low=1, high=1000)
    opponent_count = _integer(value["opponent_count"], "opponent_count", high=HAND_LIMIT)
    for field, limit in (("hand", HAND_LIMIT), ("known_opponent", opponent_count),
                         ("known_deck", 34), ("discard", 34)):
        if not isinstance(value[field], list) or len(value[field]) > limit:
            raise ValueError(f"Invalid {field} card count")
    if value.get("noped") is not None:
        _integer(value["noped"], "noped", high=1)
    if value.get("winner") is not None:
        raise ValueError("Cannot search a finished game")
    if "Bomb" in value["discard"]:
        raise ValueError("A discarded bomb is only valid in a finished game")
    phase = value["phase"]
    _object(phase, {"kind", "cards"}, {"kind"}, "phase")
    if phase["kind"] not in ("Play", "Replace", "Arrange"):
        raise ValueError("Unknown phase")
    if phase["kind"] == "Arrange":
        cards = phase.get("cards")
        if not isinstance(cards, list) or not 1 <= len(cards) <= 5:
            raise ValueError("Arrange must contain between 1 and 5 cards")
    elif "cards" in phase:
        raise ValueError("Only Arrange may contain phase cards")
    view = observation_from_wire(value)
    if Card.BOMB in view.hand or Card.BOMB in view.known_opponent:
        raise ValueError("Bombs cannot be held in a hand")
    sample = view.sample(random.Random(0))
    sample.check_invariants()
    if not view.actions():
        raise ValueError("Observation has no legal action")
    return view


def process_request(request):
    """Return one success/failure value without accepting authoritative state."""
    request_id = None
    try:
        if isinstance(request, dict):
            value = request.get("id")
            if type(value) is int and 0 <= value < 2**64:
                request_id = value
        _object(request, _REQUEST_FIELDS, {"version", "id", "observation"}, "request")
        if type(request["version"]) is not int or request["version"] != VERSION:
            raise ValueError("Unsupported protocol version; expected 1")
        _integer(request["id"], "id")
        view = validate_observation(request["observation"])
        iterations = request.get("iterations")
        iterations = 700 if iterations is None else min(20000, _integer(iterations, "iterations"))
        time_limit_ms = request.get("time_limit_ms")
        time_limit_ms = 650 if time_limit_ms is None else min(5000, _integer(time_limit_ms, "time_limit_ms"))
        seed = request.get("seed")
        seed = secrets.randbits(64) if seed is None else _integer(seed, "seed")
        result = choose(view, iterations=iterations, time_limit_ms=time_limit_ms, seed=seed)
        return {"version": VERSION, "id": request_id, **result}
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        return {"version": VERSION, "id": request_id, "error": str(error)}


def process_line(line):
    if len(line.encode("utf-8")) > MAX_REQUEST_BYTES:
        result = {"version": VERSION, "id": None, "error": "Request exceeds 65536 bytes"}
    else:
        try:
            request = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"Invalid JSON number: {value}")))
            result = process_request(request)
        except (ValueError, TypeError) as error:
            result = {"version": VERSION, "id": None, "error": f"Invalid JSON: {error}"}
    return json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def main():
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        if line.strip():
            print(process_line(line), flush=True)


if __name__ == "__main__":
    main()
