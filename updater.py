"""
A seperate .py. Used to update the code when needed or instructed.
Running this sript will shut down the main code "bot.py". Backs up the installation,
installs the new files, updates dependencies, and restarts the main bot script.
"""
#Imports
import argparse
from html import parser
from multiprocessing import process
import os
import shutil
import subprocess
import sys
import time
from unittest import result
from typing_extensions import runtime
import zipfile

from datetime import datetime
from pathlib import Path, PurePosixPath

#Creates the protected files
PROTECTED_NAMES = {
    ".env", ".venv", ".git", ".vs", "__pychache__", "release_state.json",
    "backups", "logs", "update_download"
    }

#Creates Logs
def write_log(project_folder, message):
    """
    Writer updater activity will be to console and updater log.
    """
    #Creates a timestamp for logs
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    #Formats the message for logging purpose
    formatted_message = (f"[{timestamp}] {message}")
    print(formatted_message)

    #Logs folder
    log_folder = project_folder / "logs"
    log_folder.mkdir( parent=True, exist_ok=True)
    #Log File
    log_file = log_folder / "updater.log"
    #Opens Log file and writes the formatted message for logging
    with log_file.open( "a", encoding="utf-8") as file:
        file.write(formatted_message + "\n")

#Checks if bot is still running
def process_is_running(process_id):
    """
    Checks if a process is still running/exists
    """
    if process_id <=0:
        return False

    #Checks
    try:
        #Signal 0 does not terminate the process.
        #Checks if process exists
        os.kill(process_id,0)
        return True
    #Error Lookup
    except ProcessLookupError:
        return False
    #Error Permission 
    except PermissionError:
        #Process exists, but process cannot signal it.
        return True
    #Error os
    except OSError:
        return False

