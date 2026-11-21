"""Reproducible, seat-balanced search versus local heuristic benchmark."""

import argparse
import random
from time import perf_counter

from game_core import Game, action_from_wire
from search_ai import choose, scored_actions


def benchmark(*, pairs=8, iterations=400, seed=2026, emit=print):
    started = perf_counter()
    wins = unfinished = searches = 0
    for pair in range(pairs):
        for search_seat in range(2):
            rng = random.Random(seed + pair)
            game = Game.new(rng)
            for step in range(300):
                if game.winner is not None:
                    break
                view = game.observation(game.current)
                if game.current == search_seat:
                    searches += 1
                    result = choose(view, iterations=iterations, time_limit_ms=None,
                                    seed=seed ^ (pair * 1009) ^ (step * 7919))
                    action = action_from_wire(result["action"])
                else:
                    action = scored_actions(view)[0][0]
                game.apply(action, rng)
                game.check_invariants()
            if game.winner is None:
                unfinished += 1
            elif game.winner == search_seat:
                wins += 1
            emit(f"pair={pair} search_seat={search_seat} winner={game.winner}")
    completed = pairs * 2 - unfinished
    emit(f"search_wins={wins}/{completed} unfinished={unfinished} iterations={iterations} "
         f"searches={searches} elapsed={perf_counter() - started:.2f}s")
    rate = f"{wins / completed:.1%}" if completed else "n/a"
    emit(f"descriptive_win_rate={rate} paired_seeds={pairs} confidence_interval=not_estimated")
    return {"wins": wins, "completed": completed, "unfinished": unfinished, "searches": searches}


def _nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=_nonnegative, default=8)
    parser.add_argument("--iterations", type=_nonnegative, default=400)
    parser.add_argument("--seed", type=_nonnegative, default=2026)
    args = parser.parse_args(argv)
    result = benchmark(pairs=args.pairs, iterations=args.iterations, seed=args.seed)
    return 1 if result["unfinished"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
