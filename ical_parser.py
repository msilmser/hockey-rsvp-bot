import requests
from icalendar import Calendar
from datetime import datetime, timedelta
import pytz
from recurring_ical_events import of

class ICalParser:
    def __init__(self, ical_url, timezone):
        self.ical_url = ical_url.replace('webcal://', 'https://')
        self.timezone = timezone

    def fetch_calendar(self):
        """Fetch the iCal feed from the URL"""
        try:
            response = requests.get(self.ical_url, timeout=10)
            response.raise_for_status()
            return Calendar.from_ical(response.content)
        except Exception as e:
            print(f"Error fetching calendar: {e}")
            return None

    async def get_games_on_date(self, target_date):
        """Get all games on a specific date (comparing just the date, not time)"""
        calendar = self.fetch_calendar()
        if not calendar:
            return []

        games = []
        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        # Get events for the target date
        events = of(calendar).between(start_of_day, end_of_day)

        for event in events:
            game = self._parse_event(event)
            if game:
                games.append(game)

        return games

    async def get_upcoming_games(self, days=30):
        """Get all games in the next X days"""
        calendar = self.fetch_calendar()
        if not calendar:
            return []

        games = []
        start = datetime.now(self.timezone)
        end = start + timedelta(days=days)

        # Get events in the date range
        events = of(calendar).between(start, end)

        for event in events:
            game = self._parse_event(event)
            if game:
                games.append(game)

        # Sort by start time
        games.sort(key=lambda x: x['start_time'])
        return games

    async def get_game_by_id(self, game_id):
        """Get a specific game by its UID"""
        calendar = self.fetch_calendar()
        if not calendar:
            return None

        # Search for the event with matching UID
        for component in calendar.walk():
            if component.name == "VEVENT":
                uid = str(component.get('UID', ''))
                if uid == game_id:
                    return self._parse_event(component)

        return None

    def _parse_event(self, event):
        """Parse a calendar event into a game dictionary"""
        try:
            # Get start time
            dtstart = event.get('DTSTART').dt
            if isinstance(dtstart, datetime):
                if dtstart.tzinfo is None:
                    dtstart = self.timezone.localize(dtstart)
                else:
                    dtstart = dtstart.astimezone(self.timezone)
            else:
                # If it's a date object, convert to datetime
                dtstart = self.timezone.localize(
                    datetime.combine(dtstart, datetime.min.time())
                )

            # Get event details
            summary = str(event.get('SUMMARY', ''))
            location = str(event.get('LOCATION', 'TBD'))
            description = str(event.get('DESCRIPTION', ''))
            uid = str(event.get('UID', ''))

            # Try to extract opponent from summary
            opponent = self._extract_opponent(summary)

            return {
                'id': uid,
                'start_time': dtstart,
                'summary': summary,
                'opponent': opponent,
                'location': location,
                'description': description
            }
        except Exception as e:
            print(f"Error parsing event: {e}")
            return None

    def _extract_opponent(self, summary):
        """Extract opponent team name from the game summary"""
        # Common patterns: "vs Team Name", "@ Team Name", "Team Name vs Team Name"
        if ' vs ' in summary.lower():
            parts = summary.lower().split(' vs ')
            return parts[1].strip() if len(parts) > 1 else summary
        elif ' @ ' in summary:
            parts = summary.split(' @ ')
            return parts[1].strip() if len(parts) > 1 else summary
        else:
            return summary
