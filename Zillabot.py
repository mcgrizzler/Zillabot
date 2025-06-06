import discord
import re
import os
import sqlite3
import requests
from bs4 import BeautifulSoup
from cryptography.fernet import Fernet

intents = discord.Intents.default()
intents.message_content = True

def load_token_from_file(token_file_path: str) -> str:
    """
    Loads the Discord bot token from a file.
    """
    with open(token_file_path, "r") as token_file:
        return token_file.readline().strip()

def init_db(db_path="Data/zillow_properties.db"):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            name TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_property_to_db(url, name, db_path="Data/zillow_properties.db"):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO properties (url, name) VALUES (?, ?)", (url, name))
    conn.commit()
    conn.close()

def get_property_name_from_zillow(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        # Zillow property name is usually in the <title> tag
        title = soup.title.string if soup.title else "Unknown Property"
        # Optionally, clean up the title
        name = title.replace(" | Zillow", "").strip()
        return name
    except Exception as e:
        return f"Error fetching property: {e}"

class ZillowBot(discord.Client):
    async def on_ready(self):
        print(f'Logged in as {self.user}')
        init_db()

    async def on_message(self, message):
        if message.author == self.user:
            return

        # Check for zillow.com links
        zillow_links = re.findall(r'https?://(?:www\.)?zillow\.com[^\s]*', message.content)
        for link in zillow_links:
            await message.channel.send(f"Zillow link detected: {link}")
            property_name = get_property_name_from_zillow(link)
            save_property_to_db(link, property_name)
            await message.channel.send(f"Property name saved: {property_name}")

if __name__ == "__main__":
    try:
        TOKEN = load_token_from_file("Data/token.dat")
    except Exception as e:
        print(f"Failed to load token: {e}")
        TOKEN = None

    if not TOKEN:
        print("Please create a file named 'token.dat' with your Discord bot token on the first line.")
    else:
        client = ZillowBot(intents=intents)
        client.run(TOKEN)