"""
This module implements the DeviceManager class which is used to manage control of a Cisco Device in the SmartRack system
"""

# Import System Libraries
import os
import logging
import logging.handlers
import re
import pyparsing
import multiprocessing
from typing import Any
from enum import Enum
from ctypes import c_char

# Import SmartRackLibrary modules
from .configuration import Configuration
from .ciscodevice import CiscoDevice

BACKUP_BUFFER_SIZE = 16384
# TODO: Add backup() and restore() actions


class DeviceActionCompleteEnum(Enum):
    """
    The DeviceActionCompleteEnum class implements an enumeration of device action completion states. Used to identify the specific state
    of an action that has concluded.

    :ivar CONNECTED: Indicates that the device connection process has completed.
    :ivar ENABLE: Indicates that the device has been successfully entered into enable mode, and is ready to accept commands.
    :ivar COLLECTED: Indicates that the data collection from the device is complete.
    :ivar EXTRACOLLECTED: Indicates that the collections of extra commands is complete.
    :ivar BACKUP: Indicates that backing up the configuration for the device is complete.
    :ivar RESTORE: Indicates that restoring a configuration to the device is complete.
    :ivar RESTARTED: Indicates that the device has been successfully restarted.
    :ivar ERASED: Indicates that the data erasure process on the device has concluded.
    :ivar FINISHED: Indicates that all actions on the device have concluded.
    """
    CONNECTED = 'Connected devices'
    ENABLE = 'Devices in "enable" mode'
    COLLECTED = 'Completed data collections'
    EXTRACOLLECTED = 'Completed collecting extra commands'
    BACKUP = 'Devices backed-up'
    RESTORE = 'Devices with restored configurations'
    RESTARTED = 'Restarted devices'
    ERASED = 'Device with deleted configurations'
    FINISHED = 'Devices with all actions complete'


