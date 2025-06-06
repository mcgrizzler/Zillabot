import discord
import re
import os
from cryptography.fernet import Fernet

intents = discord.Intents.default()
intents.message_content = True

def load_token_from_file(token_file_path: str) -> str:
    """
    Loads the Discord bot token from a file.
    """
    with open(token_file_path, "r") as token_file:
        return token_file.readline().strip()

class ZillowBot(discord.Client):
    async def on_ready(self):
        print(f'Logged in as {self.user}')

    async def on_message(self, message):
        if message.author == self.user:
            return

        # Check for zillow.com links
        zillow_links = re.findall(r'https?://(?:www\.)?zillow\.com[^\s]*', message.content)
        if zillow_links:
            await message.channel.send(f"Zillow link detected: {', '.join(zillow_links)}")

if __name__ == "__main__":
    try:
        TOKEN = load_token_from_file("token.dat")
    except Exception as e:
        print(f"Failed to load token: {e}")
        TOKEN = None

    if not TOKEN:
        print("Please create a file named 'token.dat' with your Discord bot token on the first line.")
    else:
        client = ZillowBot(intents=intents)
        client.run(TOKEN)