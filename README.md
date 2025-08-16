# UFC Weekly Discord Bot

A Discord bot that posts the **next upcoming UFC event** in a chosen channel.
It uses the public **UFC.ics** calendar maintained by [clarencechaan/ufc-cal](https://github.com/clarencechaan/ufc-cal).

---

## Features

* Pulls from a reliable **ICS calendar** (updated daily)
* Posts event name, local date/time, location, and the fight card (from the ICS description)
* **Weekly automatic posting** (configurable day/time & timezone)
* **Manual trigger** with `!ufc`
* Deployable on **Render Free** as a Web Service (includes a tiny keep-alive HTTP server)

---

## Requirements

* Python **3.9+**
* Discord bot + token
* Packages:

  ```bash
  pip install discord.py aiohttp pytz icalendar
  ```
* ICS source:

  * [UFC.ics (raw)](https://raw.githubusercontent.com/clarencechaan/ufc-cal/ics/UFC.ics)

---

## Configuration

Set these environment variables:

| Variable             | Default             | Description                               |
| -------------------- | ------------------- | ----------------------------------------- |
| `DISCORD_TOKEN`      | **required**        | Your Discord bot token                    |
| `DISCORD_CHANNEL_ID` | **required**        | Channel ID where the bot will post        |
| `POST_WEEKDAY`       | `5`                 | Day for scheduled post: `0=Mon … 6=Sun`   |
| `POST_HOUR`          | `12`                | Hour (0–23) for scheduled post            |
| `POST_MINUTE`        | `0`                 | Minute for scheduled post                 |
| `TZ`                 | `Europe/Copenhagen` | Time zone used when displaying event time |

> The code includes a minimal HTTP server for Render’s free Web Service health checks.

---

## Discord Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. **Bot** → **Add Bot** → confirm.
3. In the **Bot** tab, enable **MESSAGE CONTENT INTENT** (needed for `!ufc`).
4. Copy the **Token**.
5. **OAuth2 → URL Generator** → Scopes: `bot` → Permissions: `Send Messages`, `View Channels`.
6. Open the generated URL and invite the bot to your server.
7. In Discord, enable **Developer Mode** (Settings → Advanced).
8. Right-click your target channel → **Copy Channel ID**.

---

## Run Locally

```bash
export DISCORD_TOKEN="your_bot_token"
export DISCORD_CHANNEL_ID="123456789012345678"
# optional
export POST_WEEKDAY=5
export POST_HOUR=12
export POST_MINUTE=0
export TZ="Europe/Copenhagen"

python bot.py
```

* The bot connects and schedules a weekly post.
* Test any time with `!ufc` in the configured channel.

---

## Deploy on Render (Free Plan)

Render’s free tier applies to **Web Services**.
Run the bot as a Web Service and keep it alive with the included HTTP server.

1. Push your code to GitHub.
2. In Render: **New → Web Service**.
3. Connect your repo.
4. **Instance Type:** select **Free**.
5. **Build Command:**

   ```bash
   pip install -r requirements.txt
   ```
6. **Start Command:**

   ```bash
   python bot.py
   ```
7. Add environment variables:

   * `DISCORD_TOKEN`, `DISCORD_CHANNEL_ID`
   * (optional) `POST_WEEKDAY`, `POST_HOUR`, `POST_MINUTE`, `TZ`
8. Deploy. You should see logs like “Logged in as …” and scheduler output.

---

## Commands

| Command | Description                                 |
| ------- | ------------------------------------------- |
| `!ufc`  | Posts the next upcoming UFC event right now |

---

## Troubleshooting

* **`!ufc` does nothing**

  * Check the bot’s role permissions for the channel (`View Channel`, `Send Messages`).
  * Verify `DISCORD_CHANNEL_ID` matches the channel you’re testing in.
  * Ensure **MESSAGE CONTENT INTENT** is enabled in the Developer Portal.

* **Scheduled post not appearing**

  * Confirm `POST_WEEKDAY`, `POST_HOUR`, `POST_MINUTE`, and `TZ`.
  * Check Render logs for scheduler output and exceptions.

* **Render restarts / 404 health checks**

  * The bot includes a tiny HTTP server that responds `200 OK`.
    Make sure you deployed as a **Web Service** (not Worker) and selected **Free**.

* **No fight card text**

  * Sometimes the ICS description may be missing details early;
    the event summary/date/location will still post.

---

## Data Source

* Calendar feed: **UFC.ics** from [clarencechaan/ufc-cal](https://github.com/clarencechaan/ufc-cal)
  Raw ICS URL: [https://raw.githubusercontent.com/clarencechaan/ufc-cal/ics/UFC.ics](https://raw.githubusercontent.com/clarencechaan/ufc-cal/ics/UFC.ics)

> Credit to the `ufc-cal` maintainers for providing and updating the ICS feed.

---

## License

This bot is for personal use. All UFC data and trademarks belong to their respective owners.
