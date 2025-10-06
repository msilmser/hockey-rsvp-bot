import aiosqlite
from datetime import datetime

class Database:
    def __init__(self, db_path):
        self.db_path = db_path

    async def initialize(self):
        """Create the database tables if they don't exist"""
        async with aiosqlite.connect(self.db_path) as db:
            # Polls table - tracks each poll message
            await db.execute('''
                CREATE TABLE IF NOT EXISTS polls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT UNIQUE NOT NULL,
                    message_id INTEGER UNIQUE NOT NULL,
                    game_time TIMESTAMP NOT NULL,
                    reminder_sent INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Add reminder_sent column if it doesn't exist (for existing databases)
            try:
                await db.execute('ALTER TABLE polls ADD COLUMN reminder_sent INTEGER DEFAULT 0')
                await db.commit()
            except Exception:
                # Column already exists, ignore
                pass

            # RSVPs table - tracks user responses
            await db.execute('''
                CREATE TABLE IF NOT EXISTS rsvps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    poll_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    response TEXT NOT NULL CHECK(response IN ('yes', 'no', 'maybe')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE,
                    UNIQUE(poll_id, user_id)
                )
            ''')

            # Create indexes for faster lookups
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_polls_game_id ON polls(game_id)
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_polls_message_id ON polls(message_id)
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_rsvps_poll_id ON rsvps(poll_id)
            ''')

            await db.commit()

    async def create_poll(self, game_id, message_id, game_time):
        """Create a new poll record"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'INSERT INTO polls (game_id, message_id, game_time) VALUES (?, ?, ?)',
                (game_id, message_id, game_time.isoformat())
            )
            await db.commit()

    async def get_poll_by_game_id(self, game_id):
        """Get a poll by its game ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM polls WHERE game_id = ?',
                (game_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_poll_by_message_id(self, message_id):
        """Get a poll by its Discord message ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM polls WHERE message_id = ?',
                (message_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def add_or_update_rsvp(self, poll_id, user_id, username, response):
        """Add or update a user's RSVP for a poll"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO rsvps (poll_id, user_id, username, response, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(poll_id, user_id) DO UPDATE SET
                    response = excluded.response,
                    username = excluded.username,
                    updated_at = CURRENT_TIMESTAMP
            ''', (poll_id, user_id, username, response))
            await db.commit()

    async def remove_rsvp(self, poll_id, user_id):
        """Remove a user's RSVP from a poll"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'DELETE FROM rsvps WHERE poll_id = ? AND user_id = ?',
                (poll_id, user_id)
            )
            await db.commit()

    async def get_rsvps_for_poll(self, poll_id):
        """Get all RSVPs for a specific poll"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM rsvps WHERE poll_id = ? ORDER BY response, username',
                (poll_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_poll_stats(self, poll_id):
        """Get RSVP statistics for a poll"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT
                    response,
                    COUNT(*) as count
                FROM rsvps
                WHERE poll_id = ?
                GROUP BY response
            ''', (poll_id,)) as cursor:
                rows = await cursor.fetchall()
                stats = {'yes': 0, 'no': 0, 'maybe': 0}
                for row in rows:
                    stats[row['response']] = row['count']
                return stats

    async def get_polls_needing_reminder(self, reminder_time):
        """Get polls that need a reminder sent (game time is close and reminder not sent yet)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT * FROM polls
                WHERE reminder_sent = 0
                AND game_time <= ?
            ''', (reminder_time.isoformat(),)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def mark_reminder_sent(self, poll_id):
        """Mark that a reminder has been sent for this poll"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE polls SET reminder_sent = 1 WHERE id = ?',
                (poll_id,)
            )
            await db.commit()

    async def get_next_upcoming_poll(self):
        """Get the next upcoming game poll"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT * FROM polls
                WHERE game_time > ?
                ORDER BY game_time ASC
                LIMIT 1
            ''', (datetime.now().isoformat(),)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
