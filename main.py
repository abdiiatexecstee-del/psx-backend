import threading
import os
import uvicorn
from fastapi import FastAPI
import discord
from discord.ext import commands

# 1. FastAPI App Initialize
app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Server is live!"}

# 2. Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Bot is logged in as {bot.user}')

@bot.command()
async def hello(ctx):
    await ctx.send("Hello! I am running on Railway.")

# 3. Bot Run Function
def run_bot():
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Error: DISCORD_TOKEN not found in environment variables.")

# 4. Main Execution
if __name__ == "__main__":
    # Threading start
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    
    # API Server start
    uvicorn.run(app, host="0.0.0.0", port=8000)
