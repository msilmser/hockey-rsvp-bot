import pytest
import pytest_asyncio
from datetime import datetime, timedelta
import pytz

from database import Database

TIMEZONE = pytz.timezone('America/Toronto')


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / 'test.db'))
    await database.initialize()
    return database


def future(hours=48):
    return datetime.now(TIMEZONE) + timedelta(hours=hours)


def past(hours=48):
    return datetime.now(TIMEZONE) - timedelta(hours=hours)


class TestCreateAndGetPoll:
    @pytest.mark.asyncio
    async def test_create_and_retrieve_by_game_id(self, db):
        await db.create_poll('game-001', 111111, future())
        poll = await db.get_poll_by_game_id('game-001')
        assert poll is not None
        assert poll['game_id'] == 'game-001'
        assert poll['message_id'] == 111111

    @pytest.mark.asyncio
    async def test_create_and_retrieve_by_message_id(self, db):
        await db.create_poll('game-002', 222222, future())
        poll = await db.get_poll_by_message_id(222222)
        assert poll is not None
        assert poll['game_id'] == 'game-002'

    @pytest.mark.asyncio
    async def test_missing_game_id_returns_none(self, db):
        assert await db.get_poll_by_game_id('nope') is None

    @pytest.mark.asyncio
    async def test_missing_message_id_returns_none(self, db):
        assert await db.get_poll_by_message_id(999) is None


class TestRsvp:
    @pytest_asyncio.fixture
    async def poll_id(self, db):
        await db.create_poll('game-rsvp', 333333, future())
        poll = await db.get_poll_by_game_id('game-rsvp')
        return poll['id']

    @pytest.mark.asyncio
    async def test_add_rsvp(self, db, poll_id):
        await db.add_or_update_rsvp(poll_id, 1, 'Alice', 'yes')
        rsvps = await db.get_rsvps_for_poll(poll_id)
        assert len(rsvps) == 1
        assert rsvps[0]['response'] == 'yes'

    @pytest.mark.asyncio
    async def test_update_rsvp(self, db, poll_id):
        await db.add_or_update_rsvp(poll_id, 1, 'Alice', 'yes')
        await db.add_or_update_rsvp(poll_id, 1, 'Alice', 'no')
        rsvps = await db.get_rsvps_for_poll(poll_id)
        assert len(rsvps) == 1
        assert rsvps[0]['response'] == 'no'

    @pytest.mark.asyncio
    async def test_remove_rsvp(self, db, poll_id):
        await db.add_or_update_rsvp(poll_id, 1, 'Alice', 'yes')
        await db.remove_rsvp(poll_id, 1)
        rsvps = await db.get_rsvps_for_poll(poll_id)
        assert rsvps == []

    @pytest.mark.asyncio
    async def test_multiple_users(self, db, poll_id):
        await db.add_or_update_rsvp(poll_id, 1, 'Alice', 'yes')
        await db.add_or_update_rsvp(poll_id, 2, 'Bob', 'no')
        await db.add_or_update_rsvp(poll_id, 3, 'Carol', 'if_needed')
        rsvps = await db.get_rsvps_for_poll(poll_id)
        assert len(rsvps) == 3


class TestPollStats:
    @pytest.mark.asyncio
    async def test_stats_count_correctly(self, db):
        await db.create_poll('game-stats', 444444, future())
        poll = await db.get_poll_by_game_id('game-stats')
        pid = poll['id']
        await db.add_or_update_rsvp(pid, 1, 'Alice', 'yes')
        await db.add_or_update_rsvp(pid, 2, 'Bob', 'yes')
        await db.add_or_update_rsvp(pid, 3, 'Carol', 'no')
        await db.add_or_update_rsvp(pid, 4, 'Dave', 'if_needed')
        stats = await db.get_poll_stats(pid)
        assert stats == {'yes': 2, 'no': 1, 'if_needed': 1}

    @pytest.mark.asyncio
    async def test_stats_empty_poll(self, db):
        await db.create_poll('game-empty', 555555, future())
        poll = await db.get_poll_by_game_id('game-empty')
        stats = await db.get_poll_stats(poll['id'])
        assert stats == {'yes': 0, 'no': 0, 'if_needed': 0}


class TestReminders:
    @pytest.mark.asyncio
    async def test_polls_needing_reminder(self, db):
        game_time = datetime.now(TIMEZONE) + timedelta(hours=12)
        await db.create_poll('game-remind', 666666, game_time)
        threshold = datetime.now(TIMEZONE) + timedelta(hours=24)
        polls = await db.get_polls_needing_reminder(threshold)
        assert any(p['game_id'] == 'game-remind' for p in polls)

    @pytest.mark.asyncio
    async def test_polls_not_needing_reminder_if_already_sent(self, db):
        game_time = datetime.now(TIMEZONE) + timedelta(hours=12)
        await db.create_poll('game-reminded', 777777, game_time)
        poll = await db.get_poll_by_game_id('game-reminded')
        await db.mark_reminder_sent(poll['id'])
        threshold = datetime.now(TIMEZONE) + timedelta(hours=24)
        polls = await db.get_polls_needing_reminder(threshold)
        assert not any(p['game_id'] == 'game-reminded' for p in polls)

    @pytest.mark.asyncio
    async def test_future_game_not_in_reminder_window(self, db):
        game_time = datetime.now(TIMEZONE) + timedelta(hours=48)
        await db.create_poll('game-future', 888888, game_time)
        threshold = datetime.now(TIMEZONE) + timedelta(hours=24)
        polls = await db.get_polls_needing_reminder(threshold)
        assert not any(p['game_id'] == 'game-future' for p in polls)


class TestActivePolls:
    @pytest.mark.asyncio
    async def test_active_polls_excludes_past_games(self, db):
        await db.create_poll('game-past', 100001, past())
        await db.create_poll('game-future', 100002, future())
        polls = await db.get_active_polls()
        ids = {p['game_id'] for p in polls}
        assert 'game-future' in ids
        assert 'game-past' not in ids

    @pytest.mark.asyncio
    async def test_get_next_upcoming_poll(self, db):
        await db.create_poll('game-near', 100003, future(hours=10))
        await db.create_poll('game-far', 100004, future(hours=100))
        poll = await db.get_next_upcoming_poll()
        assert poll['game_id'] == 'game-near'

    @pytest.mark.asyncio
    async def test_get_next_upcoming_poll_none_when_empty(self, db):
        assert await db.get_next_upcoming_poll() is None


class TestUpdateGameTime:
    @pytest.mark.asyncio
    async def test_update_game_time(self, db):
        original_time = future(hours=24)
        await db.create_poll('game-update', 200001, original_time)
        poll = await db.get_poll_by_game_id('game-update')
        new_time = future(hours=26)
        await db.update_poll_game_time(poll['id'], new_time)
        updated = await db.get_poll_by_game_id('game-update')
        assert updated['game_time'] == new_time.isoformat()
