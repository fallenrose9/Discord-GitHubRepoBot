#Caleb McManus
#Discord Bot for interacting with a dedicated github server to post update notifications
#of GitHub repo updates.
import os
from tabnanny import check
import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pathlib import Path

#Pathing settings
#Path to the folder containg bot.py
PROJECT_FOLDER = Path(__file__).resolve().parent
#Path to the file that stores the installed bot version txt
VERSION_FILE = PROJECT_FOLDER/ "version.txt"

#Will load the variables from local .env files
#See documentations for what you need if you wish to run yourself
load_dotenv()

#Does a conversion since .getenv ends up with a string instead of a int
#Also includes error cataching. Mainly used for userIDS and channel IDS.
def read_integer_setting(setting_name):
    setting_value = os.getenv(setting_name, "").strip()
    if not setting_value:
        return 0
    try:
        return int(setting_value)
    except ValueError:
        raise RuntimeError(
            f"{setting_name} must contain numbers only. "
            "Please check your .env file."
        )

#Read the private Discord token from .env.
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN","").strip()
#Reads the github username
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "").strip()

#Sets up security for mainenance commands
BOT_OWNER_ID = read_integer_setting("BOT_OWNER_ID") #Updated to include a check for string to int conversion
MAINTENANCE_CHANNEL_ID = read_integer_setting("MAINTENANCE_CHANNEL_ID")

#Repository that contains updates for this bot.
UPDATE_REPOSITORY = os.getenv( "UPDATE_REPOSITORY", 
                              "Discord-GitHubRepoBot").strip()

#Handles the expected GitHub release Zip name
#examples:
#-GitHubDiscordBot-v0.1.0.zip
#-GitHubDiscordBot-v0.2.0.zip
UPDATE_ASSET_NAME_PREFIX = os.getenv(
    "UPDATE_ASSET_NAME_PREFIX", "GitHubDiscordBot-v").strip()

#Intents controls Discord events the bots will be receiving
intents = discord.Intents.default()
#Allows the bot to read commands from Discord channels
intents.message_content = True

#Creation of the bot
#Has it so all commands will begin with an exclamation mark.
bot = commands.Bot( command_prefix="!",
                   intents = intents, case_insensitive=True)

#Defines maintenance command ownership check
def maintenance_command():
    """
    Restricts command over maintenance to configured bot owner inside
    the configured maintenance channel.
    """
    #Does the check for owner and channel
    async def predicate(context):
        #Gets correct user
        correct_user = ( context.author.id == BOT_OWNER_ID)
        #Gets correct channel
        correct_channel = ( context.channel.id == MAINTENANCE_CHANNEL_ID)
        #returns the correct user and channels
        return correct_user and correct_channel
    return commands.check(predicate)

#Defines the system to be able to read it's installed version.
def read_installed_version():
    """
    Uses the 'version.txt' file to find the version.
    Need to make sure this is updated everytime updates are made.
    """
    #Attempts to get the version from the file
    try:
        installed_version = VERSION_FILE.read_text(encoding="utf-8").strip()
        if installed_version:
            return installed_version
    #make an error catch
    except OSError:
        pass
    #Returns
    return "Unknown"

