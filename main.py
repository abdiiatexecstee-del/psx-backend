import threading
import uvicorn
from fastapi import FastAPI
import discord
from discord.ext import commands, tasks
from ta.momentum import RSIIndicator
from ta.trend import MACD
import asyncio
import psxdata
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import urllib.request
import xml.etree.ElementTree as ET
import html
import traceback
import io

# Force matplotlib to run headlessly without needing a GUI display driver
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mplfinance as mpf

# ================= CONFIGURATION =================
DISCORD_TOKEN = "MTUwNTQ4NDA5MTUwMjM2Mjc0NQ.GR1o1t.6vGI3xX-4c51eiC--QuraGWnu1A7gH7GQAqvmA"
SCANNER_CHANNEL_ID = 1505485687879761972

BRAND_DOMAIN = "signalsbyQadri.sheedigoth.com"
BRAND_EMOJI = "🔥"

WATCHLIST = [
    "786", "AABS", "AATM", "ABOT", "ACPL", "ADAMS", "AGHA", "AGTL", "AHCL", "AICL", 
    "AIRLINK", "AKBL", "AKDSL", "APL", "ATLH", "ATRL", "BAFL", "BAHL", "BIPLS", "BML", 
    "BOP", "BWCL", "CHCC", "CNERGY", "COLG", "DCR", "DFML", "DGKC", "DLL", "EFERT", 
    "EFUG", "ENGRO", "ENGROH", "EPCL", "FABL", "FATIMA", "FCCL", "FCEPL", "FFC", "FFL", 
    "FLYNG", "GAL", "GHGL", "GHNI", "GLAXO", "GLPL", "GWLC", "HASCOL", "HBL", "HCAR", 
    "HINOON", "HMB", "HPL", "HUBC", "IBFL", "IGIHL", "ILP", "INDU", "INIL", "ISIL", 
    "ISL", "JDWS", "JSBL", "JVDC", "KAPCO", "KEL", "KOHC", "KPUS", "KTML", "LCI", 
    "LOTCHEM", "LUCK", "MARI", "MCB", "MEBL", "MLCF", "MTL", "MUGHAL", "MUREB", "NATF", 
    "NBP", "NCPL", "NESTLE", "NML", "NPL", "OGDC", "PAEL", "PAKT", "PIAHCLA", "PIAHCLB", 
    "PIBTL", "PIOC", "PKGS", "PNSC", "POL", "POWER", "PPL", "PRL", "PSO", "PSX", 
    "PTC", "RMPL", "SAZEW", "SCBPL", "SEARL", "SFL", "SGF", "SHFA", "SITC", "SNBL", 
    "SNGP", "SRVI", "SSGC", "SYS", "THALL", "THCCL", "TGL", "TRG", "TSML", "UBL", 
    "UPFL", "WAFI", "WTL", "AAL", "AASM", "ABL", "ADMM", "AGP", "AGL", "BOK", "BIPL", 
    "CPHL", "FML", "HALEON", "NRL", "PAKOXY", "SAPT"
]

# State Variables
dashboard_message = None
is_scanning_active = True
last_signals = {}
is_first_scan = True
last_known_market_state = None

# In-Memory Cache Parameters (Extended range to 260 days for safe SMA 200 processing)
STOCK_CACHE = {}
CACHE_EXPIRY_MINUTES = 3

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Baseline structural dividend matrix dictionary
DIVIDEND_DATABASE = {
    "FFC": {"yield": "14.2%", "payout": "88%", "sector": "Fertilizer"},
    "EFERT": {"yield": "12.8%", "payout": "85%", "sector": "Fertilizer"},
    "HUBC": {"yield": "11.5%", "payout": "90%", "sector": "Power Generation"},
    "ENGRO": {"yield": "10.4%", "payout": "78%", "sector": "Conglomerate"},
    "MCB": {"yield": "9.8%", "payout": "82%", "sector": "Commercial Banking"}
}

