"""
Discord bot that posts once per week about the next UFC event.

Features
- Scrapes UFCStats to find the next upcoming UFC event and its fight card
- Posts a compact summary: event name, date/time, location, and bouts (fighter vs. fighter + weight class)
- Runs on a weekly schedule (default: Fridays at 12:00 Europe/Copenhagen)

Env vars required
- DISCORD_TOKEN: your bot token
- DISCORD_CHANNEL_ID: channel ID to post into (integer)

Install
  pip install -r requirements.txt
Run
  python bot.py

Notes
- Parsing relies on UFCStats markup and may break if the site changes.
- Be respectful of the site; this script fetches only two pages per run.
"""

import os
import asyncio
import logging
from datetime import datetime

import pytz
import aiohttp
from bs4 import BeautifulSoup
import discord
from discord.ext import tasks

# --------------------- Config ---------------------
TZ = pytz.timezone("Europe/Copenhagen")
POST_WEEKDAY = 4  # 0=Mon ... 4=Fri, 5=Sat, 6=Sun
POST_HOUR = 12
POST_MINUTE = 0

UFCSTATS_UPCOMING = "https://ufcstats.com/statistics/events/upcoming"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("ufc-weekly-bot")

# --------------------- Scraper ---------------------
async def fetch(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=20)) as r:
        r.raise_for_status()
        return await r.text()

async def get_next_event(session: aiohttp.ClientSession):
    """Return dict with {title, date, location, url} for the next event."""
    html = await fetch(session, UFCSTATS_UPCOMING)
    soup = BeautifulSoup(html, "lxml")

    # The upcoming events table lists rows with event link + date + location.
    # We pick the first row.
    table = soup.select_one("table.b-statistics__table-events")
    if not table:
        raise RuntimeError("Could not locate upcoming events table on UFCStats.")

    first_row = table.select_one("tbody tr")
    if not first_row:
        raise RuntimeError("No upcoming event rows found.")

    a = first_row.select_one("a")
    date_cell = first_row.select_one("td:nth-of-type(2)")
    loc_cell = first_row.select_one("td:nth-of-type(3)")

    title = a.get_text(strip=True) if a else "UFC Event"
    url = a["href"] if a and a.has_attr("href") else None
    date_text = date_cell.get_text(strip=True) if date_cell else ""
    location = loc_cell.get_text(strip=True) if loc_cell else ""

    return {
        "title": title,
        "date_text": date_text,
        "location": location,
        "url": url,
    }

async def get_fight_card(session: aiohttp.ClientSession, event_url: str):
    """Parse event page and return list of fights: [{weight, red, blue}] in card order.
    UFCStats lists cards top-to-bottom; we keep that order.
    """
    if not event_url:
        return []
    html = await fetch(session, event_url)
    soup = BeautifulSoup(html, "lxml")

    fights = []
    # Each fight is in a tr with class b-fight-details__table-row
    for row in soup.select("tr.b-fight-details__table-row.b-fight-details__table-row__hover.js-fight-details-click"):
        # Weight class is in the first td with class b-fight-details__table-col"
        weight_td = row.select_one("td.b-fight-details__table-col:nth-of-type(1)")
        weight = weight_td.get_text(strip=True) if weight_td else ""

        # Fighters are nested inside two "b-fight-details__person" blocks or links in the 2nd/3rd columns.
        names = [a.get_text(strip=True) for a in row.select("a.b-link.b-link_style_black")]
        # Deduplicate while preserving order (each fight lists each fighter multiple times in the row)
        seen = set()
        fighters = []
        for n in names:
            if n and n not in seen:
                fighters.append(n)
                seen.add(n)
        if len(fighters) >= 2:
            red, blue = fighters[0], fighters[1]
            fights.append({"weight": weight, "red": red, "blue": blue})

    # Fallback in case the selector set above misses (markup changes):
    if not fights:
        for bout in soup.select("div.b-fight-details__fight"):
            weight = bout.select_one("i.b-fight-details__fight-title")
            weight = weight.get_text(strip=True) if weight else ""
            persons = [p.get_text(strip=True) for p in bout.select("div.b-fight-details__person a")]
            if len(persons) >= 2:
                fights.append({"weight": weight, "red": persons[0], "blue": persons[1]})

    return fights

# --------------------- Formatting ---------------------

def format_message(event: dict, fights: list) -> str:
    title = event.get("title", "Upcoming UFC Event")
    date_text = event.get("date_text", "TBA")
    location = event.get("location", "TBA")
    url = event.get("url") or UFCSTATS_UPCOMING

    header = f"**{title}**\n📅 {date_text}  •  📍 {location}\n🔗 More: {url}\n\n**Fight Card**"

    # Keep it concise: show up to 8 fights.
    lines = []
    for fight in fights[:8]:
        w = fight.get("weight", "")
        if w:
            lines.append(f"• {fight['red']} vs {fight['blue']}  —  *{w}*")
        else:
            lines.append(f"• {fight['red']} vs {fight['blue']}")

    if len(fights) > 8:
        lines.append(f"…and {len(fights) - 8} more bouts")

    return header + "\n" + "\n".join(lines)

# --------------------- Discord Bot ---------------------

intents = discord.Intents.default()
client = discord.Client(intents=intents)

async def post_update():
    if CHANNEL_ID == 0:
        logger.error("DISCORD_CHANNEL_ID not configured.")
        return

    async with aiohttp.ClientSession() as session:
        try:
            event = await get_next_event(session)
            fights = await get_fight_card(session, event.get("url"))
            msg = format_message(event, fights)
        except Exception as e:
            logger.exception("Failed to build UFC update: %s", e)
            msg = (
                "Couldn't fetch the next UFC event right now. "
                "(The source might have changed.)"
            )

    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        logger.error("Channel %s not found (check bot permissions and ID).", CHANNEL_ID)
        return
    await channel.send(msg)

@tasks.loop(minutes=1)
async def scheduler_loop():
    now = datetime.now(TZ)
    if (
        now.weekday() == POST_WEEKDAY and
        now.hour == POST_HOUR and
        now.minute == POST_MINUTE
    ):
        logger.info("Scheduled time reached — posting UFC update…")
        await post_update()

@client.event
async def on_ready():
    logger.info("Logged in as %s (id=%s)", client.user, client.user.id)
    if not scheduler_loop.is_running():
        scheduler_loop.start()
        logger.info(
            "Scheduler started. Will post on weekday=%d at %02d:%02d %s",
            POST_WEEKDAY, POST_HOUR, POST_MINUTE, TZ.zone,
        )

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("Set DISCORD_TOKEN env var with your bot token.")
    if CHANNEL_ID == 0:
        logger.warning("DISCORD_CHANNEL_ID is not set — the bot will log but not post.")
    client.run(DISCORD_TOKEN)
