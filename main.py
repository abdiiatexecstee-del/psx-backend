import threading
import os
import uvicorn
from fastapi import FastAPI
import discord
from discord.ext import commands, tasks
import asyncio
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import MACD
import traceback

# 1. FastAPI App Initialize
app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Server is live!"}

# 2. Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

# Configuration Variables
WATCHLIST = ["786", "AABS", "AATM", "ABOT", "ACPL", "AGHA", "AGTL", "AHCL", "AICL", "AIRLINK"] 

# ================= COMMANDS =================
@bot.command(name="hello")
async def hello(ctx):
    await ctx.send("Hello! I am running on Railway.")

@bot.command(name="add")
async def add_symbol(ctx, symbol: str):
    symbol = symbol.upper()
    if symbol not in WATCHLIST:
        WATCHLIST.append(symbol)
        await ctx.send(f"✅ Appended **{symbol}** to active tracking.")
    else: await ctx.send(f"ℹ️ **{symbol}** already monitored.")

@bot.command(name="remove")
async def remove_symbol(ctx, symbol: str):
    symbol = symbol.upper()
    if symbol in WATCHLIST:
        WATCHLIST.remove(symbol)
        await ctx.send(f"❌ Extracted **{symbol}** from processing.")
    else: await ctx.send(f"⚠️ **{symbol}** not found.")

@bot.command(name="watchlist")
async def show_watchlist(ctx):
    watchlist_str = ", ".join(WATCHLIST)
    await ctx.send(f"📋 **Active Assets ({len(WATCHLIST)}):**\n```{watchlist_str}```")

# 3. Bot Run Function
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Error: DISCORD_TOKEN not found!")

# 4. Main Execution
if __name__ == "__main__":
    # Bot thread start
    threading.Thread(target=run_bot, daemon=True).start()
    
    # API Server start
    uvicorn.run(app, host="0.0.0.0", port=8000)
