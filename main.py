import os
import discord
from discord.ext import commands
from fastapi import FastAPI
import uvicorn
import threading
import asyncio

# --- 1. FastAPI Setup ---
app = FastAPI()
@app.get("/")
async def root(): return {"status": "online"}

# --- 2. Discord Bot Setup ---
intents = discord.Intents.all() 
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 3. APKA SAARA LOGIC (Yahan paste karein) ---
# Apni bot.py file ka saara content: 
# WATCHLIST, functions, aur saare @bot.command yahan paste karein.
# (Example)
@bot.command(name="watchlist")
async def show_watchlist(ctx):
    await ctx.send("📋 Active Assets are being tracked.")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# --- 4. Execution ---
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    bot.run(token)

if __name__ == "__main__":
    # Bot aur Server dono ko start karein
    threading.Thread(target=run_bot, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
