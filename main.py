import os
import uvicorn
import asyncio
import discord
from discord.ext import commands
from fastapi import FastAPI
import threading

# Initialize FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "online"}

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- [PASTE ALL YOUR FUNCTIONS HERE: fetch_data, process_metrics, etc.] ---

# --- [PASTE ALL YOUR COMMANDS HERE: !psx, !map, !dashboard, etc.] ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# RUNNER
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot.run(token)

if __name__ == "__main__":
    # Start bot in a separate thread
    threading.Thread(target=run_bot, daemon=True).start()
    # Start FastAPI
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
