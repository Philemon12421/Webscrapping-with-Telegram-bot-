
```markdown
# 📊 Content Idea Scraper Telegram Bot

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&height=120&section=header&text=Content%20Idea%20Scraper%20Bot&fontSize=40&fontAlignY=25" width="100%"/>
</p>

<p align="center">
  <img src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&weight=600&size=22&duration=3000&pause=1000&color=36BCF7&center=true&vCenter=true&width=600&lines=Scrape+7+Platforms+for+Content+Ideas;Auto-Delivered+Daily+via+Telegram;Built+for+Creators+%26+Marketers;No+API+Keys+Needed+%F0%9F%9A%80" alt="Typing SVG"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Platform-Telegram-blue?logo=telegram"/>
  <img src="https://img.shields.io/badge/Scrapes-7%20Platforms-brightgreen"/>
  <img src="https://img.shields.io/badge/Delivery-Excel%20%7C%20Email%20%7C%20WhatsApp-orange"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow"/>
  <img src="https://img.shields.io/badge/Status-Active-success"/>
</p>

---

## 🌟 What Is This?

A **Telegram bot** that scours **7 different platforms** every day for fresh content ideas based on *your* topics. It compiles everything into a tidy **Excel (.xlsx) report** and delivers it to you automatically.

**Stop staring at a blank page. Let the bot find your next viral idea.** 🧠

---

## 🎯 Why Use This?

| 😩 Without Bot | 🚀 With Bot |
| :--- | :--- |
| Spend hours browsing Reddit | Bot scrapes it in seconds |
| Manually open 7+ tabs | Single command does it all |
| Copy-paste links into a doc | Auto-generated Excel report |
| Forget to check regularly | Scheduled daily delivery |
| Miss trending topics | Scrapes Twitter, News, YouTube |

---

## 🌐 Platforms Scraped

```text
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   1. 🔴 Reddit         — Top posts by keyword           │
│   2. 🐦 Twitter/X      — Tweets via Nitter              │
│   3. ✍️  Medium         — Articles by tag                │
│   4. ▶️  YouTube        — Videos via Invidious           │
│   5. ❓ Quora          — Questions people ask           │
│   6. 📦 Amazon Reviews — Customer pain points           │
│   7. 📰 Google News    — Trending stories               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🧠 Content Angles It Detects

Every idea is automatically classified into a content angle so you know exactly what type of content to create:

| Angle | Examples |
| :--- | :--- |
| 📘 **Tutorial / How-To** | Guides, walkthroughs, step-by-step |
| 🔄 **Comparison** | X vs Y, alternatives |
| ⭐ **Review / List** | Best X, top Y |
| 🔧 **Problem/Solution** | Fixes, troubleshooting |
| 🎓 **Educational** | What is X, explained |
| 📊 **Analysis / Why** | Deep dives, reasons |
| 💡 **Tips & Strategies** | Hacks, ways to... |
| 🔮 **Trend / Future** | Predictions, upcoming |
| ⚠️ **Mistakes to Avoid** | Don't do this |
| 🗣️ **Expert Advice** | Interviews, thoughts |

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
# Debian/Ubuntu/Kali:
sudo apt update && sudo apt install -y python3-venv python3-full

# Create virtual environment (recommended):
python3 -m venv contentbot_env
source contentbot_env/bin/activate

# Install packages:
pip install python-telegram-bot requests beautifulsoup4 lxml pandas openpyxl apscheduler
```

### 2. Get Your Telegram Bot Token
1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the instructions.
3. Copy your API Token (e.g., `123456:ABC-DEF...`).

### 3. Get Your Chat ID
1. Message your new bot (anything, like "Hello").
2. Open this link in your browser: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find the `"id":` value in the JSON response.

### 4. Configure & Run
Open `content_idea_bot.py` and update these variables:
```python
TELEGRAM_BOT_TOKEN = "YOUR_TOKEN_HERE"
ADMIN_CHAT_ID = "YOUR_CHAT_ID_HERE"
```

Run the bot:
```bash
python content_idea_bot.py
```

---

## 📱 Bot Commands

| Command | Action |
| :--- | :--- |
| `/start` | Show welcome screen |
| `/addtopics` | Add topics (e.g., `/addtopics python, marketing`) |
| `/mytopics` | View current tracked topics |
| `/removetopic` | Delete a specific topic |
| `/scrape` | Run all scrapers immediately |
| `/report` | Download the latest Excel report |
| `/help` | View all commands |

---

## 📊 Excel Report Preview
The generated `.xlsx` file includes:
* **Platform:** Source of the idea.
* **Title:** The headline or post title.
* **URL:** Direct link to the content.
* **Content Angle:** The AI-categorized type of post.
* **Score:** Engagement metrics (Upvotes/Views).

---

## 📧 Optional: Delivery Setup

### Gmail Notification
```python
EMAIL_ENABLED = True
EMAIL_SENDER = "you@gmail.com"
EMAIL_PASSWORD = "xxxx xxxx xxxx xxxx" # Gmail App Password
EMAIL_RECEIVER = "target@example.com"
```

### WhatsApp (Twilio)
```python
WHATSAPP_ENABLED = True
TWILIO_ACCOUNT_SID = "your_sid"
TWILIO_AUTH_TOKEN = "your_token"
WHATSAPP_RECEIVER = "whatsapp:+1234567890"
```

---

## 🛠️ Project Structure
```text
.
├── content_idea_bot.py     # Main application
├── content_bot.db          # SQLite Database (auto-generated)
├── requirements.txt        # Dependencies
└── reports/                # Folder for generated Excel files
```

---

## 🚀 Running 24/7 (Systemd)
To keep the bot running on a server:
```bash
sudo nano /etc/systemd/system/contentbot.service
```
Paste the following:
```ini
[Unit]
Description=Content Idea Bot
After=network.target

[Service]
ExecStart=/path/to/venv/bin/python /path/to/content_idea_bot.py
WorkingDirectory=/path/to/project
Restart=always
User=yourusername

[Install]
WantedBy=multi-user.target
```
Then run:
```bash
sudo systemctl enable contentbot && sudo systemctl start contentbot
```

---

## 📄 License
MIT — Feel free to use and modify for personal or commercial projects.

Made with ❤️ for Content Creators.
```
