"""
This module implements the CiscoDevice class which is used to manage control of a Cisco Device in the SmartRack system

The CiscoDevice class contains methods that:
  - Place the device in enable mode
  - Send commands to the device
  - Capture responses from the device
  - Upload configurations to the device

Running the module directly will run a test suite allowing verification of functionality.
"""

# Import Libraries
# os      - Manages creating files and directories on the system
# logging - Python logging module
import os
import logging
import logging.handlers
import multiprocessing
from typing import Any
from enum import Enum, auto

# Library modules
# config.config - SmartRack system configuration (as loaded from config TOML file)
# ciscodevice.CiscoDevice - Manages interaction with remote Cisco Device
from .config import Configuration
from .ciscodevice import CiscoDevice


class DeviceActionCompleteEnum(Enum):
    """
    The DeviceActionCompleteEnum class implements an enumeration of device action completion states. Used to identify the specific state
    of an action that has concluded.

    :ivar CONNECTED: Indicates that the device connection process has completed.
    :ivar ENABLE: Indicates that the device has been successfully entered into enable mode, and is ready to accept commands.
    :ivar COLLECTED: Indicates that the data collection from the device is complete.
    :ivar ERASED: Indicates that the data erasure process on the device has concluded.
    :ivar RESTARTED: Indicates that the device has been successfully restarted.
    :ivar FINISHED: Indicates that all actions on the device have concluded.
    """
    CONNECTED = 'Connected devices'
    ENABLE = 'Devices in "enable" mode'
    COLLECTED = 'Completed data collections'
    ERASED = 'Reset devices'
    RESTARTED = 'Restarted devices'
    FINISHED = 'Devices with all actions complete'


class DeviceManager(multiprocessing.Process):
    def __init__(self, device: CiscoDevice, device_type: str, update_queue: multiprocessing.Queue, log_queue: multiprocessing.Queue):
        """
        This class manages a device connection and corresponding commands related to the specific type of the device.
        It validates the type of the device upon instantiation to ensure compatibility with the management configuration.

        :param device: Represents the connection to the Cisco device.
        :param device_type: Specifies the type of the device to be managed. It must exist in the SmartRack configuration file.

        :raises ValueError: If the device type does not exist in the SmartRack configuration file.
        """
        super().__init__()
        self.name = 'DeviceManager(' + ':'.join(str(i) for i in self._identity) + ')'

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

        This method iterates through a list of commands to send to the Cisco Device, allows a single call to issue
        multiple commands.

        :param command_list: The list of commands to execute on the device.
        """
        for command in command_list:
            self.__log.info(f'Sending command "{command}"')
            self.__device.send_command(command)

    ##########
    # PUBLIC METHODS
    ##########
    def _establish_connection(self) -> None:
        """
        Establishes a connection with the device and configures it to the enable mode.

        This method manages all the initialisation and must be called prior to running any of the following methods.
        """
        self.__log.info(f'Establishing connection to {self.__type}')
        self.__device.connect()
        self.__log.info(f'Setting device to enable mode')
        self.__device.set_enable_mode([], [])

    def register_action(self, action: str, *args, **kwargs) -> None:
        """
        Registers an action with its corresponding method and arguments into the internal actions registry.
        When the process is running, and after the connection is established in enable mode, all registered methods
        will be executed in turn with the parameters provided here.

        :param action: The name of the method in the class to be registered.
        :param args: Positional arguments required by the action method.
        :param kwargs: Keyword arguments required by the action method.
        """
        self.__log.info(f'Registering action: {action}(args={args}, kwargs={kwargs})')
        self.__actions[action] = {'method': getattr(self, action), 'args': args, 'kwargs': kwargs}

    def collect(self, out_dir: str = '.') -> None:
        """
        Collects configurations from the device by executing pre-defined commands and saving the
        output into specified files within the given output directory.

        NOTE: This method should not be called directly, it should be registered as an action using the register_action method.

        :param out_dir: The directory where configuration command outputs will be saved. If the
            directory does not exist, it will be created. Defaults to the current directory.
        """
        self.__log.info(f'Collecting configurations')

        self.__log.debug(f'Creating output directory {out_dir}')
        os.makedirs(out_dir, exist_ok=True)

        for command in self.__manage['collect']:
            self.__log.info(f'Collecting output of command "{command}"')
            filename = command.replace(' ', '_').replace('/', '_').replace('|', '-')
            with open(os.path.join(out_dir, filename), 'w') as file:
                file.write(self.__device.capture_command(command, strip_excess_bangs=command in ['show run', 'sh run', 'sho run']))

        self.__update_queue.put({'task': DeviceActionCompleteEnum.COLLECTED, 'message': f'Collected configurations for {self.name}'})

    def erase(self) -> None:
        """
        Erases the configuration on the Cisco Device by sending a set of predefined commands.

        NOTE: This method should not be called directly, it should be registered as an action using the register_action method.
        """
        self.__log.info(f'Erasing {self.__type}')
        self._send_commands(self.__manage['erase'])
        self.__update_queue.put({'task': DeviceActionCompleteEnum.ERASED, 'message': f'{self.name} - Deleted stored configurations'})

    def restart(self) -> None:
        """
        Restarts the Cisco Device by sending a set of predefined commands.

        NOTE: This method should not be called directly, it should be registered as an action using the register_action method.
        """
        self.__log.info(f'Restarting {self.__type}')
        self._send_commands(self.__manage['restart'])
        self.__update_queue.put({'task': DeviceActionCompleteEnum.RESTARTED, 'message': f'{self.name} - Restarted'})

    def run(self) -> None:
        # Connect to device and update status
        self.__log.info(f'Establishing connection to {self.__type}')
        self.__device.connect()
        self.__update_queue.put({'task': DeviceActionCompleteEnum.CONNECTED, 'message': f'{self.name} - Connected to {self.__type} device'})

        # Set device to enable mode and update status
        self.__log.info(f'Setting device to enable mode')
        self.__device.set_enable_mode([], [])
        self.__update_queue.put({'task': DeviceActionCompleteEnum.ENABLE, 'message': f'{self.name} - Device in "enable" mode'})

        for action in self.__actions.values():
            self.__log.info(f'Executing action: {action["method"].__name__}')
            action['method'](*action['args'], **action['kwargs'])

        self.__update_queue.put({'task': DeviceActionCompleteEnum.FINISHED, 'message': f'{self.name} - Finished all actions'})
