import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
import aiohttp
import pytz
import icalendar
import discord
from discord.ext import commands
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── Config ────────────────────────────────────────────────────────────────────
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])

# Saturday noon Copenhagen by default (most UFC cards are Sat)
POST_WEEKDAY = int(os.getenv("POST_WEEKDAY", "5"))  # 0=Mon … 6=Sun
POST_HOUR = int(os.getenv("POST_HOUR", "12"))
POST_MINUTE = int(os.getenv("POST_MINUTE", "0"))
TZ = pytz.timezone(os.getenv("TZ", "Europe/Copenhagen"))

UFC_ICS_URL = "https://raw.githubusercontent.com/clarencechaan/ufc-cal/ics/UFC.ics"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("ufc-bot")

# ── Discord ───────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ── Keep Alive ────────────────────────────────────────────────────────────────
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

def run_keepalive_server():
    server = HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 8080))), KeepAliveHandler)
    server.serve_forever()

threading.Thread(target=run_keepalive_server, daemon=True).start()

# ── Fetch and parse ICS ───────────────────────────────────────────────────────
async def fetch_ics_events():
    async with aiohttp.ClientSession() as session:
        resp = await session.get(UFC_ICS_URL)
        resp.raise_for_status()
        data = await resp.read()

    cal = icalendar.Calendar.from_ical(data)
    events = []
    now = datetime.now(timezone.utc)

    for comp in cal.walk("VEVENT"):
        dt = comp.get("DTSTART").dt
        if isinstance(dt, datetime) and dt > now:
            events.append({
                "summary": str(comp.get("SUMMARY")),
                "start": dt,
                "description": str(comp.get("DESCRIPTION") or ""),
                "location": str(comp.get("LOCATION") or ""),
                "url": str(comp.get("UID") or ""),
            })

    events.sort(key=lambda e: e["start"])
    return events

def format_event(event):
    start_local = event["start"].astimezone(TZ)
    header = (
        f"**{event['summary']}**\n"
        f"📅 {start_local.strftime('%Y-%m-%d %H:%M %Z')}\n"
    )
    desc_lines = [line.strip() for line in event["description"].splitlines() if line.strip()]
    body = "\n".join(desc_lines)
    footer = ""
    if event.get("location"):
        footer += f"\n📍 {event['location']}"
    if event.get("url"):
        footer += f"\n🔗 {event['url']}"
    return header + body + footer

async def get_next_event():
    events = await fetch_ics_events()
    return events[0] if events else None

async def post_next_event(channel: discord.TextChannel):
    evt = await get_next_event()
    if not evt:
        await channel.send("Couldn’t find an upcoming UFC event right now.")
        return
    await channel.send(format_event(evt))

# ── Scheduler ─────────────────────────────────────────────────────────────────
def next_run_time(now: datetime) -> datetime:
    local_now = now.astimezone(TZ)
    target = local_now.replace(hour=POST_HOUR, minute=POST_MINUTE, second=0, microsecond=0)
    days_ahead = (POST_WEEKDAY - target.weekday()) % 7
    if days_ahead == 0 and target <= local_now:
        days_ahead = 7
    return target + timedelta(days=days_ahead)

async def scheduler():
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        log.error("Channel ID %s not found or not a text channel.", CHANNEL_ID)
        return
    while not bot.is_closed():
        now = datetime.now(TZ)
        run_at = next_run_time(now)
        wait_s = max(1.0, (run_at - now).total_seconds())
        log.info("Next scheduled post at %s (%.0fs)", run_at.isoformat(), wait_s)
        try:
            await asyncio.sleep(wait_s)
        except asyncio.CancelledError:
            break
        try:
            await post_next_event(channel)
        except Exception as e:
            log.exception("Error posting scheduled UFC event: %s", e)
        await asyncio.sleep(5)

@bot.event
async def on_ready():
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)
    if not any(t.get_name() == "ufc-scheduler" for t in asyncio.all_tasks()):
        asyncio.create_task(scheduler(), name="ufc-scheduler")

# ── Manual trigger: !ufc ──────────────────────────────────────────────────────
@bot.command(name="ufc", help="Post the next UFC event now.")
async def ufc_cmd(ctx: commands.Context):
    if ctx.channel.id != CHANNEL_ID:
        await ctx.send("This command is disabled in this channel.")
        return
    try:
        async with ctx.typing():
            await post_next_event(ctx.channel)
    except Exception as e:
        log.exception("Command error: %s", e)
        await ctx.send("Sorry, couldn’t fetch the event right now.")

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
