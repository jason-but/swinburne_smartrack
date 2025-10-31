"""
This module implements the DeviceManager class which is used to manage control of a Cisco Device in the SmartRack system
"""

# Import System Libraries
import os
import logging
import logging.handlers
import multiprocessing
from typing import Any
from enum import Enum

# Import SmartRackLibrary modules
from .configuration import Configuration
from .ciscodevice import CiscoDevice

# TODO: Enable capturing of "extra commands"
# TODO: Add backup() and restore() actions


class DeviceActionCompleteEnum(Enum):
    """
    The DeviceActionCompleteEnum class implements an enumeration of device action completion states. Used to identify the specific state
    of an action that has concluded.

    :ivar CONNECTED: Indicates that the device connection process has completed.
    :ivar ENABLE: Indicates that the device has been successfully entered into enable mode, and is ready to accept commands.
    :ivar COLLECTED: Indicates that the data collection from the device is complete.
    :ivar EXTRACOLLECTED: Indicates that the collections of extra commands is complete.
    :ivar ERASED: Indicates that the data erasure process on the device has concluded.
    :ivar RESTARTED: Indicates that the device has been successfully restarted.
    :ivar FINISHED: Indicates that all actions on the device have concluded.
    """
    CONNECTED = 'Connected devices'
    ENABLE = 'Devices in "enable" mode'
    COLLECTED = 'Completed data collections'
    EXTRACOLLECTED = 'Completed collecting extra commands'
    ERASED = 'Device with deleted configurations'
    RESTARTED = 'Restarted devices'
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