# ================= MARKET TIME LOGIC ENGINE =================
def get_market_status():
    utc_now = datetime.now(timezone.utc)
    pkt_now = utc_now + timedelta(hours=5)
    day = pkt_now.weekday()
    current_time_str = pkt_now.strftime("%H:%M")
    
    if day >= 5:
        return "CLOSED", "🔴 MARKET CLOSED (WEEKEND)"
        
    if day == 4: # Friday Timetable Configuration
        if "09:00" <= current_time_str < "09:15": return "PRE-OPEN", "🟡 MARKET PRE-OPEN"
        elif "09:15" <= current_time_str < "09:17": return "MATCHING", "⚙️ ORDER MATCHING SESSION"
        elif "09:17" <= current_time_str < "12:30": return "OPEN", "🟢 MARKET LIVE (OPEN)"
        elif "12:30" <= current_time_str < "12:50": return "POST-CLOSE", "⚪ POST-CLOSE SESSION"
        elif "12:50" <= current_time_str < "13:20": return "MODIFICATION", "🛠️ TRADE MODIFICATION"
        else: return "CLOSED", "🔴 MARKET CLOSED"
    else: # Monday - Thursday Timetable Configuration
        if "09:00" <= current_time_str < "09:15": return "PRE-OPEN", "🟡 MARKET PRE-OPEN"
        elif "09:15" <= current_time_str < "09:17": return "MATCHING", "⚙️ ORDER MATCHING SESSION"
        elif "09:17" <= current_time_str < "13:30": return "OPEN", "🟢 MARKET LIVE (OPEN)"
        elif "13:30" <= current_time_str < "13:50": return "POST-CLOSE", "⚪ POST-CLOSE SESSION"
        elif "13:50" <= current_time_str < "14:20": return "MODIFICATION", "🛠️ TRADE MODIFICATION"
        else: return "CLOSED", "🔴 MARKET CLOSED"

