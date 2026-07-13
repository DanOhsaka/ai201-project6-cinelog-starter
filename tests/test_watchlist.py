"""
tests/test_watchlist.py — CineLog

Tests for the watchlist service.
"""

import pytest
from datetime import datetime, timezone, timedelta
from app import create_app, db
from models import User, Film, WatchlistEntry
from services.watchlist_service import (
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    AlreadyOnWatchlistError,
    NotOnWatchlistError,
)
from services.collection_service import FilmNotFoundError


@pytest.fixture
def app():
    """Create an isolated test app with an in-memory database."""
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    """A user to use in tests."""
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    """A film to use in tests."""
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


# ── Nonexistent film (Comment 3) ─────────────────────────────────────────────

def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """
    Adding a film_id that doesn't exist in the database should raise
    FilmNotFoundError, not a database integrity error.
    """
    with app.app_context():
        fake_film_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=fake_film_id)


# ── Deduplication ────────────────────────────────────────────────────────────

def test_add_to_watchlist_duplicate_raises(app, sample_user, sample_film):
    """
    Adding the same film twice should raise AlreadyOnWatchlistError,
    not silently create a duplicate entry.
    """
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        with pytest.raises(AlreadyOnWatchlistError):
            add_to_watchlist(user_id=sample_user, film_id=sample_film)

        count = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count()
        assert count == 1


# ── Stretch: remove_from_watchlist ───────────────────────────────────────────

def test_remove_from_watchlist_removes_entry(app, sample_user, sample_film):
    """Removing a film that is on the watchlist should delete the entry."""
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)
        assert remove_from_watchlist(user_id=sample_user, film_id=sample_film) is True

        remaining = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert remaining is None


def test_remove_from_watchlist_missing_raises(app, sample_user, sample_film):
    """Removing a film that is not on the watchlist should raise NotOnWatchlistError."""
    with app.app_context():
        with pytest.raises(NotOnWatchlistError):
            remove_from_watchlist(user_id=sample_user, film_id=sample_film)


# ── Stretch: visibility parameter ────────────────────────────────────────────

def test_add_to_watchlist_respects_public_flag(app, sample_user, sample_film):
    """Callers can set public=False explicitly instead of relying on the default."""
    with app.app_context():
        entry = add_to_watchlist(
            user_id=sample_user, film_id=sample_film, public=False
        )
        assert entry.public is False


# ── Stretch: extra edge case — empty watchlist ───────────────────────────────

def test_get_watchlist_empty_returns_empty_list(app, sample_user):
    """
    A user with no watchlist entries should get [] — not None or an error.
    Chosen because empty lists are a common client bug (null vs []) and the
    GET endpoint should have a stable contract for new users.
    """
    with app.app_context():
        result = get_watchlist(sample_user)
        assert result == []


# ── Sort order (Comment 5) ───────────────────────────────────────────────────

def test_get_watchlist_returns_newest_first(app, sample_user):
    """get_watchlist() should return films sorted by date_added descending."""
    with app.app_context():
        film_a = Film(title="Alien", year=1979, genre="Horror")
        film_b = Film(title="Blade Runner", year=1982, genre="Sci-Fi")
        db.session.add_all([film_a, film_b])
        db.session.commit()

        earlier = datetime.now(timezone.utc) - timedelta(days=5)
        later = datetime.now(timezone.utc)

        entry_a = WatchlistEntry(
            user_id=sample_user, film_id=film_a.id, date_added=earlier
        )
        entry_b = WatchlistEntry(
            user_id=sample_user, film_id=film_b.id, date_added=later
        )
        db.session.add_all([entry_a, entry_b])
        db.session.commit()

        watchlist = get_watchlist(sample_user)
        titles = [f["title"] for f in watchlist]

        assert titles[0] == "Blade Runner"
        assert titles[1] == "Alien"
