"""Keep tests independent of real Telegram credentials and network access."""

import pytest


@pytest.fixture(autouse=True)
def isolate_telegram(monkeypatch):
    import app
    from app.services import telegram_notifier

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(app, "load_dotenv", lambda *args, **kwargs: None)

    def unexpected_network(*args, **kwargs):
        raise AssertionError("Tests must mock Telegram HTTP; real delivery is forbidden")

    monkeypatch.setattr(telegram_notifier, "urlopen", unexpected_network)
