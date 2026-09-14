"""Subprocess mode: Claude repeats the last assistant text in the result event."""

from telegram_bot.core.handlers.streaming import is_duplicate_final


def test_is_duplicate_final() -> None:
    assert is_duplicate_final("Готово.\n", "Готово.")
    assert not is_duplicate_final("", "Готово.")
    assert not is_duplicate_final("Сначала посмотрю.", "Готово.")
