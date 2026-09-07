#Caleb McManus
#Discord Bot for interacting with a dedicated github server to post update notifications
#of GitHub repo updates.
from encodings import aliases
import os
import subprocess
from tabnanny import check
import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pathlib import Path
import asyncio
import sys
import hashlib
import atexit

#Pathing settings
#Path to the folder containg bot.py
PROJECT_FOLDER = Path(__file__).resolve().parent
#Path to the file that stores the installed bot version txt
VERSION_FILE = PROJECT_FOLDER/ "version.txt"
#Path to the updater
UPDATER_FILE = PROJECT_FOLDER / "updater.py"
#Path to the temp store downloaded updates
UPDATE_DOWNLOAD_FOLDER = PROJECT_FOLDER / "update_download"
#emp name for the downloaded zip update
UPDATE_ZIP_FILE = UPDATE_DOWNLOAD_FOLDER / "bot_update.zip"
#Path used to prevent multiple bot instances from running
LOCK_FILE = PROJECT_FOLDER / "bot.lock"
#Marker file for successful update
UPDATE_SUCCESS_FILE = PROJECT_FOLDER / "update_success.txt"

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

#Keeps only one bot running
def process_is_running(process_id):
    """
    Purpose is to check if only a process is still running.
    Uses tasklist on Windows and os.kill on Linux
    """

    if process_id <= 0:
        return False
    #If Windows
    if os.name == "nt":
        try:
            result = subprocess.run([
                "tasklist", "/FI", f"PID eq {process_id}", "/NH"], 
                                    capture_output = True, text = True, timeout = 5)
            output = result.stdout.strip()
            if not output:
                return False
            if "No tasks are running" in output:
                return False
            return str(process_id) in output
        #Catches exceptions
        except( subprocess.SubprocessError, OSError):
            return False
    #Linux/Raspberry Pi process check
    try:
        os.kill(process_id, 0)
        return True
    #Exceptions
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

#Creates a lock to keep only one bot
def create_instance_lock():
    """
    This is to prevent multiple copies of the bot from running
    Locks file contains the PID of current running bot
    Replaces if the bot is no longer running, but keeps new bots from running 
    """
    current_pid = os.getpid()

    #checks whether a previous lock file exists
    if LOCK_FILE.exists():
        try:
            #Has to get it in form of string before int
            existing_pid_text = LOCK_FILE.read_text(encoding="utf-8").strip()
            #changes it to int for comparison
            existing_pid = int(existing_pid_text)
        #Exceptions
        except(OSError, ValueError):
            #Invalid lock files are stale
            existing_pid = 0
        #If the previous PID is still running, another bot instance isalready active
        if process_is_running(existing_pid):
            raise RuntimeError(f"Another instance of the Discord Bot is running with PID {existing_pid}.")

    #Saves the current bot PID
    LOCK_FILE.write_text(str(current_pid), encoding="utf-8")

#Removes instance
def remove_instance_lock():
    if not LOCK_FILE.exists():
        return
    try:
        lock_pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
        if lock_pid == os.getpid():
            LOCK_FILE.unlink()
    #Catches exceptions
    except(OSError, ValueError):
        pass

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

#startup notification check
startup_notification_sent = False

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

#Defines the method to find the correct ZIP file for update
def find_update_asset(release_information):
    """
    Finds the correct ZIP from GitHub
    Release tag example: v0.1.0
    Zip file name expected is: GitHubDiscordBot-v0.1.0.zip
    UPDATE_ASSET_NAME_PREFIX already has: GitHubDiscordBot-v
    """
    #Gets the releae tag
    release_version = release_information.get(
        "tag_name","" ).strip()
    #Stops if the GITHUB doesn't have the tag
    if not release_version:
        raise RuntimeError("The GitHub release doesn't have a tag for version.")

    #Removes the v from the version tag
    version_number = release_version.removeprefix("v")
    #Builds the expected ZIP name
    expected_asset_name = (f"{UPDATE_ASSET_NAME_PREFIX}"
                           f"{version_number}.zip")
    #Gets the list of files attached to the GitHub release
    release_assets = release_information.get("assets",[])
    #Looks through release asset
    for asset in release_assets:
        #Returns the asset if its filename matches
        if asset.get("name") == expected_asset_name:
            return asset
    #If loop doesn't find a zip, it'll stop the update and report
    raise RuntimeError("The required update ZIP was not found."
                       f"Expected: {expected_asset_name}")