#Latest bot version function
async def get_latest_bot_release():
    """
    Will pull the latest publish GitHub release for this bot
    Returns:
        A directionary containg the release information.
    Raises:
        RuntimeError if GitHub fails
    """
    #Gets the url
    release_url = (
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{UPDATE_REPOSITORY}/releases/latest")
    #Creates the header
    headers = {
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Discord-GitHubRepoBot"}
    #error try
    try:
        async with aiohttp.ClientSession( headers=headers) as session:
            async with session.get(release_url) as response:
                if response.status == 404:
                    raise RuntimeError("No published GitHub release was found.")
                if response.status != 200:
                    response_text = await response.text()
                    raise RuntimeError(
                       "GitHub could not complete the request."
                       f"Http status: {response.status}."
                       f"Response: {response_text[:200]}")
                return await response.json()
    #error catch
    except aiohttp.ClientError as error:
        raise RuntimeError( f"Could not connect to GitHub: {error}")

#Converts the version to comparable state
def convert_version_to_numbers(version_text):
    """
    As mentioned, this will revert the version text into something easier to compare.
    Example is that v0.1.1 becomes (0, 1, 1)
    """
    #Creates a "clean" version for comparison vy removing blank space and the 'v' prefix
    cleaned_version = version_text.strip().removeprefix("v")
    version_parts = cleaned_version.split(".")
    #Try the tuple
    try:
        #Creates a loop through parts
        return tuple(int(part) for part in version_parts)
    #Error catch
    except ValueError:
        raise RuntimeError(
            f"Invalid version format: {version_text}. Expected a version such as v0.1.1.")

#Bot events
@bot.event
async def on_ready():
    #Runs when the bot successfully connects to discord
    print ("--------------------------")
    print (f"Connected as: {bot.user}")  #UserName
    print (f"Bot ID: {bot.user.id}")     #UserID
    print (f"Version: {read_installed_version()}") #Installed version
    print ("--------------------------")

#Sets up commands
@bot.command()
#Intend to remove in a later release
async def test(context):
 """
 Will run when someone types !test in Discord
 This is for testing purposes.
 """
 await context.send("The GitHub release bot is working.")

#The Maintenance commands.
#Should only be used in a desinated channel and by the owner of the bot.
#Version Command
@bot.command()
@maintenance_command()
async def version(context):
    """
    Displays the installed bersion and the update info.
    Should only work for the configured owner and inside maintenance channel.
    Check your .env file for saving your ids.
    """
    installed_version = read_installed_version()
    expected_asset_pattern = (f"{UPDATE_ASSET_NAME_PREFIX}<version>.zip")

    #Change the first line to match your bot name.
    await context.send(
        "**Seraph Azrael-GH Version Information**\n\n"
        f"Installed version: `{installed_version}`\n"
        f"Update repository: `{GITHUB_USERNAME}/{UPDATE_REPOSITORY}`\n"
        f"Update asset pattern: `{expected_asset_pattern}`"
        )

#Handles the errors caused by the !version command
@version.error
async def version_error(context, error):
    if isinstance(error, commands.CheckFailure):
        await context.send(
            "Command can only be used by the bot owner inside the maintenance channel.")
        return
    raise error

#Checkupdate command
@bot.command()
@maintenance_command()
async def checkupdate(context):
    """
    Will check GitHub for a newer release.
    This command only checks, not installs.
    """
    await context.send("Checking GitHub for the latest release...")
    #Attempts to pull the github release name and info
    try:
        latest_release = await get_latest_bot_release()
        installed_version = read_installed_version()
        latest_version = latest_release.get("tag_name","").strip()
        release_page = latest_release.get("html_url","")
        #tag error
        if not latest_version:
            raise RuntimeError("Latest GitHub release does not have a tag.")
        #converts installed version to int from string
        installed_numbers = convert_version_to_numbers(installed_version)
        #Saves the latest version from Git as an int from string
        latest_numbers = convert_version_to_numbers(latest_version)

        #Compares the two install version tags
        if latest_numbers > installed_numbers:
            await context.send(
                "**Update available**\n\n"
                f"Installed version: `{installed_version}`\n"
                f"Latest version: `{latest_version}`\n"
                f"Release page: {release_page}\n\n"
                "Use `!upade` to install it.")
        #Happens if the versions are the same
        elif latest_numbers == installed_numbers:
            await context.send(
                "**The bot is up to date.**\n\n"
                f"Installed version: `{installed_version}`\n"
                f"Latest version: `{latest_version}`")
        #If installed version is newer
        else:
            await context.send(
                "**Installed version is newer than the latest GitHub release.**\n\n"
                f"Installed version: `{installed_version}`\n"
                f"Latest published version: `{latest_version}`")
    #Error hadle if update check failed
    except RuntimeError as error:
        await context.send(f"Update check failed: {error}")

#Handles the !checkupdate error
@checkupdate.error
async def checkupdate_error(context, error):
    if isinstance(error, commands.CheckFailure):
        await context.send(
            "Command can only be used by the bot owner inside the maintenance channel.")
        return
    raise error

#Validates settings before connecting...
#Discord token
if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN was not found/ loaded. Please check your .env file."
        )
#GitHub_UserName
if not GITHUB_USERNAME:
    raise RuntimeError(
        "GITHUB_USERNAME was not found/loaded. Please check your .env file")
#Owner id
if BOT_OWNER_ID <= 0:
    raise RuntimeError(
        "BOT_OWNER_ID is missing or invalid. Please check your .env file.")
#Maintenance channel id
if MAINTENANCE_CHANNEL_ID <= 0:
    raise RuntimeError(
        "MAINTENANCE_CHANNEL_ID is missing or invalid. Please chack your .env file")
#Update_repo
if not UPDATE_REPOSITORY:
    raise RuntimeError(
        "UPDATE_REPOSITORY was not found/loaded. Please check your .env file")
#Update asset name prefix
if not UPDATE_ASSET_NAME_PREFIX:
    raise RuntimeError(
        "UPDATE_ASSET_NAME_PREFIX was not found/loaded. Please check your .env file")
#Version File
if not VERSION_FILE.exists():
    raise RuntimeError(
        "version.txt was not found in the project folder.")
#Installed version
if not read_installed_version().startswith("v"):
    raise RuntimeError(
        "version.txt must contain a version beginning with 'v', such as v0.1.0.")

#Connects the bot to Discord.
bot.run(DISCORD_TOKEN)