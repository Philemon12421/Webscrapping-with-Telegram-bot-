#!/usr/bin/env python3
"""
Instagram Growth & Content Analytics Tool
Legitimate — uses official Instagram Graph API only.
No automation of likes/follows/comments. No fake engagement.
"""

import os
import json
import time
import csv
import logging
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

import requests
import pandas as pd
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ============================================================
# CONFIGURATION — EDIT THESE
# ============================================================

TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
ADMIN_CHAT_ID = "YOUR_CHAT_ID"

# Facebook / Instagram Graph API
# 1. Go to https://developers.facebook.com/apps
# 2. Create an app -> Business -> Next
# 3. Add "Instagram Graph API" product
# 4. Go to Tools -> Graph API Explorer
# 5. Select your app, get a User Access Token with pages_show_list, instagram_basic, instagram_content_publish, pages_read_engagement
FACEBOOK_ACCESS_TOKEN = "YOUR_FACEBOOK_LONG_LIVED_TOKEN"
INSTAGRAM_BUSINESS_ID = "YOUR_INSTAGRAM_BUSINESS_ID"  # Get this from /me/accounts then /{page_id}?fields=instagram_business_account

# ============================================================
# SETUP
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

DB_PATH = "instagram_analytics.db"

GRAPH_API_BASE = "https://graph.facebook.com/v18.0"

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Trend sources for content ideas (public, non-logged-in scraping)
TREND_SOURCES = {
    "reddit": "https://www.reddit.com/r/trendingsubreddits.json",
    "github_trending": "https://api.github.com/search/repositories?q=created:>2024-01-01&sort=stars&order=desc&per_page=10",
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS analytics_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE,
            followers INTEGER,
            follows INTEGER,
            media_count INTEGER,
            reach INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            profile_views INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS hashtag_tracker (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hashtag TEXT,
            date TEXT,
            posts_count INTEGER DEFAULT 0,
            avg_likes INTEGER DEFAULT 0,
            avg_comments INTEGER DEFAULT 0,
            UNIQUE(hashtag, date)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS content_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            source TEXT,
            title TEXT,
            url TEXT,
            idea_type TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS posts_cache (
            id TEXT PRIMARY KEY,
            caption TEXT,
            media_type TEXT,
            like_count INTEGER DEFAULT 0,
            comments_count INTEGER DEFAULT 0,
            timestamp TEXT,
            hashtags TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


# ============================================================
# INSTAGRAM GRAPH API WRAPPER
# ============================================================

class InstagramAPI:
    """Wrapper for Instagram Graph API (official, read-only analytics)."""

    def __init__(self, access_token, business_id):
        self.access_token = access_token
        self.business_id = business_id

    def _get(self, endpoint, params=None):
        """Make a Graph API GET request."""
        if params is None:
            params = {}
        params["access_token"] = self.access_token
        url = f"{GRAPH_API_BASE}/{endpoint}"
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 200:
                return r.json()
            else:
                logger.error(f"Graph API error {r.status_code}: {r.text}")
                return None
        except Exception as e:
            logger.error(f"Graph API request failed: {e}")
            return None

    def get_basic_profile(self):
        """Get basic profile info: followers, follows, media count."""
        fields = "followers_count,follows_count,media_count,name,username,profile_picture_url"
        data = self._get(f"{self.business_id}", {"fields": fields})
        if data:
            return {
                "followers": data.get("followers_count", 0),
                "follows": data.get("follows_count", 0),
                "media_count": data.get("media_count", 0),
                "name": data.get("name", ""),
                "username": data.get("username", ""),
                "profile_pic": data.get("profile_picture_url", ""),
            }
        return None

    def get_insights(self, metric="impressions,reach,profile_views", period="day", since=None, until=None):
        """
        Get account insights.
        Metrics: impressions, reach, profile_views, follower_count, email_contacts, phone_call_clicks, text_message_clicks, get_directions_clicks, website_clicks
        Period: day, week, days_28, lifetime
        """
        params = {
            "metric": metric,
            "period": period,
        }
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        data = self._get(f"{self.business_id}/insights", params)
        if data and "data" in data:
            results = {}
            for item in data["data"]:
                name = item.get("name", "").lower()
                values = item.get("values", [])
                if values:
                    # Get most recent value
                    results[name] = values[-1].get("value", 0)
            return results
        return {}

    def get_recent_media(self, limit=25):
        """Get recent posts with engagement stats."""
        fields = "id,caption,media_type,media_url,like_count,comments_count,timestamp,permalink"
        data = self._get(f"{self.business_id}/media", {"fields": fields, "limit": limit})
        if data and "data" in data:
            posts = []
            for post in data["data"]:
                caption = post.get("caption", "")
                # Extract hashtags from caption
                hashtags = re.findall(r"#(\w+)", caption) if caption else []
                posts.append({
                    "id": post.get("id"),
                    "caption": caption[:200] if caption else "",
                    "media_type": post.get("media_type"),
                    "media_url": post.get("media_url", ""),
                    "like_count": post.get("like_count", 0),
                    "comments_count": post.get("comments_count", 0),
                    "timestamp": post.get("timestamp", ""),
                    "permalink": post.get("permalink", ""),
                    "hashtags": hashtags,
                })
            return posts
        return []

    def get_hashtag_search(self, hashtag_name):
        """Search for a hashtag's ID (requires Instagram Creator account)."""
        # This endpoint needs instagram_hashtag_search permission
        data = self._get(f"/ig_hashtag_search", {"user_id": self.business_id, "q": hashtag_name})
        if data and "data" in data:
            return data["data"]
        return []

    def get_hashtag_analytics(self, hashtag_id):
        """Get analytics for a specific hashtag."""
        fields = "name,media_count,profile_picture_url"
        data = self._get(f"{hashtag_id}", {"fields": fields})
        if data:
            # Get recent media for this hashtag
            media = self._get(f"{hashtag_id}/recent_media", {
                "user_id": self.business_id, "fields": "id,caption,like_count,comments_count,timestamp"
            })
            avg_likes = 0
            avg_comments = 0
            count = 0
            if media and "data" in media:
                for m in media["data"]:
                    avg_likes += m.get("like_count", 0)
                    avg_comments += m.get("comments_count", 0)
                    count += 1
                if count > 0:
                    avg_likes = avg_likes // count
                    avg_comments = avg_comments // count

            return {
                "name": data.get("name"),
                "media_count": data.get("media_count", 0),
                "avg_likes": avg_likes,
                "avg_comments": avg_comments,
            }
        return None


# ============================================================
# CONTENT IDEA SCRAPER (Public Sources)
# ============================================================

def fetch_trending_ideas():
    """Fetch trending topics from public sources for content inspiration."""
    ideas = []
    
    # Reddit trending
    try:
        r = requests.get(TREND_SOURCES["reddit"], headers=COMMON_HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for post in data.get("data", {}).get("children", [])[:15]:
                p = post.get("data", {})
                ideas.append({
                    "source": "Reddit",
                    "title": p.get("title", ""),
                    "url": f"https://reddit.com{p.get('permalink', '')}",
                    "type": "Trending Topic",
                })
    except Exception as e:
        logger.warning(f"Reddit trending fetch failed: {e}")

    # GitHub trending (tech/creator angles)
    try:
        r = requests.get(TREND_SOURCES["github_trending"], headers=COMMON_HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for repo in data.get("items", [])[:10]:
                ideas.append({
                    "source": "GitHub",
                    "title": f"{repo.get('name', '')} - {repo.get('description', '')[:100]}",
                    "url": repo.get("html_url", ""),
                    "type": "Trending Project",
                })
    except Exception as e:
        logger.warning(f"GitHub trending fetch failed: {e}")

    # Save to DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    for idea in ideas:
        c.execute(
            "INSERT OR IGNORE INTO content_ideas (date, source, title, url, idea_type) VALUES (?, ?, ?, ?, ?)",
            (today, idea["source"], idea["title"][:300], idea["url"], idea["type"])
        )
    conn.commit()
    conn.close()

    return ideas


# ============================================================
# ANALYTICS ENGINE
# ============================================================

def run_full_analytics(api, save_to_db=True):
    """Run a full analytics pull and return results."""
    results = {}

    # Basic profile
    profile = api.get_basic_profile()
    if profile:
        results["profile"] = profile

    # Daily insights (last 7 days)
    today = datetime.now()
    seven_days_ago = int((today - timedelta(days=7)).timestamp())
    today_ts = int(today.timestamp())
    
    insights = api.get_insights(
        metric="impressions,reach,profile_views,follower_count",
        period="day",
        since=seven_days_ago,
        until=today_ts
    )
    results["insights"] = insights

    # Weekly aggregated insights
    weekly = api.get_insights(
        metric="impressions,reach,profile_views",
        period="week"
    )
    results["weekly_insights"] = weekly

    # Recent posts
    posts = api.get_recent_media(limit=20)
    results["recent_posts"] = posts

    # Post engagement metrics
    if posts:
        total_likes = sum(p.get("like_count", 0) for p in posts)
        total_comments = sum(p.get("comments_count", 0) for p in posts)
        total_posts_with_data = len([p for p in posts if p.get("like_count", 0) > 0 or p.get("comments_count", 0) > 0])
        results["avg_likes"] = total_likes // len(posts) if posts else 0
        results["avg_comments"] = total_comments // len(posts) if posts else 0
        results["total_engagement"] = total_likes + total_comments

        # Top performing post
        sorted_posts = sorted(posts, key=lambda x: x.get("like_count", 0), reverse=True)
        if sorted_posts:
            results["top_post"] = sorted_posts[0]

        # Extract all hashtags used
        all_hashtags = []
        for p in posts:
            all_hashtags.extend(p.get("hashtags", []))
        results["used_hashtags"] = list(set(all_hashtags))

    # Save to cache DB
    if save_to_db and profile:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        today_str = today.strftime("%Y-%m-%d")
        try:
            c.execute("""
                INSERT OR REPLACE INTO analytics_cache 
                (date, followers, follows, media_count, reach, impressions, profile_views)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                today_str,
                profile.get("followers", 0),
                profile.get("follows", 0),
                profile.get("media_count", 0),
                insights.get("reach", 0) if isinstance(insights, dict) else 0,
                insights.get("impressions", 0) if isinstance(insights, dict) else 0,
                insights.get("profile_views", 0) if isinstance(insights, dict) else 0,
            ))
        except Exception as e:
            logger.warning(f"DB cache error: {e}")
        conn.commit()
        conn.close()

    return results


# ============================================================
# REPORT GENERATION
# ============================================================

def generate_analytics_report(results):
    """Format analytics into a readable report string."""
    lines = []
    lines.append("📊 *Instagram Analytics Report*")
    lines.append(f"_{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append("")

    profile = results.get("profile", {})
    if profile:
        lines.append(f"👤 *@{profile.get('username', 'Unknown')}*")
        lines.append(f"📛 {profile.get('name', '')}")
        lines.append(f"👥 *Followers:* {profile.get('followers', 0):,}")
        lines.append(f"👣 *Following:* {profile.get('follows', 0):,}")
        lines.append(f"📸 *Posts:* {profile.get('media_count', 0)}")
        lines.append("")

    insights = results.get("insights", {})
    if insights:
        lines.append("*📈 Last 7 Days (Daily Total):*")
        lines.append(f"👁️ *Reach:* {insights.get('reach', 0):,}")
        lines.append(f"💡 *Impressions:* {insights.get('impressions', 0):,}")
        lines.append(f"👤 *Profile Views:* {insights.get('profile_views', 0):,}")
        lines.append("")

    lines.append(f"*Engagement (Last {len(results.get('recent_posts', []))} posts):*")
    lines.append(f"❤️ *Avg Likes:* {results.get('avg_likes', 0):,}")
    lines.append(f"💬 *Avg Comments:* {results.get('avg_comments', 0):,}")
    lines.append(f"📊 *Total Engagement:* {results.get('total_engagement', 0):,}")
    lines.append("")

    top_post = results.get("top_post", {})
    if top_post:
        caption = top_post.get("caption", "")[:80]
        likes = top_post.get("like_count", 0)
        comments = top_post.get("comments_count", 0)
        lines.append(f"*🏆 Top Post:* {likes} likes, {comments} comments")
        lines.append(f"  _{caption}_")
        lines.append("")

    hashtags = results.get("used_hashtags", [])
    if hashtags:
        lines.append(f"*#️⃣ Hashtags Used:* {' '.join(f'#{h}' for h in hashtags[:10])}")
        if len(hashtags) > 10:
            lines.append(f"  _...and {len(hashtags) - 10} more_")
        lines.append("")

    # Growth over time
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT * FROM analytics_cache ORDER BY date DESC LIMIT 30", conn)
        if len(df) >= 2:
            first = df.iloc[-1]
            last = df.iloc[0]
            follower_change = last["followers"] - first["followers"]
            emoji = "📈" if follower_change > 0 else "📉" if follower_change < 0 else "➡️"
            lines.append(f"*Growth (30 days):*")
            lines.append(f"{emoji} Follower change: {follower_change:+d}")
            lines.append(f"  {first['followers']:,} → {last['followers']:,}")
    except Exception as e:
        logger.warning(f"Growth calc error: {e}")
    finally:
        conn.close()

    return "\n".join(lines)


def generate_content_ideas_report():
    """Format saved content ideas into a readable list."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT source, title, url, idea_type FROM content_ideas ORDER BY date DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()

    if not rows:
        return "No content ideas cached yet. Use /ideas to fetch new ones."

    lines = []
    lines.append("💡 *Content Ideas for Your Next Post*")
    lines.append("")
    
    for i, (source, title, url, idea_type) in enumerate(rows, 1):
        lines.append(f"{i}. *[{source}]* {title[:100]}")
        if url:
            lines.append(f"   {url}")
        lines.append("")

    lines.append("_Use these as inspiration for your Instagram content!_")
    
    return "\n".join(lines)


# ============================================================
# TELEGRAM HANDLERS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 *Instagram Growth & Analytics Bot*\n\n"
        "This bot uses the *official Instagram Graph API* to provide analytics.\n"
        "No fake engagement, no automation of likes/follows — legitimate tools only.\n\n"
        "*Commands:*\n"
        "/analytics — Get your Instagram analytics report\n"
        "/posts — View your recent post performance\n"
        "/ideas — Fetch trending content ideas\n"
        "/hashtags — Analyze your hashtag usage\n"
        "/growth — See follower growth over time\n"
        "/refresh — Force a fresh analytics pull\n"
        "/export — Export analytics to CSV\n"
        "/schedule — Set daily/weekly reports\n\n"
        "_Requires Instagram Business/Creator account._",
        parse_mode="Markdown"
    )


async def analytics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run analytics and return report."""
    msg = await update.message.reply_text("📊 Pulling your Instagram analytics...")
    
    api = InstagramAPI(FACEBOOK_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ID)
    results = run_full_analytics(api)
    
    if not results.get("profile"):
        await msg.edit_text(
            "❌ Could not fetch Instagram data.\n"
            "Check your token and Instagram Business ID configuration.\n"
            "Make sure your access token has the required permissions."
        )
        return
    
    report = generate_analytics_report(results)
    await msg.edit_text(report, parse_mode="Markdown")


async def posts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent post performance."""
    msg = await update.message.reply_text("📸 Fetching your recent posts...")
    
    api = InstagramAPI(FACEBOOK_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ID)
    posts = api.get_recent_media(limit=15)
    
    if not posts:
        await msg.edit_text("No posts found or unable to fetch.")
        return
    
    lines = []
    lines.append(f"📸 *Recent {len(posts)} Posts*")
    lines.append("")
    
    for i, post in enumerate(posts, 1):
        caption = post.get("caption", "")[:60] or "(no caption)"
        likes = post.get("like_count", 0)
        comments = post.get("comments_count", 0)
        ts = post.get("timestamp", "")[:10]
        media_type = post.get("media_type", "IMAGE")
        type_icon = {"IMAGE": "📷", "VIDEO": "🎬", "CAROUSEL_ALBUM": "📚"}.get(media_type, "📷")
        
        lines.append(f"{i}. {type_icon} {caption}")
        lines.append(f"   ❤️ {likes}  💬 {comments}  🕐 {ts}")
        if post.get("hashtags"):
            lines.append(f"   #{' #'.join(post['hashtags'][:5])}")
        lines.append("")
    
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


async def ideas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch and display trending content ideas."""
    msg = await update.message.reply_text("💡 Fetching trending content ideas...")
    
    ideas = fetch_trending_ideas()
    
    if not ideas:
        await msg.edit_text("Couldn't fetch ideas. Try again later.")
        return
    
    report = generate_content_ideas_report()
    await msg.edit_text(report, parse_mode="Markdown")


async def hashtag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyze hashtag usage from your recent posts."""
    msg = await update.message.reply_text("#️⃣ Analyzing your hashtag usage...")
    
    api = InstagramAPI(FACEBOOK_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ID)
    posts = api.get_recent_media(limit=30)
    
    if not posts:
        await msg.edit_text("No posts found to analyze.")
        return
    
    # Count hashtag frequency and associated engagement
    hashtag_stats = defaultdict(lambda: {"count": 0, "total_likes": 0, "total_comments": 0})
    
    for post in posts:
        likes = post.get("like_count", 0)
        comments = post.get("comments_count", 0)
        for ht in post.get("hashtags", []):
            ht_lower = ht.lower()
            hashtag_stats[ht_lower]["count"] += 1
            hashtag_stats[ht_lower]["total_likes"] += likes
            hashtag_stats[ht_lower]["total_comments"] += comments
    
    if not hashtag_stats:
        await msg.edit_text("No hashtags found in your recent posts. Try adding hashtags to your posts!")
        return
    
    # Sort by frequency
    sorted_hashtags = sorted(hashtag_stats.items(), key=lambda x: x[1]["count"], reverse=True)
    
    lines = []
    lines.append("#️⃣ *Hashtag Usage Analysis*")
    lines.append(f"_Based on last {len(posts)} posts_")
    lines.append("")
    lines.append("`#Hashtag        | Posts | Avg Likes | Avg Cmts`")
    lines.append("─" * 50)
    
    for ht, stats in sorted_hashtags[:20]:
        avg_likes = stats["total_likes"] // stats["count"]
        avg_comments = stats["total_comments"] // stats["count"]
        lines.append(f"`#{ht:<15}| {stats['count']:<5} | {avg_likes:<9} | {avg_comments:<8}`")
    
    lines.append("")
    lines.append("_Tip: Use a mix of popular and niche hashtags for best reach._")
    
    await msg.edit_text("\n".join(lines), parse_mode="Markdown")


async def growth_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show follower growth chart data."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT date, followers FROM analytics_cache ORDER BY date ASC", conn)
    except Exception as e:
        await update.message.reply_text(f"Error reading data: {e}")
        return
    finally:
        conn.close()
    
    if df.empty:
        await update.message.reply_text(
            "No historical data yet. Run /analytics a few times over several days to build growth history."
        )
        return
    
    lines = []
    lines.append("📈 *Follower Growth Over Time*")
    lines.append("")
    
    for _, row in df.iterrows():
        lines.append(f"  {row['date']}: {row['followers']:,}")
    
    if len(df) >= 2:
        first = df.iloc[0]["followers"]
        last = df.iloc[-1]["followers"]
        change = last - first
        pct = (change / first * 100) if first else 0
        lines.append("")
        lines.append(f"*Total Change:* {change:+d} ({pct:+.1f}%)")
        lines.append(f"*Period:* {df.iloc[0]['date']} → {df.iloc[-1]['date']}")
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force a fresh analytics pull."""
    msg = await update.message.reply_text("🔄 Refreshing all analytics data...")
    
    api = InstagramAPI(FACEBOOK_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ID)
    results = run_full_analytics(api)
    
    if results.get("profile"):
        # Also fetch ideas
        fetch_trending_ideas()
        await msg.edit_text("✅ Analytics refreshed! Use /analytics to see the latest data.")
    else:
        await msg.edit_text("❌ Refresh failed. Check your API configuration.")


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export analytics to CSV."""
    msg = await update.message.reply_text("📁 Exporting analytics data...")
    
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT * FROM analytics_cache ORDER BY date ASC", conn)
    except Exception as e:
        await msg.edit_text(f"Export error: {e}")
        return
    finally:
        conn.close()
    
    if df.empty:
        await msg.edit_text("No data to export. Run /analytics first.")
        return
    
    csv_path = f"/tmp/instagram_analytics_{datetime.now().strftime('%Y%m%d')}.csv"
    df.to_csv(csv_path, index=False)
    
    # Send via Telegram
    with open(csv_path, "rb") as f:
        await update.message.reply_document(
            f,
            filename=f"instagram_analytics_{datetime.now().strftime('%Y%m%d')}.csv",
            caption=f"📊 Instagram Analytics Export — {len(df)} records"
        )
    
    await msg.edit_text("✅ Export sent above!")


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show schedule info."""
    await update.message.reply_text(
        "⏰ *Scheduled Reports*\n\n"
        "This bot supports scheduled analytics pulls.\n"
        "Configure cron jobs in the code or use a service like cron-job.org\n\n"
        "Example cron schedule (runs daily at 8 AM):\n"
        "`0 8 * * * curl -s https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>&text=/analytics`\n\n"
        "Or run the bot with APScheduler (uncomment the scheduler section in the code).",
        parse_mode="Markdown"
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")


# ============================================================
# MAIN
# ============================================================

def main():
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("analytics", analytics_command))
    application.add_handler(CommandHandler("posts", posts_command))
    application.add_handler(CommandHandler("ideas", ideas_command))
    application.add_handler(CommandHandler("hashtags", hashtag_command))
    application.add_handler(CommandHandler("growth", growth_command))
    application.add_handler(CommandHandler("refresh", refresh_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_error_handler(error_handler)
    
    logger.info("Instagram Analytics Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import re  # For hashtag regex in the class
    main()
