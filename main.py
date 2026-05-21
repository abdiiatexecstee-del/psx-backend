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
async def read_root():
    return {"status": "online", "message": "PSX Bot is running"}

# Bot Configuration
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- [YAHA SE APNA SARA LOGIC COPY KAREIN] ---
# Apne bot.py se saare functions: fetch_data(), process_metrics(), 
# generate_chart_buffer(), commands (@bot.command) yahan paste karein.
# --- [END LOGIC] ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# Main Execution Thread
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    token = os.getenv("DISCORD_TOKEN")
    bot.run(token)

if __name__ == "__main__":
    # Start Bot in background thread
    threading.Thread(target=run_bot, daemon=True).start()
    
    # Start FastAPI Server (Railway PORT)
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
import os
import uvicorn
import asyncio
import discord
from discord.ext import commands
from fastapi import FastAPI
import threading
import io
import mplfinance as mpf
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# Initialize FastAPI
app = FastAPI()

@app.get("/")
async def read_root():
    return {"status": "online"}

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- [YAHA SE APNA PURA LOGIC COPY KAREIN] ---
# Apne bot.py file mein jo 'psx', 'check', 'map', 'screener' 
# ke functions aur @bot.command hain, unhe yahan paste karein.
# --- [END LOGIC] ---

# RUNNER
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    bot.run(token)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
