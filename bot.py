#Caleb McManus
#Discord Bot for interacting with a dedicated github server to post update notifications
#of GitHub repo updates.
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

#Will load the variables from local .env files
#See documentations for what you need if you wish to run yourself
load_dotenv()
#Read the private Discord token from .env.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
#Intents controls Discord events the bots will be receiving
intents = discord.Intents.default()
#Allows the bot to read commands from Discord channels
intents.message_content = True

#Creation of the bot
#Has it so all commands will begin with an exclamation mark.
bot = commands.Bot( command_prefix="!",
                   intents = intents)

#Bot events
@bot.event
async def on_ready():
    #Runs when the bot successfully connects to discord
    print ("--------------------------")
    print (f"Connected as: {bot.user}")
    print (f"Bot ID: {bot.user.id}")
    print ("--------------------------")

    #Sets up commands
    @bot.command()
    async def test(context):
        """
        Will run when someone types !test in Discord
        This is for testing purposes.
        """
        await context.send("The GitHub release bot is working.")

#Catch when the program is missing the token
if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN was not found/ loaded. Please check your .env file."
        )

#Connects the bot to Discord.
bot.run(DISCORD_TOKEN)