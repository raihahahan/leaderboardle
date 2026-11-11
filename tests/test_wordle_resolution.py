from types import SimpleNamespace

from leaderboardle.bot import LeaderboardBot


def result(played, streak, distribution):
    return SimpleNamespace(
        played_total=played,
        current_streak=streak,
        distribution=distribution,
    )


def test_first_stats_screen_can_prove_latest_loss():
    item = result(4, 0, (0, 1, 0, 1, 0, 1))
    assert LeaderboardBot._resolve_wordle_stats(item, None) == (7, False)


def test_distribution_delta_finds_successful_row():
    previous = {"played": 4, "distribution": "[0, 1, 0, 1, 0, 1]"}
    item = result(5, 1, (0, 1, 1, 1, 0, 1))
    assert LeaderboardBot._resolve_wordle_stats(item, previous) == (3, True)


def test_unchanged_distribution_with_new_play_is_loss():
    previous = {"played": 5, "distribution": "[0, 1, 1, 1, 0, 1]"}
    item = result(6, 0, (0, 1, 1, 1, 0, 1))
    assert LeaderboardBot._resolve_wordle_stats(item, previous) == (7, False)
