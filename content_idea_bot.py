#!/usr/bin/env python3
"""
Content Idea Scraper Telegram Bot
Scrapes Reddit, Twitter, Medium, YouTube, Quora, Amazon, and more for content ideas.
Compiles results into a neat Excel file and delivers via Telegram/Email/WhatsApp.
"""

import os
import re
import json
import csv
import io
import time
import random
import logging
import smtplib
import sqlite3
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from collections import defaultdict

import requests
from bs4 import BeautifulSoup
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    ContextTypes, CallbackQueryHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ============================================================
# CONFIGURATION — EDIT THESE
# ============================================================

# --- Telegram ---
TELEGRAM_BOT_TOKEN = "zYoDx1-tI_J05gtheEJk"  # Get from @BotFather
ADMIN_CHAT_ID = "503"  # Your Telegram user ID

# --- Email (Gmail SMTP) ---
EMAIL_ENABLED = False
EMAIL_SENDER = "youremail@gmail.com"
EMAIL_PASSWORD = "your-app-password"  # Use Gmail App Password, not your regular password
EMAIL_RECEIVER = "receiver@example.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# --- WhatsApp (Twilio) ---
WHATSAPP_ENABLED = False
TWILIO_ACCOUNT_SID = "your_twilio_sid"
TWILIO_AUTH_TOKEN = "your_twilio_token"
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"  # Twilio sandbox number
WHATSAPP_RECEIVER = "whatsapp:+1234567890"  # Your number (must be verified in sandbox)

# --- Scraping Settings ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Results per platform per scrape
RESULTS_LIMIT = 20

# ============================================================
# SETUP
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database for user topics
DB_PATH = "content_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_topics (
            chat_id INTEGER,
            topic TEXT,
            UNIQUE(chat_id, topic)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            date TEXT,
            platform TEXT,
            title TEXT,
            url TEXT,
            source TEXT,
            topic TEXT,
            snippet TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_random_header():
    return {"User-Agent": random.choice(USER_AGENTS)}

# ============================================================
# SCRAPERS — Each platform returns list of dicts
# ============================================================

def scrape_reddit(topic, limit=RESULTS_LIMIT):
    """Scrape Reddit using free JSON endpoints. No API key needed."""
    results = []
    try:
        # Use Reddit's public JSON endpoint
        url = f"https://www.reddit.com/search.json?q={topic}&sort=top&t=week&limit={limit}"
        headers = get_random_header()
        headers["Accept"] = "application/json"
        
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            logger.warning(f"Reddit returned {r.status_code} for topic: {topic}")
            return results
        
        data = r.json()
        posts = data.get("data", {}).get("children", [])
        
        for post in posts:
            post_data = post.get("data", {})
            title = post_data.get("title", "No title")
            permalink = post_data.get("permalink", "")
            url_full = f"https://www.reddit.com{permalink}" if permalink else ""
            score = post_data.get("score", 0)
            num_comments = post_data.get("num_comments", 0)
            selftext = post_data.get("selftext", "")[:200]
            
            results.append({
                "platform": "Reddit",
                "title": title,
                "url": url_full,
                "snippet": selftext or title,
                "score": score,
                "comments": num_comments,
                "topic": topic
            })
        
        time.sleep(random.uniform(0.5, 1.5))
    except Exception as e:
        logger.error(f"Reddit scrape error: {e}")
    
    return results


def scrape_twitter(topic, limit=RESULTS_LIMIT):
    """Scrape Twitter/X via Nitter (public front-end, no API needed)."""
    results = []
    nitter_instances = [
        "https://nitter.net",
        "https://nitter.lacontrevoie.fr",
        "https://nitter.1d4.us",
    ]
    
    for instance in nitter_instances:
        try:
            url = f"{instance}/search?q={topic}&f=tweets"
            r = requests.get(url, headers=get_random_header(), timeout=15)
            if r.status_code != 200:
                continue
            
            soup = BeautifulSoup(r.text, "lxml")
            tweets = soup.select(".timeline-item")[:limit]
            
            for tweet in tweets:
                title_el = tweet.select_one(".tweet-content")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)[:300]
                
                link_el = tweet.select_one("a.tweet-link")
                url_path = link_el.get("href", "") if link_el else ""
                full_url = f"{instance}{url_path}" if url_path else ""
                
                stats = tweet.select_one(".tweet-stats")
                
                results.append({
                    "platform": "Twitter/X",
                    "title": title,
                    "url": full_url,
                    "snippet": title,
                    "score": 0,
                    "comments": 0,
                    "topic": topic
                })
            
            if results:
                break
            
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            logger.warning(f"Nitter instance {instance} failed: {e}")
            continue
    
    return results


