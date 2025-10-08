import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import asyncio
from datetime import datetime, timedelta
import pytz
from ical_parser import ICalParser
from database import Database

# Load environment variables
load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
ICAL_URLS = [url.strip() for url in os.getenv('ICAL_URLS', '').split(',')]
TEAM_NAMES = [name.strip() for name in os.getenv('TEAM_NAMES', '').split(',')]
TIMEZONE = pytz.timezone(os.getenv('TIMEZONE', 'America/Toronto'))

# Initialize components - create parser for each team
ical_parsers = []
for i, ical_url in enumerate(ICAL_URLS):
    team_name = TEAM_NAMES[i] if i < len(TEAM_NAMES) else f"Team {i+1}"
    ical_parsers.append({
        'name': team_name,
        'parser': ICalParser(ical_url, TIMEZONE)
    })
db = None

# Emoji mappings for reactions
REACTIONS = {
    'yes': '✅',
    'no': '❌',
    'if_needed': '🤷'
}

@bot.event
async def on_ready():
    global db
    db = Database('data/hockey_rsvp.db')
    await db.initialize()
    print(f'{bot.user} has connected to Discord!')
    check_upcoming_games.start()
    check_reminders.start()
    check_game_time_changes.start()

@tasks.loop(hours=24)
async def check_upcoming_games():
    """Check daily for games that are 7 days away and create polls"""
    await bot.wait_until_ready()

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Could not find channel with ID {CHANNEL_ID}")
        return

    # Get games happening in 7 days for all teams
    target_date = datetime.now(TIMEZONE) + timedelta(days=7)

    for team in ical_parsers:
        games = await team['parser'].get_games_on_date(target_date)

        for game in games:
            # Check if poll already exists for this game
            existing_poll = await db.get_poll_by_game_id(game['id'])
            if existing_poll:
                continue

            # Add team name to game data
            game['team_name'] = team['name']

            # Create poll message
            poll_message = await create_game_poll(channel, game)

            # Save poll to database
            await db.create_poll(game['id'], poll_message.id, game['start_time'])

async def create_game_poll(channel, game):
    """Create a poll message for a game"""
    # Format game details
    start_time = game['start_time'].strftime('%A, %B %d at %I:%M %p')
    opponent = game.get('opponent', 'TBD')
    location = game.get('location', 'Home')
    team_name = game.get('team_name', 'Team')

    embed = discord.Embed(
        title=f"🏒 {team_name} - Game RSVP",
        description=f"**{start_time}**\n\nOpponent: {opponent}\nLocation: {location}",
        color=discord.Color.blue(),
        timestamp=game['start_time']
    )

    embed.add_field(name="✅ Yes", value="0 players", inline=True)
    embed.add_field(name="❌ No", value="0 players", inline=True)
    embed.add_field(name="🤷 If needed", value="0 players", inline=True)

    embed.set_footer(text="React with ✅, ❌, or 🤷 to RSVP")

    message = await channel.send(embed=embed)

    # Add reaction options
    for reaction in REACTIONS.values():
        await message.add_reaction(reaction)

    return message

@bot.event
async def on_raw_reaction_add(payload):
    """Handle when a user adds a reaction to a poll"""
    # Ignore bot's own reactions
    if payload.user_id == bot.user.id:
        return

    # Check if this is a poll message
    poll = await db.get_poll_by_message_id(payload.message_id)
    if not poll:
        return

    # Map emoji to response type
    response_type = None
    for rtype, emoji in REACTIONS.items():
        if str(payload.emoji) == emoji:
            response_type = rtype
            break

    if not response_type:
        return

    # Remove user's other responses for this poll
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    for rtype, emoji in REACTIONS.items():
        if rtype != response_type:
            try:
                await message.remove_reaction(emoji, payload.member)
            except discord.errors.Forbidden:
                # Bot lacks permission to remove reactions, skip it
                pass

    # Update database
    await db.add_or_update_rsvp(poll['id'], payload.user_id, str(payload.member), response_type)

    # Update poll message
    await update_poll_message(message, poll['id'])

@bot.event
async def on_raw_reaction_remove(payload):
    """Handle when a user removes a reaction from a poll"""
    # Check if this is a poll message
    poll = await db.get_poll_by_message_id(payload.message_id)
    if not poll:
        return

    # Remove from database
    await db.remove_rsvp(poll['id'], payload.user_id)

    # Update poll message
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    await update_poll_message(message, poll['id'])