class DeviceManager(multiprocessing.Process):
    """
    Manages control of a Cisco device within the SmartRack system, can be used to collect, configure, or reset devices automatically.

    All Cisco Devices are managed a subprocess within the multiprocess system. This allows multiple devices to be managed in parallel. Once the instance
    is instantiated, a series of tasks to be completed can be registered prior to the process being executed. Allowed tasks include:
     - collect: Collect output of a series of commands and store to a file in a common directory
     - erase: Delete all configurations on the device
     - restart: Reload the device
    """
    def __init__(self, device: CiscoDevice, device_type: str, description: str, full_description: str, update_queue: multiprocessing.Queue, log_queue: multiprocessing.Queue, usernames: list[str] = None, passwords: list[str] = None):
        """
        Initializes an instance of the DeviceManager class, which manages a Cisco device connection and device-specific functionalities.

        This class also handles initialization of logging and update queues for asynchronous operations.

        :param device: CiscoDevice object that represents the device to be managed.
        :param device_type: The type of the device being managed. Must be a valid type as defined in the Configuration class.
        :param description: A short description of the DeviceManager instance, will be used to describe the device when updating progress and logging.
            Default is generated based on class identity if not explicitly provided.
        :param full_description: A detailed description for the DeviceManager instance. Defaults to the same as the short description if not explicitly provided.
        :param update_queue: A multiprocessing Queue to return progress updates to the main process.
        :param log_queue: A multiprocessing Queue for passing log messages handled by the logging system.

        :raises ValueError: Raised if the provided device_type is not supported as defined in the Configuration class.
        """
        super().__init__()
        self.description = description or 'DeviceManager(' + ':'.join(str(i) for i in self._identity) + ')'
        self.full_description = full_description or self.description

        # Store multiprocessing queue variables
        self.__update_queue: multiprocessing.Queue = update_queue
        self.__log_queue: multiprocessing.Queue = log_queue

        # Validate parameters
        if device_type not in Configuration().manage:
            raise ValueError(f'DeviceManager: type {device_type} is not supported')

        # Store device connection, device type, and all commands related to managing this device type
        self.__device = device
        self.__type = device_type
        self.__manage: dict[str, list[str]] = Configuration().manage[device_type]
        self.__actions: dict[str, Any] = {}
        self.__usernames = usernames
        self.__passwords = passwords

        # Create shared variable so parent process can know of successful completion
        self.__complete = multiprocessing.Value('b', False)

        # Create shared variable to store backed-up configuration so parent process can access (initialised with zeroes)
        self.__config = multiprocessing.Array(c_char, BACKUP_BUFFER_SIZE, lock=True)

        # Establish logger for DeviceManager class - has to be done last as otherwise calling Configure() will delete the queue log handler
        self.__log = logging.getLogger('DeviceManager')
        self.__log.addHandler(logging.handlers.QueueHandler(log_queue))
        self.__log.debug(f'Constructing Class')

    ##########
    # PRIVATE METHODS
    ##########
    def _send_commands(self, command_list: list[str]) -> None:
        """
        Sends a list of commands to the connected device and logs each command sent.

        This method iterates through a list of commands to send to the Cisco Device, allows a single call to issue multiple commands.

        :param command_list: The list of commands to execute on the device.
        """
        for command in command_list:
            self.__log.info(f'({self.description}) Sending command "{command}"')
            self.__device.send_command(command)

    def _establish_connection(self) -> None:
        """
        Establishes a connection with the device and configures it to the enable mode.

        This method manages all the initialisation and must be called prior to running any of the following methods.
        """
        self.__log.info(f'({self.description}) Establishing connection to {self.__type}')
        self.__device.connect()
        self.__log.info(f'({self.description}) Setting device to enable mode')
        self.__device.set_enable_mode([], [])

    @staticmethod
    def _sh_vlan_brief_to_commands(sh_vlan_brief: str) -> str:
        """
        VLAN creation and names are not stored in the output of "show run" on a Cisco Switch. We need to extract the VLAN information from the output of
        "show vlan brief" and convert it into a series of commands that will create the required programming commands.

        :param sh_vlan_brief: Captured "show vlan brief" output as a string
        :return: String containing the modified configuration that can be re-uploaded.
        """
        # pyparser class to handle an integer and convert to an int type
        int_parser = pyparsing.Word(pyparsing.nums)
        int_parser.setParseAction(lambda x: int(x[0]))

        # pyparser class to handle a label/name
        name_parser = pyparsing.Word(pyparsing.printables)

        # Parser to ignore the rest of line (or whole line)
        ignore_text = pyparsing.Suppress(pyparsing.restOfLine + pyparsing.lineEnd())

        # A VLAN match is any line that begins with an integer, followed by a parser name, then text to ignore
        vlan_line = pyparsing.LineStart() + int_parser('vlan_id') + name_parser('vlan_name') + ignore_text

        # We parse the sh vlan brief output by matching either vlan_line or ignore_text
        vlan_parser = vlan_line | ignore_text

        # Create list of all dictionaries matched in captured output. If a line does NOT contain VLAN information, the list entry will be an empty dictionary.
        parsed_output = [vlan_parser.parse_string(line).as_dict() for line in sh_vlan_brief.splitlines()]

        return '\n'.join([configs for vlan in parsed_output
                          if len(vlan) > 0 and vlan['vlan_id'] > 1 and (vlan['vlan_id'] < 1002 or vlan['vlan_id'] > 1005)
                          for configs in (f'vlan {vlan['vlan_id']}', f'name {vlan['vlan_name']}')
                          ]) + '\n'

    @staticmethod
    def _insert_no_shutdowns(sh_run: str) -> str:
        """
        Take a captured "show run" output and convert it into a configuration that can be re-uploaded. We need to do this as the "show run" output only shows
        "shutdown" interfaces, whereas if the device has everything shutdown by default, uploading captured text will not enable the interface. Inserting a
        "no shutdown" before any relevant "shutdown" statement will result in a proper upload.

        1) Delete all text before the first "!" in the captured output.
        2) Insert "no shutdown" at start of each interface definition block
        3) Remove last line of capture which contains the router prompt

        :param sh_run: Captured "show run" output as a string
        :return: String containing the modified configuration that can be re-uploaded.
        """
        # Find the first '!' in the captured show_run, everything before this is not a configuration item
        start_config = sh_run.index('!')
        # Find the last 'end' beginning at the start of a line, this line (end) is not part of the configuration but the command to exit config mode
        end_config = sh_run.rindex('\nend') + 1

        # Regular expression to find all lines in multi-line string that begin with the text "interface "
        regex = re.compile('^interface .*$', re.MULTILINE)

        # Use regular expression to insert " no shutdown" after all matches in the text starting with the first "!" up to and including the last line of the actual config