def scrape_medium(topic, limit=RESULTS_LIMIT):
    """Scrape Medium articles by tag."""
    results = []
    try:
        tag = topic.lower().replace(" ", "-")
        url = f"https://medium.com/tag/{tag}"
        r = requests.get(url, headers=get_random_header(), timeout=15)
        if r.status_code != 200:
            return results
        
        soup = BeautifulSoup(r.text, "lxml")
        
        # Medium uses a script tag with JSON data
        scripts = soup.find_all("script")
        for script in scripts:
            if "window.__INITIAL_STATE__" in script.text:
                json_str = script.text.split("= ")[1].split(";")[0]
                data = json.loads(json_str)
                # Navigate the nested objects (structure varies)
                try:
                    posts = list(data.get("collections", {}).values())
                    # Simplified: just grab visible article cards
                    break
                except:
                    pass
        
        # Fallback: grab article cards from HTML
        articles = soup.select("article")[:limit]
        for article in articles:
            h2 = article.select_one("h2")
            h3 = article.select_one("h3")
            title = (h2.get_text(strip=True) if h2 else "") or (h3.get_text(strip=True) if h3 else "Medium article")
            
            link_el = article.select_one("a[href*='medium.com']") or article.select_one("a")
            link = link_el.get("href", "") if link_el else ""
            if link and not link.startswith("http"):
                link = f"https://medium.com{link}"
            
            results.append({
                "platform": "Medium",
                "title": title,
                "url": link,
                "snippet": title,
                "score": 0,
                "comments": 0,
                "topic": topic
            })
        
        time.sleep(random.uniform(0.5, 1))
    except Exception as e:
        logger.error(f"Medium scrape error: {e}")
    
    return results


def scrape_youtube(topic, limit=RESULTS_LIMIT):
    """Scrape YouTube search results using yt-dlp metadata extraction."""
    results = []
    try:
        # Use invidious or piped instances as free YouTube frontends
        instances = [
            "https://invidious.snopyta.org",
            "https://yewtu.be",
            "https://inv.riverside.rocks",
        ]
        
        for instance in instances:
            try:
                url = f"{instance}/search?q={topic}&sort=views"
                r = requests.get(url, headers=get_random_header(), timeout=15)
                if r.status_code != 200:
                    continue
                
                soup = BeautifulSoup(r.text, "lxml")
                videos = soup.select(".video-card")[:limit]
                
                for vid in videos:
                    title_el = vid.select_one("p.title") or vid.select_one("h4")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    
                    link_el = vid.select_one("a[href*='/watch']")
                    href = link_el.get("href", "") if link_el else ""
                    full_url = f"{instance}{href}" if href else ""
                    
                    results.append({
                        "platform": "YouTube",
                        "title": title,
                        "url": full_url,
                        "snippet": title,
                        "score": 0,
                        "comments": 0,
                        "topic": topic
                    })
                
                if results:
                    break
                time.sleep(random.uniform(1, 2))
            except:
                continue
    except Exception as e:
        logger.error(f"YouTube scrape error: {e}")
    
    return results


def scrape_quora(topic, limit=RESULTS_LIMIT):
    """Scrape Quora for questions related to a topic."""
    results = []
    try:
        url = f"https://www.quora.com/search?q={topic}&type=question"
        r = requests.get(url, headers=get_random_header(), timeout=15)
        if r.status_code != 200:
            return results
        
        soup = BeautifulSoup(r.text, "lxml")
        
        # Quora is heavily JS-rendered, but we can grab what we can
        question_els = soup.select("a.question_link") or soup.select("a[href*='/questions/']")[:limit]
        
        for q in question_els:
            title = q.get_text(strip=True)
            href = q.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://www.quora.com{href}"
            
            if title and len(title) > 10:
                results.append({
                    "platform": "Quora",
                    "title": title,
                    "url": href,
                    "snippet": title,
                    "score": 0,
                    "comments": 0,
                    "topic": topic
                })
        
        time.sleep(random.uniform(1, 2))
    except Exception as e:
        logger.error(f"Quora scrape error: {e}")
    
    return results