async def update_poll_message(message, poll_id):
    """Update the poll embed with current RSVP counts"""
    rsvps = await db.get_rsvps_for_poll(poll_id)

    # Count responses - use mentions instead of usernames
    counts = {'yes': [], 'no': [], 'if_needed': []}
    for rsvp in rsvps:
        user_mention = f"<@{rsvp['user_id']}>"
        counts[rsvp['response']].append(user_mention)

    # Get original embed
    embed = message.embeds[0]

    # Update fields
    embed.clear_fields()

    yes_users = '\n'.join(counts['yes']) if counts['yes'] else 'None'
    no_users = '\n'.join(counts['no']) if counts['no'] else 'None'
    if_needed_users = '\n'.join(counts['if_needed']) if counts['if_needed'] else 'None'

    embed.add_field(
        name=f"✅ Yes ({len(counts['yes'])})",
        value=yes_users if len(yes_users) <= 1024 else f"{len(counts['yes'])} players",
        inline=True
    )
    embed.add_field(
        name=f"❌ No ({len(counts['no'])})",
        value=no_users if len(no_users) <= 1024 else f"{len(counts['no'])} players",
        inline=True
    )
    embed.add_field(
        name=f"🤷 If needed ({len(counts['if_needed'])})",
        value=if_needed_users if len(if_needed_users) <= 1024 else f"{len(counts['if_needed'])} players",
        inline=True
    )

    await message.edit(embed=embed)

@bot.command(name='testpoll')
async def test_poll(ctx, team_index: int = 0):
    """Manually create a test poll (admin only). Optional: specify team index (0, 1, etc.)"""
    if team_index >= len(ical_parsers):
        await ctx.send(f"Invalid team index. Available teams: 0-{len(ical_parsers)-1}")
        return

    team = ical_parsers[team_index]

    # Get next game
    upcoming_games = await team['parser'].get_upcoming_games(days=30)
    if not upcoming_games:
        await ctx.send(f"No upcoming games found for {team['name']} in the next 30 days.")
        return

    game = upcoming_games[0]
    game['team_name'] = team['name']
    poll_message = await create_game_poll(ctx.channel, game)
    await db.create_poll(game['id'], poll_message.id, game['start_time'])
    await ctx.send(f"Test poll created for {team['name']} game on {game['start_time'].strftime('%B %d')}")

@bot.command(name='checkgames')
async def check_games(ctx):
    """Manually trigger the daily game check (admin only)"""
    await ctx.send("Checking for games 7 days from now...")
    await check_upcoming_games()
    await ctx.send("Check complete!")

@bot.command(name='createpoll')
async def create_poll_for_date(ctx, days_ahead: int = 0):
    """Create polls for games X days from now. Usage: !createpoll 0 (today), !createpoll 3 (Wednesday)"""
    channel = ctx.channel
    target_date = datetime.now(TIMEZONE) + timedelta(days=days_ahead)

    polls_created = 0

    for team in ical_parsers:
        games = await team['parser'].get_games_on_date(target_date)

        for game in games:
            # Check if poll already exists for this game
            existing_poll = await db.get_poll_by_game_id(game['id'])
            if existing_poll:
                await ctx.send(f"Poll already exists for {team['name']} game on {game['start_time'].strftime('%B %d at %I:%M %p')}")
                continue

            # Add team name to game data
            game['team_name'] = team['name']

            # Create poll message
            poll_message = await create_game_poll(channel, game)

            # Save poll to database
            await db.create_poll(game['id'], poll_message.id, game['start_time'])
            polls_created += 1
            await ctx.send(f"✅ Created poll for {team['name']} game on {game['start_time'].strftime('%B %d at %I:%M %p')}")

    if polls_created == 0:
        await ctx.send(f"No games found on {target_date.strftime('%A, %B %d, %Y')}")

@bot.command(name='testreminder')
async def test_reminder(ctx):
    """Manually send a reminder for the next upcoming game"""
    # Get the next upcoming poll
    poll = await db.get_next_upcoming_poll()

    if not poll:
        await ctx.send("No upcoming games found.")
        return

    try:
        # Fetch the poll message
        channel = bot.get_channel(CHANNEL_ID)
        message = await channel.fetch_message(poll['message_id'])

        # Get RSVP stats
        rsvps = await db.get_rsvps_for_poll(poll['id'])
        stats = await db.get_poll_stats(poll['id'])

        # Parse game time
        game_time = datetime.fromisoformat(poll['game_time'])
        time_until_game = game_time - datetime.now(TIMEZONE)
        hours_until = int(time_until_game.total_seconds() / 3600)

        # Create reminder message
        reminder_text = f"⏰ **TEST REMINDER**: Game in approximately {hours_until} hours!\n\n"
        reminder_text += f"Current RSVPs: ✅ {stats['yes']} | ❌ {stats['no']} | 🤷 {stats['if_needed']}\n\n"

        # Get list of users who haven't responded
        responded_users = {rsvp['user_id'] for rsvp in rsvps}

        if responded_users:
            reminder_text += "If you haven't responded yet, please react to the poll above!"
        else:
            reminder_text += "No responses yet! Please react to the poll above!"

        # Send reminder as a reply to the poll
        await message.reply(reminder_text)
        await ctx.send(f"Test reminder sent for game on {game_time.strftime('%B %d at %I:%M %p')}")

    except discord.errors.NotFound:
        await ctx.send(f"Poll message not found.")
    except Exception as e:
        await ctx.send(f"Error sending reminder: {e}")