#Handles the downloading of the zip file
async def download_update_asset(asset_information):
    """
    Downloads the GitHub releaseZip into the temporary update_folder
    REturns PAth to the downloaded ZIP file
    """
    #Gets the download url from release asset
    download_url = asset_information.get("browser_download_url","")
    #Fails to pull url
    if not download_url:
        raise RuntimeError("GitHub release asset has no download URL.")
    #Creates the temp update folder
    UPDATE_DOWNLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    headers = {"Accept": "application/octet-stream", "User-Agent": "Discord-GitHubRepoBot"}

    #Attempts the connection and download
    try:
        #Opens a connection to GitHub
        async with aiohttp.ClientSession(headers=headers) as session:
            #Downloads the zip
            async with session.get(download_url) as response:
                #If the response fails
                if response.status != 200:
                    raise RuntimeError("GitHub could not download the update. "
                                       f"HTTP status: {response.status}")
                #IF successful reads the download into memory
                update_data = await response.read()
    #CAtaches the errors for attempting the connection and download
    except aiohttp.ClientError as error:
        raise RuntimeError( f"Could not download the update: {error}")

    #GitHub saves thenexpected file sizes
    expected_size = asset_information.get("size")
    #Compares the sizes
    #IF it's not the same
    if(isinstance(expected_size, int) and len(update_data) != expected_size):
        raise RuntimeError("Downloaded update size does not match the GitHub release asset.")
    #Saves the downloaded ZIP.
    UPDATE_ZIP_FILE.write_bytes(update_data)
    #Returns the downlaoded Zipfile
    return UPDATE_ZIP_FILE

# Verifies the update
def verify_update_checksum(update_file, asset_information):
    """
    Will verify the downloaded update using GitHub's SHA-256 digest when GitHub provides one
    Helps make sure the zip was not corrupted or changed during the download.
    """
    github_digest = asset_information.get("digest")
    #Release asset may not have a digest, if that is case the size check is still used
    if not github_digest:
        return True
    #Only supports the SHA-256 digests; catches a error if it's not
    if not github_digest.startswith("sha256:"):
        raise RuntimeError("GitHub returned an unsupported checksum format.")
    #Will remove the "sha256:" so only checksum remains
    expected_checksum = github_digest.removeprefix("sha256:")
    #Calculates our own SHA-256 checksum for the zip
    calculated_checksum = hashlib.sha256(update_file.read_bytes()).hexdigest()
    #Compare our checksum against GitHub's
    if calculated_checksum != expected_checksum:
        raise RuntimeError("Downloaded update failed SHA-256 verification.")
    return True

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

    #Gets the startup notification boolean
    global startup_notification_sent
    #Saves the installed version
    installed_version = read_installed_version()
    #Loads info into terminal
    print ("--------------------------")
    print (f"Connected as: {bot.user}")  #UserName
    print (f"Bot ID: {bot.user.id}")     #UserID
    print (f"Version: {installed_version}") #Installed version
    print ("--------------------------")
    #Stops notification logic if process is already started
    if startup_notification_sent:
        return
    #Sets up maintenance channel 
    maintenance_channel = bot.get_channel(MAINTENANCE_CHANNEL_ID)
    #Checks if there is a maintenance channel id
    if maintenance_channel is None:
        print("Maintenance channel could not be found.")
        return
    #Checks if the bot had started after a successful update
    if UPDATE_SUCCESS_FILE.exists():
        #Attempts to send update successful
        try:
            updated_version = UPDATE_SUCCESS_FILE.read_text(encoding="utf-8").strip()
            await maintenance_channel.send("**Update completed successfully.**\n"
                                           f"Bot is now running `{updated_version}`.")
            #Deletes the marker as to not repeate
            UPDATE_SUCCESS_FILE.unlink()
        #Exception catch
        except OSError as error:
            print(f"Failed to read update success marker: {error}")
    #Typically used in case of a restart
    else:
        await maintenance_channel.send("**Bot connected successfully.**\n"
                                       f"Running version: `{installed_version}`")
    #MArks the startup notification as completed
    startup_notification_sent = True

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
                "Use `!update` to install it.")
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