def scrape_amazon_reviews(topic, limit=RESULTS_LIMIT):
    """Scrape Amazon for product reviews mentioning pain points."""
    results = []
    try:
        search_url = f"https://www.amazon.com/s?k={topic}&ref=nb_sb_noss"
        r = requests.get(search_url, headers=get_random_header(), timeout=15)
        if r.status_code != 200:
            return results
        
        soup = BeautifulSoup(r.text, "lxml")
        
        # Get product links
        products = soup.select("a.a-link-normal.s-underline-text.s-link-style")[:5]
        
        for prod in products[:3]:  # Check first 3 products
            prod_url = prod.get("href", "")
            if not prod_url or "/dp/" not in prod_url:
                continue
            if not prod_url.startswith("http"):
                prod_url = f"https://www.amazon.com{prod_url}"
            
            # Get the product page
            time.sleep(random.uniform(1, 2))
            prod_r = requests.get(prod_url, headers=get_random_header(), timeout=15)
            if prod_r.status_code != 200:
                continue
            
            prod_soup = BeautifulSoup(prod_r.text, "lxml")
            prod_title = prod_soup.select_one("#productTitle")
            prod_title_text = prod_title.get_text(strip=True) if prod_title else "Amazon Product"
            
            # Look for review snippets
            reviews = prod_soup.select("span.review-text") or prod_soup.select("[data-hook='review-body']")[:limit]
            
            for rev in reviews:
                text = rev.get_text(strip=True)[:300]
                if text and len(text) > 20:
                    results.append({
                        "platform": "Amazon Reviews",
                        "title": f"Review: {prod_title_text[:80]}",
                        "url": prod_url,
                        "snippet": text[:200],
                        "score": 0,
                        "comments": 0,
                        "topic": topic
                    })
            
            time.sleep(random.uniform(0.5, 1))
    except Exception as e:
        logger.error(f"Amazon scrape error: {e}")
    
    return results


def scrape_news(topic, limit=RESULTS_LIMIT):
    """Scrape Google News for trending topic ideas."""
    results = []
    try:
        url = f"https://news.google.com/search?q={topic}&hl=en-US&gl=US&ceid=US:en"
        r = requests.get(url, headers=get_random_header(), timeout=15)
        if r.status_code != 200:
            return results
        
        soup = BeautifulSoup(r.text, "lxml")
        articles = soup.select("article")[:limit]
        
        for article in articles:
            title_el = article.select_one("h3, h4, a[aria-label]")
            if not title_el:
                continue
            title = title_el.get("aria-label", "") or title_el.get_text(strip=True)
            
            link_el = article.select_one("a")
            href = ""
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("./"):
                    href = f"https://news.google.com{href[1:]}"
            
            results.append({
                "platform": "Google News",
                "title": title,
                "url": href,
                "snippet": title,
                "score": 0,
                "comments": 0,
                "topic": topic
            })
        
        time.sleep(random.uniform(0.5, 1))
    except Exception as e:
        logger.error(f"News scrape error: {e}")
    
    return results


# ============================================================
# EXCEL GENERATION
# ============================================================

def generate_excel(all_results, topic_filters=None):
    """Generate a formatted Excel file from all results."""
    
    # Flatten all results
    data = []
    seen = set()
    
    for result in all_results:
        # Deduplicate by URL
        url_key = result.get("url", "")
        if url_key and url_key in seen:
            continue
        if url_key:
            seen.add(url_key)
        
        data.append({
            "Platform": result.get("platform", ""),
            "Topic": result.get("topic", ""),
            "Title": result.get("title", ""),
            "URL": result.get("url", ""),
            "Snippet / Idea": result.get("snippet", "")[:250],
            "Score": result.get("score", ""),
            "Comments": result.get("comments", ""),
            "Date Found": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Content Angle": classify_angle(result.get("title", "") + " " + result.get("snippet", ""))
        })
    
    if not data:
        df = pd.DataFrame([{"Status": "No results found for your topics. Try different keywords or check back later."}])
    else:
        df = pd.DataFrame(data)
    
    # Write to Excel with formatting
    filename = f"content_ideas_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    filepath = f"/tmp/{filename}"
    
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Content Ideas", index=False)
        
        # Auto-adjust column widths
        from openpyxl import load_workbook
        wb = writer.book
        ws = writer.sheets["Content Ideas"]
        
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 60)
            ws.column_dimensions[column_letter].width = adjusted_width
    
    return filepath, filename


