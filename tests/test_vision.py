import cv2
import numpy as np

from leaderboardle.vision import (
    _classify_game,
    _extract_krillion_score,
    _extract_minecraftle,
    _parse_attempts,
)


def test_game_names():
    dark_portrait = np.zeros((1000, 800, 3), dtype=np.uint8)
    bright_banner = np.full((100, 500, 3), 220, dtype=np.uint8)
    assert _classify_game("Wordle 1,234 3/6", dark_portrait) == "Wordle"
    assert _classify_game("You won! Took 5 guesses", bright_banner) == "Minecraftle"
    assert _classify_game("You used 81 guesses. The best solution was 9 guesses.", dark_portrait) == "Poople"
    assert _classify_game("KRILLION DIVE LOG BETTER THAN 80% OF TODAY'S PLAYERS", dark_portrait) == "Krillion"
    assert _classify_game("random cat", dark_portrait) is None


def test_score_formats():
    assert _parse_attempts("Wordle 1,234 3/6") == (3, 6, True)
    assert _parse_attempts("Wordle 1,234 X/6") == (7, 6, False)
    assert _parse_attempts("Solved in 4 attempts") == (4, None, True)
    assert _extract_minecraftle("You won! Took 6 quesses.") == 6


def test_krillion_score_in_uncropped_landscape_result():
    image = np.full((638, 1114, 3), (28, 42, 52), dtype=np.uint8)
    cv2.putText(
        image,
        "280",
        (75, 205),
        cv2.FONT_HERSHEY_SIMPLEX,
        4,
        (245, 245, 245),
        8,
        cv2.LINE_AA,
    )

    assert _extract_krillion_score(image) == 280