@tasks.loop(hours=1)
async def check_reminders():
    """Check hourly for games that need 24-hour reminders"""
    await bot.wait_until_ready()

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Could not find channel with ID {CHANNEL_ID}")
        return

    # Get current time + 24 hours
    reminder_threshold = datetime.now(TIMEZONE) + timedelta(hours=24)

    # Get polls that need reminders
    polls = await db.get_polls_needing_reminder(reminder_threshold)

    for poll in polls:
        try:
            # Fetch the poll message
            message = await channel.fetch_message(poll['message_id'])

            # Get RSVP stats
            rsvps = await db.get_rsvps_for_poll(poll['id'])
            stats = await db.get_poll_stats(poll['id'])

            # Parse game time
            game_time = datetime.fromisoformat(poll['game_time'])
            time_until_game = game_time - datetime.now(TIMEZONE)
            hours_until = int(time_until_game.total_seconds() / 3600)

            # Create reminder message
            reminder_text = f"⏰ **REMINDER**: Game in approximately {hours_until} hours!\n\n"
            reminder_text += f"Current RSVPs: ✅ {stats['yes']} | ❌ {stats['no']} | 🤷 {stats['if_needed']}\n\n"

            # Get list of users who haven't responded
            responded_users = {rsvp['user_id'] for rsvp in rsvps}

            if responded_users:
                reminder_text += "If you haven't responded yet, please react to the poll above!"
            else:
                reminder_text += "No responses yet! Please react to the poll above!"

            # Send reminder as a reply to the poll
            await message.reply(reminder_text)

            # Mark reminder as sent
            await db.mark_reminder_sent(poll['id'])

            print(f"Sent reminder for poll {poll['id']}")

        except discord.errors.NotFound:
            print(f"Poll message {poll['message_id']} not found, marking as sent anyway")
            await db.mark_reminder_sent(poll['id'])
        except Exception as e:
            print(f"Error sending reminder for poll {poll['id']}: {e}")

@tasks.loop(hours=2)
async def check_game_time_changes():
    """Check every 2 hours for game time changes"""
    await bot.wait_until_ready()

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Could not find channel with ID {CHANNEL_ID}")
        return

    # Get all active polls (games that haven't happened yet)
    polls = await db.get_active_polls()

    for poll in polls:
        try:
            game_id = poll['game_id']
            stored_time = datetime.fromisoformat(poll['game_time'])

            # Find which team this game belongs to
            current_game = None
            team_name = None
            for team in ical_parsers:
                game = await team['parser'].get_game_by_id(game_id)
                if game:
                    current_game = game
                    team_name = team['name']
                    break

            if not current_game:
                print(f"Game {game_id} no longer found in calendar feed")
                continue

            # Check if time has changed
            new_time = current_game['start_time']
            if new_time != stored_time:
                # Time has changed!
                time_diff = new_time - stored_time
                hours_diff = abs(time_diff.total_seconds() / 3600)

                # Only notify if the change is significant (more than 15 minutes)
                if hours_diff >= 0.25:
                    print(f"Game time changed for {game_id}: {stored_time} -> {new_time}")

                    # Fetch the poll message
                    message = await channel.fetch_message(poll['message_id'])

                    # Update the embed with new time
                    embed = message.embeds[0]
                    embed.timestamp = new_time

                    # Update description to include time change notice
                    old_time_str = stored_time.strftime('%I:%M %p')
                    new_time_str = new_time.strftime('%I:%M %p')

                    if time_diff.total_seconds() > 0:
                        change_text = f"\n\n⚠️ **TIME CHANGE**: Game moved from {old_time_str} to {new_time_str} (later)"
                    else:
                        change_text = f"\n\n⚠️ **TIME CHANGE**: Game moved from {old_time_str} to {new_time_str} (earlier)"

                    # Update embed description
                    current_desc = embed.description or ""
                    # Remove any previous time change notices
                    if "⚠️ **TIME CHANGE**" in current_desc:
                        current_desc = current_desc.split("\n\n⚠️ **TIME CHANGE**")[0]
                    embed.description = current_desc + change_text

                    await message.edit(embed=embed)

                    # Get all users who have RSVPd
                    rsvps = await db.get_rsvps_for_poll(poll['id'])

                    if rsvps:
                        # Notify users about the time change
                        user_mentions = ' '.join([f"<@{rsvp['user_id']}>" for rsvp in rsvps])
                        notification = f"🔔 **Game time has changed!**\n\n"
                        notification += f"**{team_name}** game on {new_time.strftime('%B %d')}\n"
                        notification += f"**Old time**: {old_time_str}\n"
                        notification += f"**New time**: {new_time_str}\n\n"
                        notification += f"Please check if you can still make it: {user_mentions}"

                        await message.reply(notification)

                    # Update database with new time
                    await db.update_poll_game_time(poll['id'], new_time)

                    print(f"Updated poll {poll['id']} with new game time and notified {len(rsvps)} users")

        except discord.errors.NotFound:
            print(f"Poll message {poll['message_id']} not found")
        except Exception as e:
            print(f"Error checking game time for poll {poll['id']}: {e}")

if __name__ == '__main__':
    bot.run(DISCORD_TOKEN)