#Handles the update command
@bot.command()
@maintenance_command()
async def update(context):
    """
    Downloads and installs the newest GitHub release...
    """
    await context.send("Checking GitHub for an available update...")

    #Attempts to update
    try:
        #Gets the latest pubished GitHub Release.
        latest_release = await get_latest_bot_release()
        #Get's the current installed version
        installed_version = read_installed_version()
        #Get's the version tag from GitHub release page
        latest_version = latest_release.get("tag_name","").strip()
        #Gives an error message if tag isn't right or there
        if not latest_version:
            raise RuntimeError("Latest release has no version tag.")
        #converts both version files to something comparable.
        installed_numbers = convert_version_to_numbers(installed_version)
        latest_numbers = convert_version_to_numbers(latest_version)

        #Stops if installed is current or newer.
        if latest_numbers <= installed_numbers:
            await context.send("No newer update is available.\n\n"
                               f"Installed: `{installed_version}`\n"
                               f"Latest: `{latest_version}`")
            return
        #Find the matching ZIP asset
        update_asset = find_update_asset(latest_release)
        await context.send(f"Downloading `{update_asset['name']}`...")

        #Downloads the update Zip
        downloaded_file = await download_update_asset(update_asset)

        #verify the download file checksum
        verify_update_checksum(downloaded_file, update_asset)

        #Verifies that updater.py exists
        if not UPDATER_FILE.exists():
            raise RuntimeError("Updater.py was not found.")
        await context.send(f"Updating from `{installed_version}` "
                           f"to `{latest_version}`. \n"
                           "The bot will disconnect and restart.")

        #Sets options used when updater starts
        #This keeps updater running superate from the bot
        updater_process_options = {"cwd" : PROJECT_FOLDER}

        #If it's a window os
        if os.name == "nt":
            updater_process_options["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP)
        #If it's a linux/ Raspberry system
        else:
            updater_process_options["start_new_session"] = True

        #Starts updater.py as a seperate process
        #Uses command-line arguments to pass all update information.
        subprocess.Popen([
            #Uses the same python interpreter already running
            sys.executable,
            #Path to updater.py
            str(UPDATER_FILE),
            #Path to downloaded zip
            "--update-file", str(downloaded_file),
            #Path to bot project folder
            "--project-folder", str(PROJECT_FOLDER),
            #Version installed
            "--old-version", installed_version,
            #Version being installed
            "--new-version", latest_version,
            #Process id of current bot
            "--parent-pid", str(os.getpid())
            ], **updater_process_options)

        #Gives Discord time to send update message
        await asyncio.sleep(2)
        #Shuts down the bot to replace files
        await bot.close()

    #Error cataches for update process
    except RuntimeError as error:
        await context.send(f"Update failed: {error}")

#Handles the errors for !update
@update.error
async def update_error(context, error):
    if isinstance(error, commands.CheckFailure):
        await context.send( "Command can only be used by the bot owner inside maintenance channel.")
        return
    raise error

#Stop command; immediately disconnects the bot from discord and ends program
@bot.command(name="stop", aliases=["end"])
@maintenance_command()
async def stop(context):
    #Let discord know shutdown command was accepted
    await context.send("Stopping bot and disconnecting...")
    #Gives Discord a moment to send the message
    await asyncio.sleep(1)
    #Closes the Discord connection
    await bot.close()
#Handles the errors for !stop command
@stop.error
async def stop_error(context, error):
    if isinstance(error, commands.CheckFailure):
        await context.send("Command can only be used by the owner inside the"
                           "maintenance channel.")
        return
    raise error

#Restart bot command
@bot.command()
@maintenance_command()
async def restart(context):
    """
    Restarts the current bot
    """
    await context.send("Restarting bot...")
    #Gives Discord time to send message
    await asyncio.sleep(1)
    #settings for new bot process
    restart_process_options = {"cwd" : PROJECT_FOLDER}
    #Windows setting
    if os.name == "nt":
        restart_process_options["creationflags"] = ( subprocess.CREATE_NEW_PROCESS_GROUP)
    #Linux
    else:
        restart_process_options["start_new_session"] = True
    #Removes current instance lock for replacement
    remove_instance_lock()
    #Starts a new copy using same python interpreter
    subprocess.Popen([
        sys.executable, str(PROJECT_FOLDER / "bot.py")
        ], **restart_process_options)
    #Disconnects and shuts down
    await bot.close()
#Handles the restart command errors
@restart.error
async def restart_error(context, error):
    if isinstance(error, commands.CheckFailure):
        await context.send( "Command can only be used by the bot owner inside the maintenance channel.")
        return
    raise error

###=======================================
###Start
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

#Prevents multiple copies from starting
create_instance_lock()
#Remove the lock when Python exits normally.
atexit.register(remove_instance_lock)
#Connects the bot to Discord.
bot.run(DISCORD_TOKEN)