#        return regex.sub(r'\g<0>\n' + ' no shutdown', re.sub(r'^!', '', sh_run[find_start_config.start() - 1:])).rsplit('\n', 1)[0]
        # Use regular expression to insert " no shutdown" after all matches in the text starting and ending with start_config->end_config
        return regex.sub(r'\g<0>\n' + ' no shutdown', re.sub(r'^!', '', sh_run[start_config:end_config]))

    ##########
    # PUBLIC METHODS
    ##########
    @property
    def process_complete(self) -> bool:
        """
        Returns True if the process has completed as stored in the multiprocess shared variable self.__complete.

        :return: Boolean representation of number stored in self.__complete.
        """
        return bool(self.__complete.value)

    def register_action(self, action: str, *args, **kwargs) -> None:
        """
        Registers an action with its corresponding method and arguments into the internal actions registry.
        When the process is running, and after the connection is established in enable mode, all registered methods
        will be executed in turn with the parameters provided here.

        Currently allowed actions are:
         - register_action('collect', out_dir='/file/storage/directory')
         - register_action('extra_collect', command_list=['command 1', 'command 2', ...]
         - register_action('erase')
         - register_action('restart')

        :param action: The name of the method in the class to be registered.
        :param args: Positional arguments required by the action method.
        :param kwargs: Keyword arguments required by the action method.
        """
        self.__log.info(f'({self.description}) Registering action: {action}(args={args}, kwargs={kwargs})')
        self.__actions[action] = {'method': getattr(self, action), 'args': args, 'kwargs': kwargs}

    def collect(self, out_dir: str = '.') -> None:
        """
        Collects configurations from the device by executing pre-defined commands and saving the output into specified files within the given output directory.

        NOTE: This method should not be called directly, it should be registered as an action using the register_action method.

        :param out_dir: The directory where configuration command outputs will be saved. If the directory does not exist, it will be created. Defaults to the current directory.
        """
        self.__log.info(f'({self.description}) Collecting configurations')

        self.__log.debug(f'({self.description}) Creating output directory {out_dir}')
        os.makedirs(out_dir, exist_ok=True)

        for command in self.__manage['collect']:
            self.__log.info(f'({self.description}) Collecting output of command "{command}"')
            filename = command.replace(' ', '_').replace('/', '_').replace('|', '-')
            with open(os.path.join(out_dir, filename), 'w') as file:
                file.write(self.__device.capture_command(command, strip_excess_bangs=command in ['show run', 'sh run', 'sho run']))

        self.__update_queue.put({'task': DeviceActionCompleteEnum.COLLECTED, 'message': f'Collected configurations for {self.description}'})

    def extra_collect(self, out_dir: str = '.', command_list: list[str] = []) -> None:
        """
        Collects extra configurations from the device by executing commands provided in the command_list and saving the output into specified files within the given output directory.

        NOTE: This method should not be called directly, it should be registered as an action using the register_action method.

        :param out_dir: The directory where configuration command outputs will be saved. If the directory does not exist, it will be created. Defaults to the current directory.
        :param command_list: List of extra commands to capture the output of.
        """
        self.__log.info(f'({self.description}) Collecting extra configurations')

        self.__log.debug(f'({self.description}) Creating output directory {out_dir}')
        os.makedirs(out_dir, exist_ok=True)

        for command in command_list:
            self.__log.info(f'({self.description}) Collecting output of command "{command}"')
            filename = command.replace(' ', '_').replace('/', '_').replace('|', '-')
            with open(os.path.join(out_dir, filename), 'w') as file:
                file.write(self.__device.capture_command(command, strip_excess_bangs=command in ['show run', 'sh run', 'sho run']))

        self.__update_queue.put({'task': DeviceActionCompleteEnum.EXTRACOLLECTED, 'message': f'Collected extra configurations for {self.description}'})

    def erase(self) -> None:
        """
        Erases the configuration on the Cisco Device by sending a set of predefined commands.

        NOTE: This method should not be called directly, it should be registered as an action using the register_action method.
        """
        self.__log.info(f'({self.description}) Erasing {self.__type}')
        self._send_commands(self.__manage['erase'])
        self.__update_queue.put({'task': DeviceActionCompleteEnum.ERASED, 'message': f'{self.description} - Deleted stored configurations'})

    def restart(self) -> None:
        """
        Restarts the Cisco Device by sending a set of predefined commands.

        NOTE: This method should not be called directly, it should be registered as an action using the register_action method.
        """
        self.__log.info(f'({self.description}) Restarting {self.__type}')
        self._send_commands(self.__manage['restart'])
        self.__update_queue.put({'task': DeviceActionCompleteEnum.RESTARTED, 'message': f'{self.description} - Restarted'})

    def backup(self) -> None:
        """
        Runs a backup of the device, storing the saved configuration in the shared string c char array so that the primary process can retrieve after backup
        completed.

        NOTE: This method should not be called directly, it should be registered as an action using the register_action method.
        """
        self.__log.info(f'({self.description}) Backing up configuration')

        config: str = ''

        for command in self.__manage['backup']:
            self.__log.info(f'({self.description}) Collecting output of command "{command}"')
            capture = self.__device.capture_command(command, strip_excess_bangs=command in ['show run', 'sh run', 'sho run'])

            if command in ['show run', 'sh run', 'sho run']:
                self.__log.info(f'({self.description}) Inserting "no shutdown" at start of each interface definition block')
                config += DeviceManager._insert_no_shutdowns(capture)

            if command in ['show vlan brief', 'sh vlan brief', 'sh vlan br']:
                self.__log.info(f'({self.description}) Inserting "no shutdown" at start of each interface definition block')
                config += DeviceManager._sh_vlan_brief_to_commands(capture)

        self.__log.info(f'({self.description}) Storing configuration for later access')
        self.__config[:len(config)] = config.encode('utf-8')

        self.__update_queue.put({'task': DeviceActionCompleteEnum.BACKUP, 'message': f'{self.description} - Configuration backed up'})

    def restore(self, config_list: list[str] = []) -> None:
        """
        Restores a configuration to the device. The configuration commands to upload are provided as multiple strings in command_list.

        We cannot just upload config_list to the device. upload_config() will send each config_list item one line at a time, waiting for the device prompt
        before sending the next. This will work for all config items except a multi-line MOTD, where the device will display no prompt until the MOTD is
        closed. We need to collapse all lines related to the MOTD to a single entry in the configuration list which contains '\r\n' to preserve the line
        breaks.

        Cisco "sh run", outputs the MOTD as "banner motd ^C ...message... ^C". We do not want to send two characters, so we replace all instances of '^C' in the
        MOTD strings with a '|' (hopefully no student will use this character)

        NOTE: This method should not be called directly, it should be registered as an action using the register_action method.

        :param config_list: List of configuration commands to enter into device in "configuration mode"
        """
        self.__log.info(f'({self.description}) Restoring backed-up configuration')

        # Create a new list of configuration items to send where multi-line MOTD settings are collapsed into a single line
        configs_to_send: list[str] = []

        config_iter = iter(config_list)
        for config_line in config_iter:
            if not config_line.startswith('banner motd ^C'):
                # This is a normal - non MOTD - line in the configuration, append config_line to the configs_to_send and loop to the next line
                configs_to_send.append(config_line)
                continue

            if config_line.count('^C') == 2:
                # This is a single-line MOTD banner, append config_line (replacing all '^C' with '|') to the configs_to_send and loop to the next line
                configs_to_send.append(config_line.replace('^C', '|'))
                continue

            # We have hit a multi-line MOTD, need to collapse all lines (until we see another line ending with '^C')
            motd: list[str] = []  # Initialise empty list to hold the MOTD

            # Loop through config lines, appending each one (starting with the current) EXCEPT for the first line that ends with '^C'
            while not config_line.endswith('^C') or len(motd) == 0:
                # Append config_line to motd. IF this is the first line in the multi-line MOTD, replace the first '^C' with a '|'
                motd.append(config_line if len(motd) else config_line.replace('^C', '|', 1))
                config_line = next(config_iter)

            # Append MOTD closing config line, replacing last two characters ('^C') with a '|'
            motd.append(config_line[:-2] + '|')

            # Append the MOTD to the result and loop to the next line
            configs_to_send.append('\n'.join(motd))

        self.__device.upload_config(configs_to_send)

        self.__update_queue.put({'task': DeviceActionCompleteEnum.RESTORE, 'message': f'{self.description} - Restored configuration'})

    def run(self) -> None:
        """
        Method to be run in the sub-process

        When launched as a process, will:
         - Connect to the CiscoDevice
         - Set the device to "enable" mode
         - Execute all registered actions in turn

        All progress updates are pushed to the update queue. Logs are generated at each significant step in the process.
        """
        # Connect to device and update status
        self.__log.info(f'({self.description}) Establishing connection to {self.__type}')
        self.__device.connect()
        self.__update_queue.put({'task': DeviceActionCompleteEnum.CONNECTED, 'message': f'{self.description} - Connected to {self.__type} device'})

        # Set device to enable mode and update status
        self.__log.info(f'({self.description}) Setting device to enable mode')
        self.__device.set_enable_mode(self.__usernames, self.__passwords)
        self.__update_queue.put({'task': DeviceActionCompleteEnum.ENABLE, 'message': f'{self.description} - Device in "enable" mode'})

        for action in self.__actions.values():
            self.__log.info(f'({self.description}) Executing action: {action["method"].__name__}')
            action['method'](*action['args'], **action['kwargs'])

        with self.__complete.get_lock():
            self.__complete.value = True
        self.__update_queue.put({'task': DeviceActionCompleteEnum.FINISHED, 'message': f'{self.description} - Finished all actions'})

    def recreate(self) -> 'DeviceManager':
        """
        Recreates a new instance of the DeviceManager with the current object's attributes.

        If the DeviceManager process is terminated early, or fails, it cannot be restarted to try again. Therefore, this method returns a new instance
        of the same sub-process that can be restarted to re-try the failed attempt. This method will create a fresh instance of the DeviceManager.
        It reinitializes all attributes, registered actions, and other parameters to ensure that the same tasks will be attempted when restarting the
        sub-process.

        :return: A new instance of the DeviceManager initialized with the current object's attributes.
        """
        self.__log.info(f'({self.description}) Recreating DeviceManager instance')
        result = DeviceManager(self.__device, self.__type, self.description, self.full_description, self.__update_queue, self.__log_queue, self.__usernames, self.__passwords)
        for action, params in self.__actions.items(): result.register_action(action, *params['args'], **params['kwargs'])
        return result

    @property
    def config(self) -> str:
        """
        Returns the device configuration stored in the shared string c char array. Extract from array and convert to string for returning.

        :return: String stored in self.__config
        """
        raw = bytes(self.__config[:]).split(b'\x00', 1)[0]
        return raw.decode('utf-8', errors='strict')