# ================= DATA EXTRACTION ENGINE =================
def fetch_data(symbol):
    global STOCK_CACHE
    now = datetime.now()
    
    if symbol in STOCK_CACHE:
        df, cache_time = STOCK_CACHE[symbol]
        if now - cache_time < timedelta(minutes=CACHE_EXPIRY_MINUTES):
            return df
            
    try:
        end = now
        # Expanded lookback days to 320 to reliably populate 200-period indicators
        start = end - timedelta(days=320)
        df = psxdata.stocks(symbol, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        
        if df is None or df.empty:
            if symbol in STOCK_CACHE: return STOCK_CACHE[symbol][0]
            return None
            
        STOCK_CACHE[symbol] = (df, now)
        return df
    except:
        if symbol in STOCK_CACHE: return STOCK_CACHE[symbol][0]
        return None

def process_metrics(df):
    df = df.sort_values("date").copy()
    if len(df) < 20:
        return None
       
    # Basic technical indicators calculation
    df["rsi"] = RSIIndicator(df["close"], window=14).rsi()
    macd_init = MACD(df["close"])
    df["macd"] = macd_init.macd()
    df["signal_line"] = macd_init.macd_signal()
    
    # Advanced moving averages tracking matrix
    df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["sma_50"] = df["close"].rolling(window=50).mean()
    df["sma_200"] = df["close"].rolling(window=200).mean()
    
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    price = round(float(last_row["close"]), 2)
    prev_price = round(float(prev_row["close"]), 2)
    change_pct = round(((price - prev_price) / prev_price) * 100, 2) if prev_price > 0 else 0.0
    
    raw_volume = last_row.get("volume", 0)
    try:
        volume = int(float(str(raw_volume).replace(',', '')))
    except:
        volume = 0
        
    rsi = last_row["rsi"] if not hasattr(last_row["rsi"], "isna") else 50.0
    macd_v = last_row["macd"]
    signal_v = last_row["signal_line"]
   
    if rsi != rsi: rsi = 50.0
    recent_window = df.tail(15)
    local_high = float(recent_window["high"].max())
    local_low = float(recent_window["low"].min())
   
    resistance = local_high if local_high > price else price * 1.02
    support = local_low if local_low < price else price * 0.98
   
    dist_resistance = max(0.45, round(((resistance - price) / price) * 100, 2))
    dist_support = max(1.12, round(((price - support) / price) * 100, 2))
    
    # Advanced Multi-Layer Structural Pivot Math Matrix (S1-S4 / R1-R4)
    p_high = float(last_row["high"])
    p_low = float(last_row["low"])
    p_close = float(last_row["close"])
    
    pivot = (p_high + p_low + p_close) / 3.0
    r1 = (2 * pivot) - p_low
    s1 = (2 * pivot) - p_high
    r2 = pivot + (p_high - p_low)
    s2 = pivot - (p_high - p_low)
    r3 = p_high + 2 * (pivot - p_low)
    s3 = p_low - 2 * (p_high - pivot)
    r4 = r3 + (p_high - p_low)
    s4 = s3 - (p_high - p_low)
    
    # Historical rolling timeline matrix returns computation
    h_1w = round(((p_close - float(df.iloc[-5]["close"])) / float(df.iloc[-5]["close"])) * 100, 2) if len(df) >= 5 else 0.0
    h_3w = round(((p_close - float(df.iloc[-15]["close"])) / float(df.iloc[-15]["close"])) * 100, 2) if len(df) >= 15 else 0.0
    h_4w = round(((p_close - float(df.iloc[-20]["close"])) / float(df.iloc[-20]["close"])) * 100, 2) if len(df) >= 20 else 0.0
    
    # Structural liquidity calculation engine
    avg_volume_20 = df["volume"].tail(20).mean()
    if volume > avg_volume_20 * 1.5: liquidity_score = "🟢 HIGH LIQUIDITY DEPTH"
    elif volume < avg_volume_20 * 0.5: liquidity_score = "🔴 THIN LIQUIDITY MATRIX"
    else: liquidity_score = "⚡ MODERATE LIQUIDITY DISTRIBUTION"
    
    if rsi < 35 and macd_v > signal_v:
        trend, rec, signal_type = "BULLISH (STRONG)", "BUY / ACCUMULATE", f"STRONG BUY {BRAND_EMOJI}"
        long_trend = "BULLISH"
    elif rsi > 65 and macd_v < signal_v:
        trend, rec, signal_type = "BEARISH (STRONG)", "SELL / EXIT", "STRONG SELL 🔴"
        long_trend = "BEARISH"
    elif rsi > 52:
        trend, rec, signal_type = "BULLISH", "HOLD", "HOLD ⚪"
        long_trend = "BULLISH"
    elif rsi < 45:
        trend, rec, signal_type = "BEARISH", "WATCHING", "NONE ⚖️"
        long_trend = "BEARISH"
    else:
        trend, rec, signal_type = "NEUTRAL (STRONG)", "WAIT", "NONE ⚖️"
        long_trend = "NEUTRAL"
    
    tp_short_min = round(price * (1 + (dist_resistance * 0.005)), 2)
    tp_short_max = round(tp_short_min * 1.003, 2)
    sl_short_min = round(price * 0.985, 2)
    sl_short_max = round(sl_short_min * 1.003, 2)
    pot_profit_short = f"{round(((tp_short_min - price) / price) * 100, 2)}%"
    tp_long_min = round(price * 1.10, 2)
    tp_long_max = round(tp_long_min * 1.02, 2)
    pot_profit_long = f"{round(((tp_long_min - price) / price) * 100, 2)}%"
    trailing_sl = round(price * 0.993, 2)
    buy_zone_min = round(support * 0.99, 2)
    buy_zone_max = round(support * 1.015, 2)
    
    return {
        "price": price, "trend": trend, "rec": rec,
        "change_pct": change_pct, "volume": volume,
        "dist_res": dist_resistance, "dist_sup": dist_support,
        "tp_s_min": tp_short_min, "tp_s_max": tp_short_max,
        "sl_s_min": sl_short_min, "sl_s_max": sl_short_max,
        "p_prof_s": pot_profit_short, "tp_l_min": tp_long_min,
        "tp_l_max": tp_long_max, "p_prof_l": pot_profit_long,
        "l_trend": long_trend, "trail_sl": trailing_sl,
        "bz_min": buy_zone_min, "bz_max": buy_zone_max, "sig": signal_type,
        "raw_res": resistance, "raw_sup": support,
        "r1": round(r1, 2), "r2": round(r2, 2), "r3": round(r3, 2), "r4": round(r4, 2),
        "s1": round(s1, 2), "s2": round(s2, 2), "s3": round(s3, 2), "s4": round(s4, 2),
        "h_1w": h_1w, "h_3w": h_3w, "h_4w": h_4w, "liq": liquidity_score,
        "ema9": round(float(last_row["ema_9"]), 2) if "ema_9" in last_row else price,
        "ema21": round(float(last_row["ema_21"]), 2) if "ema_21" in last_row else price,
        "sma50": round(float(last_row["sma_50"]), 2) if not np.isnan(last_row["sma_50"]) else price,
        "sma200": round(float(last_row["sma_200"]), 2) if not np.isnan(last_row["sma_200"]) else price,
        "rsi_val": round(rsi, 2)
    }

# ================= HIGH-DENSITY CHART MAPPING ENGINE =================
def generate_chart_buffer(df, symbol, metrics):
    chart_df = df.sort_values("date").tail(30).copy()
    chart_df['date'] = pd.to_datetime(chart_df['date'])
    chart_df.set_index('date', inplace=True)
    
    chart_df = chart_df[['open', 'high', 'low', 'close', 'volume']]
    chart_df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    for col in ['Open', 'High', 'Low', 'Close']:
        chart_df[col] = pd.to_numeric(chart_df[col].astype(str).str.replace(',', ''), errors='coerce').astype(float)
    chart_df['Volume'] = pd.to_numeric(chart_df['Volume'].astype(str).str.replace(',', ''), errors='coerce').fillna(0).astype(int)
    
    custom_theme = mpf.make_mpf_style(
        base_mpf_style='nightclouds',
        marketcolors=mpf.make_marketcolors(up='#26a69a', down='#ef5350', inherit=True),
        gridcolor='#2b2b2b', facecolor='#1e1e1e'
    )
    
    buf = io.BytesIO()
    hlines_config = dict(
        hlines=[metrics['raw_res'], metrics['raw_sup']],
        colors=['#ef5350', '#26a69a'],
        linestyle='--',
        linewidths=1.2
    )
    
    mpf.plot(
        chart_df, type='candle', style=custom_theme, volume=True,
        title=f"\n{symbol} Structural Support & Resistance Blueprint",
        hlines=hlines_config, figsize=(11, 6),
        savefig=dict(fname=buf, format='png', dpi=140)
    )
    buf.seek(0)
    return buf

# ================= FINANCIAL NEWS NETWORK SCALPER =================
def fetch_symbol_news(symbol):
    try:
        query = f"{symbol}+PSX+stock+news+Pakistan"
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-PK&gl=PK&ceid=PK:en"
        
        req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        articles = []
        
        for item in root.findall(".//item")[:4]:
            title = item.find("title").text if item.find("title") is not None else ""
            link = item.find("link").text if item.find("link") is not None else ""
            pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
            source = item.find("source").text if item.find("source") is not None else "Financial Source"
            
            if " - " in title: title = title.rsplit(" - ", 1)[0]
            title = html.unescape(title)
            articles.append({"title": title, "link": link, "pub_date": pub_date, "source": source})
            
        if not articles: return None, "neutral", "No records parsed."

        good_words = ["profit", "dividend", "growth", "skyrock", "surge", "expansion", "bullish", "acquisition", "deal", "positive", "increase", "jump", "record"]
        bad_words = ["loss", "decline", "fall", "drop", "penalty", "scam", "cyber", "attack", "decrease", "negative", "slashed", "deficit", "bearish", "fine"]
        
        score = 0
        for art in articles:
            text_lower = art["title"].lower()
            for gw in good_words:
                if gw in text_lower: score += 1
            for bw in bad_words:
                if bw in text_lower: score -= 1
                
        if score > 0: sentiment = "good"
        elif score < 0: sentiment = "bad"
        else: sentiment = "neutral"
            
        return articles, sentiment, score
    except Exception as e:
        print(f"🔴 News Fetcher Error: {e}")
        return None, "error", str(e)

# ================= UI REFRESH AND ANALYTICS LOGIC =================
async def update_dashboard_ui(channel):
    global dashboard_message, last_signals, is_first_scan, last_known_market_state
    state_key, state_label = get_market_status()
    
    if last_known_market_state is not None and state_key != last_known_market_state:
        if state_key == "PRE-OPEN":
            embed_pop = discord.Embed(title="🌅 PSX PRE-OPEN ALIVE", description="Orders are assembling inside the terminal queue.", color=discord.Color.gold())
            await channel.send(embed=embed_pop)
        elif state_key == "OPEN":
            embed_pop = discord.Embed(title="🔔 LIVE SESSION COMMENCED", description="The floor is open. Real-time institutional orders are flowing.", color=discord.Color.green())
            await channel.send(embed=embed_pop)
        elif state_key == "CLOSED":
            embed_pop = discord.Embed(title="🛑 LIVE SESSION TERMINATED", description="Market closing procedures fully processed.", color=discord.Color.red())
            await channel.send(embed=embed_pop)

    last_known_market_state = state_key

    if dashboard_message is None:
        try:
            async for msg in channel.history(limit=50):
                if msg.author == bot.user and msg.embeds and "PSX LIVE INSTITUTIONAL SCANNER" in str(msg.embeds[0].title):
                    dashboard_message = msg
                    print("🔄 Dashboard footprint acquired inside current tracking block.")
                    break
        except Exception as e:
            print(f"⚠️ Channel lookup failed: {e}")

    embed = discord.Embed(
        title=f"{BRAND_EMOJI} PSX LIVE INSTITUTIONAL SCANNER",
        description=f"📊 Session Status: **{state_label}**\n🕒 Last Matrix Sync: **{datetime.now().strftime('%H:%M:%S')}** | Active Assets: {len(WATCHLIST)}\n*Dashboard matrix processing runs every 30 seconds.*",
        color=discord.Color.green() if state_key == "OPEN" else discord.Color.red() if state_key == "CLOSED" else discord.Color.gold()
    )
    embed.set_footer(text=f"Powered by {BRAND_DOMAIN}")
    
    data_tasks = [asyncio.to_thread(fetch_data, sym) for sym in WATCHLIST[:18]]
    results = await asyncio.gather(*data_tasks)
    
    for symbol, df in zip(WATCHLIST[:18], results):
        if df is None or df.empty: continue
        try:
            m = process_metrics(df)
            if not m: continue
            
            vol_val = m['volume']
            if vol_val >= 1_000_000: formatted_vol = f"{vol_val / 1_000_000:.2f}M"
            elif vol_val >= 1_000: formatted_vol = f"{vol_val / 1_000:.1f}K"
            else: formatted_vol = str(vol_val)
                
            sign = "+" if m['change_pct'] > 0 else ""
            field_name = f"{symbol} | {m['sig'].split(' ')[0]}"
            field_value = f"💰 Price: **{m['price']}**\n📊 Chg: `{sign}{m['change_pct']}%`\n💎 Vol: `{formatted_vol}`"
            embed.add_field(name=field_name, value=field_value, inline=True)

            current_state = m["sig"]
            previous_state = last_signals.get(symbol, None)

            if current_state != previous_state:
                if not is_first_scan:
                    if "STRONG BUY" in current_state or "STRONG SELL" in current_state:
                        alert_color = discord.Color.green() if "BUY" in current_state else discord.Color.red()
                        
                        alert_embed = discord.Embed(
                            title=f"🚨 ACTION REQUIRED: {symbol} BREAKOUT",
                            description=f"Structural delta shift mapped for **{symbol}**.",
                            color=alert_color,
                            timestamp=datetime.now(timezone.utc)
                        )
                        alert_embed.add_field(name="Signal Vector", value=f"**{m['sig']}**", inline=False)
                        alert_embed.add_field(name="Market Price", value=f"**{m['price']} PKR**", inline=True)
                        alert_embed.add_field(name="Target Vector (TP)", value=f"**{m['tp_s_min']} - {m['tp_s_max']}**", inline=True)
                        alert_embed.add_field(name="Stop Allocation (SL)", value=f"`{m['sl_s_min']}`", inline=True)
                        alert_embed.set_footer(text=f"Instant Signal Array • {BRAND_DOMAIN}")
                        await channel.send(embed=alert_embed)
                last_signals[symbol] = current_state
        except Exception as e:
            print(f"⚠️ Error calculating metrics for {symbol}: {e}")
            continue
    
    if is_first_scan:
        is_first_scan = False
        print("🟢 Tracking arrays successfully loaded.")

    try:
        if dashboard_message is None: dashboard_message = await channel.send(embed=embed)
        else: await dashboard_message.edit(embed=embed)
    except Exception as e:
        print(f"🔴 Dashboard layout modification error: {e}")
        dashboard_message = None

# ================= REPEAT TICK LOOP =================
@tasks.loop(seconds=30)
async def live_scanner_loop():
    if not is_scanning_active: return
    channel = bot.get_channel(SCANNER_CHANNEL_ID)
    if not channel: return
    await update_dashboard_ui(channel)

# ================= DISCORD INTERACTION INTERFACES =================

@bot.command(name="check")
async def check_all_metrics(ctx, symbol: str = None):
    if not symbol:
        return await ctx.send("❌ **Usage:** `!check BOP`")
        
    symbol = symbol.upper()
    status_msg = await ctx.send(f"🛰️ **Parsing Master A-to-Z Metrics Framework for {symbol}...**")
    
    try:
        df = await asyncio.to_thread(fetch_data, symbol)
        if df is None or df.empty:
            await status_msg.delete()
            return await ctx.send(f"❌ Core telemetry rows returned empty for `{symbol}`.")
            
        m = process_metrics(df)
        await status_msg.delete()
        if not m:
            return await ctx.send(f"❌ Matrix computation failed for `{symbol}` due to insufficient tracking range.")
            
        sign = "+" if m['change_pct'] > 0 else ""
        embed = discord.Embed(
            title=f"{BRAND_EMOJI} MASTER TELEMETRY ENGINE: {symbol}",
            description=f"Current market valuation overview for **{symbol}** traded on the exchange.",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Panel 1: Price and Signal Vector
        embed.add_field(
            name="📊 Price & Market Momentum",
            value=f"💰 **Price:** {m['price']} PKR\n📈 **Change:** `{sign}{m['change_pct']}%`\n🎯 **Signal Status:** {m['sig']}\n⚡ **RSI (14):** `{m['rsi_val']}`",
            inline=False
        )
        
        # Panel 2: Multi-Layer Support and Resistance Matrix
        embed.add_field(
            name="🧱 S/R Support Boundaries",
            value=f"🟢 **S1:** `{m['s1']}`\n🟢 **S2:** `{m['s2']}`\n🟢 **S3:** `{m['s3']}`\n🟢 **S4:** `{m['s4']}`",
            inline=True
        )
        embed.add_field(
            name="🛑 S/R Resistance Ceilings",
            value=f"🔴 **R1:** `{m['r1']}`\n🔴 **R2:** `{m['r2']}`\n🔴 **R3:** `{m['r3']}`\n🔴 **R4:** `{m['r4']}`",
            inline=True
        )
        
        # Panel 3: Historical Timeframes Lookback Engine
        sign1 = "+" if m['h_1w'] > 0 else ""
        sign3 = "+" if m['h_3w'] > 0 else ""
        sign4 = "+" if m['h_4w'] > 0 else ""
        embed.add_field(
            name="⏳ Historical Returns Matrix",
            value=f"📅 **1-Week Performance:** `{sign1}{m['h_1w']}%`\n📅 **3-Week Performance:** `{sign3}{m['h_3w']}%`\n📅 **4-Week Performance:** `{sign4}{m['h_4w']}%`",
            inline=False
        )
        
        # Panel 4: Moving Averages Tracking Nodes
        embed.add_field(
            name="📈 Institutional Moving Averages",
            value=f"▫️ **EMA (9):** `{m['ema9']}`\n▫️ **EMA (21):** `{m['ema21']}`\n▫️ **SMA (50):** `{m['sma50']}`\n▫️ **SMA (200):** `{m['sma200']}`",
            inline=True
        )
        
        # Panel 5: Liquidity Deep Scans & Payout Parameters
        div_info = DIVIDEND_DATABASE.get(symbol, {"yield": "N/A", "payout": "N/A", "sector": "Unmapped"})
        embed.add_field(
            name="💎 Liquidity & Payout Structure",
            value=f"📊 **Liquidity Score:**\n`{m['liq']}`\n🏦 **Sector Hierarchy:** `{div_info['sector']}`\n💰 **Est. Dividend Yield:** `{div_info['yield']}`\n📈 **Payout Ratio:** `{div_info['payout']}`",
            inline=True
        )
        
        embed.set_footer(text=f"A-to-Z Execution Sequence Engine • {BRAND_DOMAIN}")
        await ctx.send(embed=embed)
        
    except Exception as e:
        print(traceback.format_exc())
        try: await status_msg.delete()
        except: pass
        await ctx.send(f"⚠️ Core execution error inside master compiler node: `{str(e)}`")


@bot.command(name="map")
async def map_stock(ctx, symbol: str = None):
    if not symbol:
        return await ctx.send("❌ Usage: `!map BOP`")
    
    symbol = symbol.upper()
    processing_msg = await ctx.send(f"📊 Processing charting array coordinates for **{symbol}**...")
    
    try:
        df = await asyncio.to_thread(fetch_data, symbol)
        if df is None or df.empty:
            await processing_msg.delete()
            return await ctx.send(f"❌ Could not isolate technical data rows for `{symbol}`.")
            
        m = process_metrics(df)
        if not m:
            await processing_msg.delete()
            return await ctx.send(f"❌ Strategy configuration processing matrix failed for `{symbol}`.")
            
        chart_buffer = await asyncio.to_thread(generate_chart_buffer, df, symbol, m)
        await processing_msg.delete()
        
        sign = "+" if m['change_pct'] > 0 else ""
        embed = discord.Embed(
            title=f"📈 {symbol} GRAPHICAL STRATEGY INTERCEPT",
            description=f"💰 **Current Valuation:** {m['price']} PKR (`{sign}{m['change_pct']}%`)\n"
                        f"🟢 **Accumulation Zone:** `{m['bz_min']} - {m['bz_max']}`\n"
                        f"🎯 **Target Runway (TP):** `{m['tp_s_min']} - {m['tp_s_max']}`\n"
                        f"🛡️ **System Protection (SL):** `{m['sl_s_min']}`",
            color=discord.Color.dark_teal()
        )
        embed.set_image(url="attachment://map_chart.png")
        embed.set_footer(text=f"Structural Blueprint System • {BRAND_DOMAIN}")
        
        file = discord.File(fp=chart_buffer, filename="map_chart.png")
        await ctx.send(embed=embed, file=file)
        
    except Exception as e:
        try: await processing_msg.delete()
        except: pass
        await ctx.send(f"⚠️ Graphic compiler exception: `{str(e)}`")

@bot.command(name="scan")
async def force_scan_repost(ctx):
    global dashboard_message
    if dashboard_message:
        try: await dashboard_message.delete()
        except: pass
        dashboard_message = None
        
    status_msg = await ctx.send("🔄 **Relocating live dashboard tracker stack...**")
    try:
        await update_dashboard_ui(ctx.channel)
        await status_msg.delete()
    except Exception as e:
        await ctx.send(f"⚠️ Interface positioning tracking failure: `{e}`")

@bot.command(name="dashboard")
async def dashboard_shortcut(ctx):
    await force_scan_repost(ctx)

@bot.command(name="signals")
async def target_signals_list(ctx):
    processing_msg = await ctx.send("📡 Extracting active tactical alerts from layout structures...")
    buy_signals, sell_signals = [], []
    
    for symbol in WATCHLIST[:25]: 
        df = fetch_data(symbol)
        if df is not None and not df.empty:
            try:
                m = process_metrics(df)
                if not m: continue
                signal_status = m["sig"]
                price_info = f"**{symbol}** @ {m['price']} PKR"
                if "STRONG BUY" in signal_status: buy_signals.append(f"🟢 {price_info}")
                elif "STRONG SELL" in signal_status: sell_signals.append(f"🔴 {price_info}")
            except: continue

    embed = discord.Embed(
        title=f"{BRAND_EMOJI} ACTIVE TARGET SIGNAL COMPILATION",
        description=f"🕒 Execution Time: **{datetime.now().strftime('%I:%M:%S %p')} PKT**",
        color=discord.Color.gold(), timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Market Scan System • {BRAND_DOMAIN}")
    
    if buy_signals: embed.add_field(name="🔥 INSTITUTIONAL ACCUMULATION", value="\n".join(buy_signals), inline=False)
    else: embed.add_field(name="🔥 INSTITUTIONAL ACCUMULATION", value="*No strong breakouts detected.*", inline=False)
    
    if sell_signals: embed.add_field(name="🚨 LIQUIDATION ALERTS", value="\n".join(sell_signals), inline=False)
    else: embed.add_field(name="🚨 LIQUIDATION ALERTS", value="*No risk-out markers crossed.*", inline=False)

    await processing_msg.delete()
    await ctx.send(embed=embed)

@bot.command(name="news")
async def get_news(ctx, symbol: str = None):
    if not symbol: return await ctx.send("❌ Usage: `!news BOP`")
    symbol = symbol.upper()
    status_msg = await ctx.send(f"📡 Querying external financial news layers for **{symbol}**...")
    try:
        articles, sentiment, score = await asyncio.to_thread(fetch_symbol_news, symbol)
        if articles is None:
            await status_msg.delete()
            return await ctx.send(f"ℹ️ No parsed public filings or media statements for `{symbol}`.")
            
        if sentiment == "good": sent_title, sent_color = "🟢 BULLISH SENTIMENT BIAS", discord.Color.green()
        elif sentiment == "bad": sent_title, sent_color = "🔴 BEARISH SENTIMENT BIAS", discord.Color.red()
        else: sent_title, sent_color = "⚪ STRUCTURALLY NEUTRAL SENTIMENT", discord.Color.light_grey()
            
        embed = discord.Embed(title=f"📰 {symbol} MEDIA SENTIMENT LOGS", color=sent_color, timestamp=datetime.now(timezone.utc))
        embed.description = f"**Composite Directional Bias Score:** `{score}`\n\n" + f"**{sent_title}**"
        
        for idx, art in enumerate(articles, 1):
            embed.add_field(name=f"{idx}. {art['source']}", value=f"**[{art['title']}]({art['link']})**", inline=False)
        await status_msg.delete()
        await ctx.send(embed=embed)
    except Exception as e:
        if status_msg: await status_msg.delete()
        await ctx.send(f"⚠️ Analytics news parsing failure: `{str(e)}`")

@bot.command(name="psx")
async def psx(ctx, symbol: str = None):
    if not symbol: return await ctx.send("❌ Usage: `!psx BOP`")
    symbol = symbol.upper()
    processing_msg = await ctx.send(f"🔍 Parsing on-demand structural metrics for **{symbol}**...")
   
    try:
        df = await asyncio.to_thread(fetch_data, symbol)
        if df is None or df.empty:
            await processing_msg.delete()
            return await ctx.send(f"❌ Analytics fetch returned no elements for `{symbol}`.")
        m = process_metrics(df)
        if not m:
            await processing_msg.delete()
            return await ctx.send(f"⚠️ Historical framework length criteria unmet for `{symbol}`.")
        
        sign = "+" if m['change_pct'] > 0 else ""
        report = (
            f"**{symbol}: {m['price']}** ({sign}{m['change_pct']}%)\n"
            f"⚖️ **Trend Profile:** {m['trend']} | **Vol:** {m['volume']:,}\n"
            f"🎯 **Target (Short):** {m['tp_s_min']:.2f} - {m['tp_s_max']:.2f}\n"
            f"🛡️ **Defense (SL):** {m['sl_s_min']:.2f} - {m['sl_s_max']:.2f}\n"
            f"💚 **Accumulation Zone:** {m['bz_min']:.2f} - {m['bz_max']:.2f}\n"
            f"**Signal Execution:** {m['sig']}"
        )
        await processing_msg.delete()
        await ctx.send(report)
    except Exception as e:
        try: await processing_msg.delete()
        except: pass
        await ctx.send(f"⚠️ Evaluation exception: `{str(e)}`")

@bot.command(name="signal")
async def signal_fallback(ctx, symbol: str = None): 
    await psx(ctx, symbol)

@bot.command(name="screener")
async def screener_fallback(ctx):
    embed = discord.Embed(title="📊 PSX DIVIDEND SCREENER PANEL", color=discord.Color.teal())
    for sym, d in DIVIDEND_DATABASE.items():
        embed.add_field(name=f"⚡ {sym}", value=f"Sector: `{d['sector']}`\nYield: **{d['yield']}** | Payout: **{d['payout']}**", inline=False)
    embed.set_footer(text=f"Baseline Snapshot • {BRAND_DOMAIN}")
    await ctx.send(embed=embed)

@bot.command(name="scr")
async def scr_shortcut(ctx):
    await screener_fallback(ctx)

@bot.command(name="add")
async def add_symbol(ctx, symbol: str):
    symbol = symbol.upper()
    if symbol not in WATCHLIST:
        WATCHLIST.append(symbol)
        await ctx.send(f"✅ Appended **{symbol}** to active tracking arrays.")
    else: await ctx.send(f"ℹ️ **{symbol}** already monitored.")

@bot.command(name="remove")
async def remove_symbol(ctx, symbol: str):
    symbol = symbol.upper()
    if symbol in WATCHLIST:
        WATCHLIST.remove(symbol)
        await ctx.send(f"❌ Extracted **{symbol}** from live processing arrays.")
    else: await ctx.send(f"⚠️ **{symbol}** not verified in current tracking arrays.")

@bot.command(name="watchlist")
async def show_watchlist(ctx):
    watchlist_str = ", ".join(WATCHLIST)
    if len(watchlist_str) > 1800: watchlist_str = watchlist_str[:1800] + "..."
    await ctx.send(f"📋 **Active Structural Array Matrix ({len(WATCHLIST)} assets):**\n```{watchlist_str}```")

# ================= INITIALIZATION BLOCK =================
def run_discord_bot():
    """Discord bot ko alag thread mein chalane ke liye function"""
    # Agar bot pehle se start hai toh dubara na karein
if not bot.is_ready():
        # 1. Bot ko wrap karne ke liye function
def run_discord_bot():
    bot.run(DISCORD_TOKEN)

# 2. Initialization Block (Isay file ke bilkul end mein rakhein)
if __name__ == "__main__":
        # Threading: Bot ko background mein chalayega
        threading.Thread(target=run_discord_bot, daemon=True).start()
        
        # API Server: Main process mein chalega
        uvicorn.run(app, host="0.0.0.0", port=8000)

@bot.event
async def on_ready():
    print(f"=====================================================")
    print(f"🟢 Connection Established: {bot.user.name}")
    print(f"🔥 Active Core Domain: {BRAND_DOMAIN}")
    print(f"=====================================================")
    if not live_scanner_loop.is_running(): 
        live_scanner_loop.start()

if __name__ == "__main__":
    # 1. Bot ko background mein start karein
    bot_thread = threading.Thread(target=run_discord_bot, daemon=True)
    bot_thread.start()
    
    # 2. FastAPI server ko main process mein chalayein
    # Railway ke liye host 0.0.0.0 aur port zaroori hai
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
# 1. Bot ko wrap karne ke liye function
def run_discord_bot():
    bot.run(DISCORD_TOKEN)  # Yeh line 4 spaces aage honi chahiye

# 2. Initialization Block
if __name__ == "__main__":
    # Yeh dono lines bhi 4 spaces aage honi chahiye
    threading.Thread(target=run_discord_bot, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