#Parent_process
def wait_for_parent_process( process_id, project_folder, timeout_seconds=30):
    """
    Waits for bot.py to finish being shut down.
    """
    #Logs the waiting for shut down.
    write_log( project_folder, f"Waiting for bot process {process_id} to stop.")
    #Creates a timestamp
    start_time = time.time()

    #checks if the bot was shut down in time
    while process_is_running(process_id):
        if time.time() - start_time >= timeout_seconds:
            raise RuntimeError("The running bot did not shut down within expected time.")
        time.sleep(0.5)

    #Logs
    write_log(project_folder, "The bot has been stopped successfully for updating...")

    #Validates zip
    def validate_zip_archive(update_file):
        """
        Validates the ZIP pathing before extracting
        rejects:
        -Abolute paths
        -Parent-directory paths such as ../
        -Windows drive paths
        -Symbolic links
        """
        #Rejects if the file isn't a proper zip
        if not zipfile.is_zipfile(update_file):
            raise RuntimeError("The downloaded update is not a valid ZIP file.")
        #Valid zip process
        with zipfile.ZipFile(update_file, "r") as archive:
            if archive.testzip() is not None:
                raise RuntimeError("The update ZIP contains a damaged file.")
            #Checks the files and folders stored inside the zip with a loop
            for member in archive.infolist():
                #Converts the ZIP to POSIX-style pathing.
                member_path = PurePosixPath(member.filename)
                #Blocks absolute pathings; example: /etc/pass
                #This is to protect against malicious zips that may try to extract to outside the folder
                if member_path.is_absolute():
                    raise RuntimeError(f"Unsafe absolute path in Zip: "
                                       f"{member.filename}")
                """
                Blocks parent-directory traversal such as 
                ../bot.py
                ../../other folder/file.txt
                This is to prevent from updating or overwritting outside the intended directory
                """
                if ".." in member_path.parts:
                    raise RuntimeError(f"Unsafe parent path in ZIP: {member.filename}")
                #Rejects the pathing resembling the c drive; C:/folder/file
                if (member_path.parts and ":" in member_path.parts[0]):
                    raise RuntimeError(f"Unsafe drive path in ZIP: {member.filename}")
                #Check the Unix file-type bits stored in the ZIP
                unix_mode = member.external_attr >> 16
                file_type = unix_mode & 0o170000
                #0o120000 represents a symbolic link.
                if file_type == 0o120000:
                    raise RuntimeError( f"Symbolic links are not allowed: {member.filename}")

    #Defines the extraction of the update file
    def extract_update(update_file, staging_folder, project_folder):
        """
        Extracts validated update into a temp staging folder.
        """
        if staging_folder.exists():
            shutil.rmtree(staging_folder)
        staging_folder.mkdir(parents=True, exist_ok=True)
        #Calls to validate the file
        validate_zip_archive(update_file)

        #Logs The extraction of update files
        write_log(project_folder, f"Extracting update into {staging_folder}.")

        #Archives the files into the staging folder
        with zipfile.ZipFile(update_file, "r") as archive:
            archive.extractall(staging_folder)

    #Update Root
    def locate_update_root(staging_folder):
        """
        Locates the folder conating the actual update folder
        Supports both: files from inside the zip or one containing folder inside the zip
        """
        required_file = staging_folder / "bot.py"
        if required_file.exists():
            return staging_folder
        contents = list(staging_folder.iterdir())
        #Creates the directories list loop
        directories = [ item for item in contents if item.is_dir()]
        #Creates the file list loop
        files = [ item for item in contents if item.is_file()]
        #Finds possible root
        if len(directories) == 1 and not files:
            possible_root = directories[0]
            if(possible_root / "bot.py").exists():
                return possible_root
        #Gives an error when bot.py doesn't exists
        raise RuntimeError("The update ZIP does not contain bot.py in the expected location.")

    #Defines function of validation update
    def validate_update_contents(update_root, new_version):
        #Confirms that release contains all required files
        #Points out what files are required
        required_files = { "bot.py", "updater.py", "requirements.txt", "version.txt"}
        #Makes a list of missing files
        missing_files = []
        
        #If there is missing files, add it to the list
        for filename in required_files:
            if not (update_root / filename).is_file():
                missing_files.append(filename)
        #Gives an error if there are missing files
        if missing_files:
            raise RuntimeError( "The update is missing required files: "
                               + ", ".join(missing_files))
        
        #Sets up a check of packaged version of update
        packaged_version = ( update_root / "version.txt").read_text(encoding="utf-8").strip()
        #Checks if the package matches the GitHub release.
        if packaged_version != new_version:
            raise RuntimeError( "The update version does not match its GitHub release tag."
                               f"Expected {new_version}, but version.txt contains {packaged_version}.")

    #Protects top-level
    def should_protect(path):
        #Returns True when a top-level project item must be preserved
        if path.name in PROTECTED_NAMES:
            return True
        if path.suffix.lower() == ".zip":
            return True
        return False

    #Creates a backup
    def create_backup(project_folder, old_version):
        #Copies the current program files into a timestamped backup.
        #Creates a safe_version
        safe_version = old_version.replace("/", "_")
        #Timestamps backup
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        #Creates backup folder
        backup_folder = (project_folder / "backups" / f"{safe_version}-{timestamp}")
        #Backup folder
        backup_folder.mkdir(parents=True, exist_ok=False)

        #Writes a log for creating a backup folder
        write_log(project_folder, f"Creating backup at {backup_folder}.")

        #Cycles through files
        for item in project_folder.iterdir():
            #Skips protected files
            if should_protect(item):
                continue
            destination = backup_folder / item.name
            #This is folders
            if item.is_dir():
                shutil.copytree(item, destination)
            #normal files
            else:
                shutil.copy2(item, destination)
        #Returns the completed backup folder
        return backup_folder

    #Will remove the current installment of exe
    def remove_current_program_files(project_folder):
        """
        Will remove the application and it's files while preserving the configuration,
        the environment, Git info, the logs, and backups.
        """
        #Loops through folder
        for item in project_folder.iterdir():
            #If the item is a protect folder, if so skip it
            if should_protect(item):
                continue
            #If the item is a folder, delete it
            if item.is_dir():
                shutil.rmtree(item)
            #It the item is a file, delete it
            else:
                item.unlink()

     #Will copy the new update files into the project folder
    def copy_update_files(update_root, project_folder):
         #Creates a log for the update
         write_log(project_folder, "Installing new application files.")
         #Loops through the update folder
         for item in update_root.iterdir():
            #if the file/folder is protected
            if should_protect(item):
                #Skips it
                continue
            #Sets up the destination for the update
            destination = project_folder / item.name
            #Checks if an older version exists, if so delete it
            if destination.exists():
                #If it's a folder
                if destination.is_dir():
                    shutil.rmtree(destination)
                #If it's a normal file
                else:
                    destination.unlink()

            #Checks if the new update is a folder
            if item.is_dir():
                #Copies the update folder into the project fodler
                shutil.copytree(item, destination)
            #if the update is a normal file
            else:
                shutil.copy2(item, destination)
    #Creates the restore backup process
    def restore_backup(project_folder, backup_folder):
         #Can be used to restore from backup after a failed update
        
         #Creates a log for restoring backup
         write_log(project_folder, f"Restoring backup from {backup_folder}.")

         #Removes the current file
         remove_current_program_files(project_folder)

         #Loops through the backup folder
         for item in backup_folder.iterdir():
            #Sets up destination
            destination = project_folder / item.name
            #If folder
            if item.is_dir():
                shutil.copytree( item, destination)
            #If file
            else:
                shutil.copy2(item, destination)

    #Installs the requirements for the code
    def install_requirements(project_folder):
        #Install the Python packages using the interpreter.
        #Sets up the requirement file
        requirements_file = (project_folder / "requirements.txt")

        #Logs the installation of Python requirments
        write_log( project_folder, "Installing Python requirements.")

        #Creates a pip in a seperate process to update and install packages from requirements.txt
        """
        sys.executable uses same python interpreter, "-m" & "pip" uses the Python pip module,
        "install" tells the pip to install the packages, "-r" will point at the names stored in requirments file,
        str(requirments_file) will convert the Path object into a normal string path, cwd will run the command inside the bot's
        folder, capture_output is used to save the commands normal output and error outputs, text will return
        stdout and stderr as a normal string instead of bytes, timeout will stop if pip takes longer than 300 seconds.
        """
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements_file),]
                                , cwd=project_folder, capture_output = True, text = True, timeout = 300 )
        #if pip is functionning normal with expected output, saves the output to the log
        if result.stdout:
            #Logs the normal update
            write_log( project_folder, result.stdout.strip())
        #Side note, a return code of 0 means a successful update
        #Anyelse is a failed update, hence the error catach
        if result.returncode != 0:
            #Attempts to collect the error message generated by pip; includes a fallback
            error_output = (result.stderr.strip() or "Unknown pip error.")
            #Logs the failure
            write_log( project_folder, f"Installing requirments have failed: {error_output}")

            #Stops the update and reports the failure
            raise RuntimeError( "Installing requirements failed: "
                               f"{error_output}")

    #Defines the restart function
    def restart_bot(project_folder):
        """
        Will be used to start bot.py by using the same environment already in use.
        Use this after update to restart bot, should be automatic. 
        Set to the project folder so keep the bot.py there
        """
        #Sets the path for the bot.py location
        bot_file = project_folder / "bot.py"
        #Creates a log for restarting the bot
        write_log(project_folder, "Restarting Discord bot.")
        
        #Builds the command for restarting bot.
        #sys.executable points at current python interpreter as it uses .venv and the installed packages
        process_arguments = [ sys.executable, str(bot_file) ]

        #Stores the additional settings to be passed into the subprocess
        #cwd is set to directory to the bot's project folder to ensure use of .env and version.txt in the folder.
        process_options = { "cwd" : project_folder }

        #If the os is a windows (nt)
        if os.name == "nt":
            #Will start the bot in a new window process group as to allow the updater.py to finish and still run the bot.py
            process_options[ "creationflags" ] = ( subprocess.CREATE_NEW_PROCESS_GROUP)
            #logs the use of Windows environment
            write_log ( project_folder , "Using the Window process settings.")
        #Else use the linux os.
        else:
            #Linux will include Raspberry Pi OS, will start_new_session and detaches bot into own process
            #This is to prevents the bot from terminated when updater.py stops 
            process_options[ "start_new_sesstion" ] = True
            #Logs the use of Linux environment
            write_log (project_folder , "USing the Linux process settings.")

        #Will restart the bot.py in a new process.
        #Popen() will start the process without waiting for updater.py to finish. 
        #Reason is that the bot is expected to run continuously so it needs to quickly be up and running
        subprocess.Popen( process_arguments, **process_options)

    #Defines the clean up function
    def clean_download_files(update_file, staging_folder, project_folder):
        """
        Used to delete/remove the temp files downloaded for updating the program.
        Once the zip file is unloaded into the temp folder and then update is applied, this
        function will delete these to keep storage.
        Includes logging to inform if files have been removed or not
        """
        #Tracks if each steps of the cleanup was successful; set to True by default
        staging_deleted = True
        update_file_deleted = True

        #Attempts to remove the temp staging folder
        if staging_folder.exists():
            #Deletes
            try:
                shutil.rmtree(staging_folder)
            #IF it fails to delete
            except OSError as error:
                #Sets staging check to false
                staging_deleted = False
                #logs failure
                write_log(project_folder, f"Failed to delete staging folder: {error}")

        #Attempts to delete the downloaded ZIP
        if update_file.exists():
            #Deletes
            try:
                update_file.unlink()
            #Fails to delete the zip
            except OSError as error:
                update_file_deleted = False
                #Logs the failure
                write_log(project_folder, f"Failed to delete the ZIP folder: {error}")

        #Logs success of both
        if staging_deleted and update_file_deleted:
            write_log(project_folder, "Update cleanup was successfull. All files removed.")
        #If one or both failed, logs it
        else:
            write_log(project_folder, "Update cleanup was unsuccessfull, see logs for more information.")
    
    #Defines the parse argument for the command line
    def parse_arguments():
        """
        Will read the command-line value passed into the updater.py
        bot.py will start updater.py as seperate process and will send info regarding the update
        through a command-line.
        """
        #Creates a argument parser
        parser = argparse.ArgumentParser( description = "Install a Discord bot update.")
        #Sets the path to the ZIP that is pulled from GitHub
        #required must be True, otherwise the updater.py will refuse to start if not passed
        parser.add_argument( "--update-file", required = True, help = "Path to the downloaded GitHub release ZIP." )
        #sets the path for the bots folder to be installed into.
        #Used to create backups, replace old files, find the requirements.txt, and restarts the bot.py
        parser.add.argument( "--project-folder", required = True, help = "Path to the bot's project folder.")

        #Pulls the naming of current installation to use as naming for backup
        parser.add_argument( "--old-version" , required= True, help = "Version currently installed before the update.")

        #Pulls the version install name from GitHub release
        parser.add_argument ("--new-version ", required = True, help="Version being installed from GitHub.")

        #Pulls the id for the discord bot
        #Does this as a seperate process to ensure that updater.py will wait before replacing files while bot.py
        #is still running.
        parser.add_argument("--parent-pid", required=True, type = int,help = "Process ID of the running Discord bot.")

        #REads the supplied command-line arguments and return them
        #Allowed access-
        # arguments.update_file
        # arguments.project_folder
        # arguments.old_version
        # arguments.new_version
        # arguments.parent_pid
        return parser.parse_args()
    #Defines the main body code
    def main():
        """
        Runs through all the update process.
        Will receive information passed by the bot.py, waits for the bot to properly shut down, 
        will stage the downloaded update, back up current installation, install new files, update the
        requirements, then restarts bot.
        If update fails, automatically reverts to the backup file and restarts while informing of a failed update.
        0 on success, 1 on failure.
        """
        #Reads the command-line
        arguments = parse_arguments()
        #Creates a resolved Path for updater to use to access project_folder
        project_folder = Path(arguments.project_folder).resolve()
        #Converts the downloaded update ZIP path into a resolved path as well
        update_file = Path(arguments.update_file).resolve()
        #Converts the staging file Path for the ZIP into a resolved Path
        staging_folder = (project_folder / "update_download" / "staging")
        #No backup folder will be assigned on start, once the function create_backup() is called,
        #it will assign the backup folder

        #Begins the update process
        try:
            #Logs the update starting.
            write_log(project_folder, (f"Starting update from "
                                       f"{arguments.old_version} "
                                       f"to {arguments.new_version}."))
            #Waits for the bot.py to stop completely
            wait_for_parent_process( arguments.parent_pid, project_folder)
            #Validates the ZIP and moves to staging folder
            extract_update(update_file, staging_folder, project_folder)
            #Locates the update files and folders sithin the ZIP
            update_root = locate_update_root(staging_folder)
            #Validates the release holds the required files and validates the version.txt.
            validate_update_contents(update_root, arguments.new_version)
            #Creates the backup
            backup_folder = create_backup(project_folder, arguments.old_version)
            #Removes old replaceable files
            remove_current_program_files(project_folder)
            #Copies the new application files from the staging folder into project folder
            copy_update_files(update_root, project_folder)
            #Installs new or updated requirments
            install_requirements(project_folder)
            #If program reaches this point, logs the files and requirements were installed
            write_log(project_folder,( "Update completed successfully. "
                                     f"Installed {arguments.new_version}."))
            #Cleans up temp files
            clean_download_files(update_file, staging_folder, project_folder)
            #Restarts the bot
            restart_bot(project_folder)
            #Returns 0 for success
            return 0
        #Exception for the try
        #Happens if any step above fails
        except Exception as error:
            #Logs the error from the update process. It catches the error built in the methods
            write_log( project_folder, f"Update failed: {error}")
            #Should automatically perform a roll back if a backup was successful 
            if (backup_folder is not None and backup_folder.exists()):
                #Attempts the rollback
                try:
                    #Removes the failed files and overwrites with working files
                    restore_backup(project_folder, backup_folder)
                    #Logs the backup was restored
                    write_log(project_folder, "The previous version was restored.")
                #Cataches error
                except Exception as rollback_error:
                    #IF the rollback fails, record it as manual recovery will be needed
                    write_log( project_folder, ("Automatic rollback failed: "
                                                f"{rollback_error}"))
            #Cleans up downloaded files even if failed
            clean_download_files(update_file, staging_folder, project_folder)
            #Attempts to restart bot
            try:
                restart_bot(project_folder)
            #Catches restart error
            except Exception as restart_error:
                #Logs the restart failure seperately because something went completely wrong
                write_log(project_folder, ("The bot could not be restarted: "
                                           f"{restart_error}"))
            #Returns 1 for failure.
            return 1

#Main body call
if __name__ == "__main__":
    raise SystemExit(main())