def classify_angle(text):
    """Classify the content idea into an angle/category."""
    text = text.lower()
    
    if any(w in text for w in ["how to", "guide", "tutorial", "step", "walkthrough", "beginner"]):
        return "Tutorial / How-To"
    elif any(w in text for w in ["vs", "versus", "alternative", "better", "compared", "comparison"]):
        return "Comparison"
    elif any(w in text for w in ["review", "best", "top", "recommended", "worth"]):
        return "Review / List"
    elif any(w in text for w in ["problem", "fix", "solution", "error", "issue", "help", "support"]):
        return "Problem/Solution"
    elif any(w in text for w in ["what is", "definition", "explain", "meaning", "introduction"]):
        return "Educational / Explain"
    elif any(w in text for w in ["why", "reason", "because", "cause", "impact"]):
        return "Analysis / Why"
    elif any(w in text for w in ["tips", "tricks", "hacks", "ideas", "strategies", "ways"]):
        return "Tips & Strategies"
    elif any(w in text for w in ["trend", "future", "2025", "2026", "upcoming", "prediction"]):
        return "Trend / Future"
    elif any(w in text for w in ["mistake", "avoid", "wrong", "dont"]):
        return "Mistakes to Avoid"
    elif any(w in text for w in ["interview", "expert", "advice", "thoughts"]):
        return "Expert Advice"
    else:
        return "General"


# ============================================================
# DELIVERY FUNCTIONS
# ============================================================

