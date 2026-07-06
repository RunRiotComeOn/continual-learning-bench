from types import SimpleNamespace

from src.interface import Query
from src.tasks.exploitable_poker.task import Poker, PokerAction


def test_terminal_observation_exposes_scored_hand_outcome() -> None:
    task = Poker(
        num_instances=2,
        opponent_policy="calling_station",
        opponent_name="Tom",
    )
    task.game = SimpleNamespace(
        players=[
            SimpleNamespace(chips=0),
            SimpleNamespace(chips=task.starting_chips),
        ]
    )
    task.system_folded = True
    task.bot_folded = False
    task.current_hand_actions = []
    task.hands_played = 0
    task.system_profit = 0

    def fake_start_fresh_hand() -> None:
        task.game = SimpleNamespace(
            is_hand_running=lambda: True,
            players=[
                SimpleNamespace(chips=task.starting_chips),
                SimpleNamespace(chips=task.starting_chips),
            ],
        )

    task._start_fresh_hand = fake_start_fresh_hand
    task._get_current_query = lambda: Query(
        prompt="next hand",
        response_schema=PokerAction,
        metadata={},
    )

    result = task._handle_hand_end(None)

    assert result.observation.metadata["reward"] == -100.0
    assert result.observation.metadata["success"] is False
