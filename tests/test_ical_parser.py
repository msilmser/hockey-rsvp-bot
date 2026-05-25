import pytest
from datetime import datetime, date, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from icalendar import Calendar, Event
import pytz

from ical_parser import ICalParser

TIMEZONE = pytz.timezone('America/Toronto')

# Build SAMPLE_ICAL with dates relative to now so the test window never goes
# stale.  game1 = 30 days out, game2 = 37 days out — both safely inside the
# days=365 window used in the tests.
_now = datetime.now(timezone.utc)
_fmt = '%Y%m%dT%H%M%SZ'
_g1_start = (_now + timedelta(days=30)).strftime(_fmt)
_g1_end   = (_now + timedelta(days=30, hours=2)).strftime(_fmt)
_g2_start = (_now + timedelta(days=37)).strftime(_fmt)
_g2_end   = (_now + timedelta(days=37, hours=2)).strftime(_fmt)

SAMPLE_ICAL = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
DTSTART:{_g1_start}
DTEND:{_g1_end}
SUMMARY:Rivals FC @ Mighty Pucks
LOCATION:Test Arena
DESCRIPTION:Game night
UID:game-home-001@test.com
END:VEVENT
BEGIN:VEVENT
DTSTART:{_g2_start}
DTEND:{_g2_end}
SUMMARY:Mighty Pucks @ Ice Kings
LOCATION:Away Arena
DESCRIPTION:Away game
UID:game-away-001@test.com
END:VEVENT
END:VCALENDAR
""".encode()


@pytest.fixture
def parser():
    return ICalParser('https://example.com/cal.ics', TIMEZONE)


class TestExtractOpponent:
    def test_home_game_returns_away_team(self, parser):
        assert parser._extract_opponent('Rivals FC @ Mighty Pucks') == 'Rivals FC'

    def test_away_game_returns_home_team(self, parser):
        assert parser._extract_opponent('Mighty Pucks @ Ice Kings') == 'Ice Kings'

    def test_no_at_symbol_returns_full_summary(self, parser):
        assert parser._extract_opponent('Mystery Game') == 'Mystery Game'

    def test_case_insensitive_team_name(self, parser):
        assert parser._extract_opponent('Rivals FC @ MIGHTY PUCKS') == 'Rivals FC'


class TestIsHomeGame:
    def test_home_game(self, parser):
        assert parser._is_home_game('Rivals FC @ Mighty Pucks') is True

    def test_away_game(self, parser):
        assert parser._is_home_game('Mighty Pucks @ Ice Kings') is False

    def test_no_at_symbol_returns_none(self, parser):
        assert parser._is_home_game('Mystery Game') is None

    def test_case_insensitive(self, parser):
        assert parser._is_home_game('Rivals @ MIGHTY PUCKS') is True


class TestParseEvent:
    def _make_event(self, summary, uid, dtstart, location='Arena', description=''):
        event = Event()
        from icalendar import vDatetime, vText
        event.add('SUMMARY', summary)
        event.add('UID', uid)
        event.add('DTSTART', dtstart)
        event.add('LOCATION', location)
        event.add('DESCRIPTION', description)
        return event

    def test_parses_datetime_event(self, parser):
        dt = datetime(2026, 4, 25, 19, 0, 0, tzinfo=pytz.utc)
        event = self._make_event('Rivals FC @ Mighty Pucks', 'uid-001', dt)
        game = parser._parse_event(event)
        assert game is not None
        assert game['id'] == 'uid-001'
        assert game['opponent'] == 'Rivals FC'
        assert game['is_home'] is True
        assert game['location'] == 'Arena'

    def test_parses_date_only_event(self, parser):
        event = self._make_event('Mighty Pucks @ Ice Kings', 'uid-002', date(2026, 4, 30))
        game = parser._parse_event(event)
        assert game is not None
        assert game['is_home'] is False

    def test_returns_none_on_missing_dtstart(self, parser):
        event = Event()
        event.add('SUMMARY', 'Bad Event')
        event.add('UID', 'uid-bad')
        assert parser._parse_event(event) is None


class TestGetUpcomingGames:
    @pytest.mark.asyncio
    async def test_returns_games_from_calendar(self, parser):
        calendar = Calendar.from_ical(SAMPLE_ICAL)
        with patch.object(parser, 'fetch_calendar', new=AsyncMock(return_value=calendar)):
            games = await parser.get_upcoming_games(days=365)
        assert len(games) == 2
        ids = {g['id'] for g in games}
        assert 'game-home-001@test.com' in ids
        assert 'game-away-001@test.com' in ids

    @pytest.mark.asyncio
    async def test_returns_empty_on_fetch_failure(self, parser):
        with patch.object(parser, 'fetch_calendar', new=AsyncMock(return_value=None)):
            games = await parser.get_upcoming_games(days=7)
        assert games == []

    @pytest.mark.asyncio
    async def test_results_sorted_by_start_time(self, parser):
        calendar = Calendar.from_ical(SAMPLE_ICAL)
        with patch.object(parser, 'fetch_calendar', new=AsyncMock(return_value=calendar)):
            games = await parser.get_upcoming_games(days=365)
        times = [g['start_time'] for g in games]
        assert times == sorted(times)


class TestGetGameById:
    @pytest.mark.asyncio
    async def test_finds_game_by_uid(self, parser):
        calendar = Calendar.from_ical(SAMPLE_ICAL)
        with patch.object(parser, 'fetch_calendar', new=AsyncMock(return_value=calendar)):
            game = await parser.get_game_by_id('game-home-001@test.com')
        assert game is not None
        assert game['id'] == 'game-home-001@test.com'

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_uid(self, parser):
        calendar = Calendar.from_ical(SAMPLE_ICAL)
        with patch.object(parser, 'fetch_calendar', new=AsyncMock(return_value=calendar)):
            game = await parser.get_game_by_id('does-not-exist')
        assert game is None