async def send_to_telegram(update_or_chat_id, filepath, filename, caption="Here's your content ideas Excel file"):
    """Send Excel file via Telegram."""
    chat_id = update_or_chat_id if isinstance(update_or_chat_id, int) else update_or_chat_id.effective_chat.id
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    
    with open(filepath, "rb") as f:
        files = {"document": (filename, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        data = {"chat_id": chat_id, "caption": caption}
        requests.post(url, data=data, files=files)


def send_email(filepath, filename):
    """Send Excel file via email."""
    if not EMAIL_ENABLED:
        return False
    
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        msg["Subject"] = f"Content Ideas Report - {datetime.now().strftime('%Y-%m-%d')}"
        
        body = f"Attached is your content ideas report generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}.\n\nTopics and platforms scraped.\n\n- Content Idea Bot"
        msg.attach(MIMEText(body, "plain"))
        
        with open(filepath, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            msg.attach(part)
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Email sent to {EMAIL_RECEIVER}")
        return True
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return False


def send_whatsapp(filepath, filename):
    """Send Excel via WhatsApp using Twilio."""
    if not WHATSAPP_ENABLED:
        return False
    
    try:
        from twilio.rest import Client
        
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Twilio needs the file hosted somewhere accessible
        # Simple approach: send a text message with the report summary
        message = client.messages.create(
            body=f"Content Ideas Report ({datetime.now().strftime('%Y-%m-%d')}) has been generated and sent to your email/Telegram. Check those platforms for the full Excel file.",
            from_=TWILIO_WHATSAPP_NUMBER,
            to=WHATSAPP_RECEIVER
        )
        
        logger.info(f"WhatsApp message sent: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        return False


# ============================================================
# SCRAPE ENGINE — Runs all scrapers for all user topics
# ============================================================

async def run_all_scrapes(chat_id=None, return_results=False):
    """Run all scrapers for all stored topics. Returns results list."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if chat_id:
        c.execute("SELECT DISTINCT topic FROM user_topics WHERE chat_id = ?", (chat_id,))
    else:
        c.execute("SELECT DISTINCT chat_id, topic FROM user_topics")
    
    rows = c.fetchall()
    conn.close()
    
    all_results = []
    
    # Build topic list
    topics = set()
    topic_chat_map = defaultdict(set)
    
    if chat_id:
        for row in rows:
            topics.add(row[0])
            topic_chat_map[row[0]].add(chat_id)
    else:
        for row in rows:
            topics.add(row[1])
            topic_chat_map[row[1]].add(row[0])
    
    if not topics:
        return all_results
    
    scrapers = [
        ("Reddit", scrape_reddit),
        ("Twitter/X", scrape_twitter),
        ("Medium", scrape_medium),
        ("YouTube", scrape_youtube),
        ("Quora", scrape_quora),
        ("Amazon Reviews", scrape_amazon_reviews),
        ("Google News", scrape_news),
    ]
    
    logger.info(f"Starting scrape for {len(topics)} topics across {len(scrapers)} platforms")
    
    for topic in topics:
        for platform_name, scraper_func in scrapers:
            try:
                logger.info(f"Scraping {platform_name} for: {topic}")
                results = scraper_func(topic)
                
                if return_results:
                    all_results.extend(results)
                
                # Store in DB
                if results:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    today = datetime.now().strftime("%Y-%m-%d")
                    for r in results:
                        for cid in topic_chat_map[topic]:
                            c.execute("""
                                INSERT OR IGNORE INTO daily_results 
                                (chat_id, date, platform, title, url, source, topic, snippet)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (cid, today, r["platform"], r["title"], r["url"], r["url"], r["topic"], r["snippet"]))
                    conn.commit()
                    conn.close()
                
                logger.info(f"Got {len(results)} results from {platform_name} for '{topic}'")
                
            except Exception as e:
                logger.error(f"Failed scraping {platform_name} for {topic}: {e}")
    
    return all_results


# ============================================================
# SCHEDULED REPORT
# ============================================================

async def generate_and_deliver_daily_report():
    """Generates report and delivers via all configured channels."""
    logger.info("=== RUNNING DAILY SCHEDULED REPORT ===")
    
    all_results = await run_all_scrapes(return_results=True)
    
    if not all_results:
        # Try getting results from today's DB entries
        conn = sqlite3.connect(DB_PATH)
        today = datetime.now().strftime("%Y-%m-%d")
        df = pd.read_sql(f"SELECT * FROM daily_results WHERE date = '{today}'", conn)
        conn.close()
        
        if df.empty:
            logger.warning("No results to report")
            return
    
    # Generate Excel
    filepath, filename = generate_excel(all_results)
    
    # Send to Telegram admin
    try:
        await send_to_telegram(ADMIN_CHAT_ID, filepath, filename, 
                               f"Daily Content Ideas Report — {datetime.now().strftime('%Y-%m-%d')}")
        logger.info("Daily report sent via Telegram")
    except Exception as e:
        logger.error(f"Failed to send daily report via Telegram: {e}")
    
    # Send via email
    if EMAIL_ENABLED:
        send_email(filepath, filename)
    
    # Send via WhatsApp
    if WHATSAPP_ENABLED:
        send_whatsapp(filepath, filename)
    
    logger.info("=== DAILY REPORT COMPLETE ===")


async def generate_and_deliver_weekly_report():
    """Weekly summary report."""
    logger.info("=== RUNNING WEEKLY REPORT ===")
    
    # Get last 7 days of data
    conn = sqlite3.connect(DB_PATH)
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    df = pd.read_sql(f"SELECT * FROM daily_results WHERE date >= '{week_ago}' ORDER BY date DESC", conn)
    conn.close()
    
    if df.empty:
        await send_to_telegram(ADMIN_CHAT_ID, None, None, 
                               "Weekly Report: No data collected this week. Add topics with /addtopics")
        return
    
    # Group by platform and topic
    summary = df.groupby(["platform", "topic"]).size().reset_index(name="count")
    
    # Create weekly Excel
    all_results = []
    for _, row in df.iterrows():
        all_results.append(row.to_dict())
    
    filepath, filename = generate_excel(all_results)
    
    await send_to_telegram(ADMIN_CHAT_ID, filepath, filename,
                           f"WEEKLY Content Ideas Report — {datetime.now().strftime('%Y-%m-%d')}\n"
                           f"Total ideas collected this week: {len(df)}\n"
                           f"Platforms: {', '.join(df['platform'].unique())}")
    
    if EMAIL_ENABLED:
        send_email(filepath, filename)
    
    if WHATSAPP_ENABLED:
        send_whatsapp(filepath, filename)
    
    logger.info("=== WEEKLY REPORT COMPLETE ===")


# ============================================================
# TELEGRAM BOT HANDLERS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message."""
    await update.message.reply_text(
        "Content Idea Scraper Bot\n\n"
        "I scrape Reddit, Twitter, Medium, YouTube, Quora, Amazon Reviews, and Google News "
        "for content ideas based on your topics.\n\n"
        "Commands:\n"
        "/addtopics topic1, topic2, topic3 — Set your topics\n"
        "/mytopics — See your current topics\n"
        "/removetopic topic — Remove a topic\n"
        "/scrape — Run a scrape right now\n"
        "/report — Generate and get your Excel report\n"
        "/platforms — See all platforms I scrape\n"
        "/schedule — See the schedule\n"
        "/help — Full help\n\n"
        "Built for content creators, bloggers, and marketers."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help."""
    await update.message.reply_text(
        "How to use this bot:\n\n"
        "1. Set your topics with /addtopics\n"
        "2. Run /scrape to collect fresh ideas\n"
        "3. Run /report to get your Excel file\n"
        "4. Or just wait — daily reports auto-deliver!\n\n"
        "Delivery Channels:\n"
        "- Telegram (this bot)\n"
        "- Email (if configured)\n"
        "- WhatsApp (if configured)\n\n"
        "Tips:\n"
        "- More specific topics = better results\n"
        '- Try: "digital marketing tips", "vegan recipes", "Python tutorials"\n'
        "- Results are saved daily and compiled weekly"
    )


async def add_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add topics for scraping."""
    text = update.message.text.replace("/addtopics", "").strip()
    
    if not text:
        await update.message.reply_text(
            "Please provide topics separated by commas.\n\n"
            "Example: /addtopics digital marketing, Python programming, vegan recipes"
        )
        return
    
    topics = [t.strip() for t in text.split(",") if t.strip()]
    chat_id = update.effective_chat.id
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    added = 0
    for topic in topics:
        try:
            c.execute("INSERT OR IGNORE INTO user_topics (chat_id, topic) VALUES (?, ?)", 
                     (chat_id, topic.lower()))
            if c.rowcount > 0:
                added += 1
        except:
            pass
    
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"Added {added} topic(s):\n"
        f"{', '.join(topics)}\n\n"
        f"Run /scrape to collect ideas now, or wait for the daily report!"
    )


async def my_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's topics."""
    chat_id = update.effective_chat.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT topic FROM user_topics WHERE chat_id = ?", (chat_id,))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await update.message.reply_text(
            "You haven't set any topics yet.\n"
            "Use /addtopics topic1, topic2, topic3 to get started!"
        )
        return
    
    topics = [row[0] for row in rows]
    await update.message.reply_text(
        f"Your Topics:\n{', '.join(topics)}\n\n"
        f"Total: {len(topics)} topics"
    )


async def remove_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a topic."""
    text = update.message.text.replace("/removetopic", "").strip()
    
    if not text:
        await update.message.reply_text(
            "Usage: /removetopic topic_name\n"
            "See your topics with /mytopics"
        )
        return
    
    chat_id = update.effective_chat.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM user_topics WHERE chat_id = ? AND topic = ?", 
             (chat_id, text.lower()))
    removed = c.rowcount
    conn.commit()
    conn.close()
    
    if removed:
        await update.message.reply_text(f"Removed '{text}' from your topics.")
    else:
        await update.message.reply_text(f"Topic '{text}' not found. Use /mytopics to see your topics.")


async def scrape_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run scrape immediately."""
    await update.message.reply_text("Starting scrape across all platforms... This may take a minute.")
    
    chat_id = update.effective_chat.id
    all_results = await run_all_scrapes(chat_id=chat_id, return_results=True)
    
    total = len(all_results)
    platforms_found = set(r["platform"] for r in all_results)
    
    await update.message.reply_text(
        f"Scrape complete!\n"
        f"- Found {total} ideas across {len(platforms_found)} platforms\n"
        f"- Platforms: {', '.join(sorted(platforms_found))}\n\n"
        f"Run /report to generate your Excel file!"
    )


async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send Excel report."""
    msg = await update.message.reply_text("Generating your Excel report...")
    
    # Get today's results from DB
    chat_id = update.effective_chat.id
    conn = sqlite3.connect(DB_PATH)
    today = datetime.now().strftime("%Y-%m-%d")
    
    df = pd.read_sql(f"""
        SELECT * FROM daily_results 
        WHERE chat_id = ? AND date = ?
        ORDER BY platform, topic
    """, conn, params=(chat_id, today))
    conn.close()
    
    if df.empty:
        # Try yesterday
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql(f"""
            SELECT * FROM daily_results 
            WHERE chat_id = ? AND date = ?
            ORDER BY platform, topic
        """, conn, params=(chat_id, yesterday))
        conn.close()
    
    if df.empty:
        await msg.edit_text("No data yet. Run /scrape first to collect ideas!")
        return
    
    # Convert to list of dicts
    all_results = []
    for _, row in df.iterrows():
        all_results.append({
            "platform": row["platform"],
            "title": row["title"],
            "url": row["url"],
            "snippet": row["snippet"],
            "topic": row["topic"],
            "score": 0,
            "comments": 0
        })
    
    filepath, filename = generate_excel(all_results)
    
    platform_count = df["platform"].nunique()
    topic_count = df["topic"].nunique()
    
    await send_to_telegram(
        chat_id, filepath, filename,
        f"Content Ideas Report — {today}\n"
        f"- {len(df)} ideas from {platform_count} platforms\n"
        f"- {topic_count} topics\n\n"
        f"Daily reports are also sent automatically!"
    )
    
    await msg.edit_text("Excel report sent above!")


async def show_platforms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show available platforms."""
    await update.message.reply_text(
        "Platforms I Scrape:\n\n"
        "1. Reddit — Top posts by topic\n"
        "2. Twitter/X — Trending tweets\n"
        "3. Medium — Articles by tag\n"
        "4. YouTube — Top videos\n"
        "5. Quora — Questions people ask\n"
        "6. Amazon Reviews — Pain points & needs\n"
        "7. Google News — Trending news\n\n"
        "Each platform gives you a different angle for content ideas!"
    )


async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the scraping schedule."""
    await update.message.reply_text(
        "Schedule:\n\n"
        "- Daily Scrape: Runs every day at 06:00 AM UTC\n"
        "- Daily Report: Delivered right after scraping\n"
        "  -> Telegram\n"
        f"  -> Email {'YES' if EMAIL_ENABLED else 'NO (not configured)'}\n"
        f"  -> WhatsApp {'YES' if WHATSAPP_ENABLED else 'NO (not configured)'}\n"
        "- Weekly Report: Every Sunday at 10:00 AM UTC\n\n"
        "You can also trigger manually with /scrape and /report"
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors."""
    logger.error(f"Update {update} caused error {context.error}")


# ============================================================
# MAIN
# ============================================================

# Initialize scheduler (module-level, no start() yet — that happens in post_init)
scheduler = AsyncIOScheduler()


async def post_init(application: Application):
    """Start the scheduler after the application is running (event loop exists)."""
    # Daily at 06:00 UTC
    scheduler.add_job(
        generate_and_deliver_daily_report,
        trigger="cron",
        hour=6,
        minute=0,
        timezone="UTC",
        id="daily_report",
        replace_existing=True
    )

    # Weekly on Sunday at 10:00 UTC
    scheduler.add_job(
        generate_and_deliver_weekly_report,
        trigger="cron",
        day_of_week="sun",
        hour=10,
        minute=0,
        timezone="UTC",
        id="weekly_report",
        replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler started — daily report @ 06:00 UTC, weekly report @ Sun 10:00 UTC")


def main():
    """Start the bot."""
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("addtopics", add_topics))
    application.add_handler(CommandHandler("mytopics", my_topics))
    application.add_handler(CommandHandler("removetopic", remove_topic))
    application.add_handler(CommandHandler("scrape", scrape_now))
    application.add_handler(CommandHandler("report", generate_report))
    application.add_handler(CommandHandler("platforms", show_platforms))
    application.add_handler(CommandHandler("schedule", show_schedule))
    application.add_error_handler(error_handler)
    
    logger.info("Bot starting... Press Ctrl+C to stop.")
    
    # Run the bot — this starts the event loop internally
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
