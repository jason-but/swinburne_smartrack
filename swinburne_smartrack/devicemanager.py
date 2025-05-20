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

# Library modules
# config.config - SmartRack system configuration (as loaded from config TOML file)
# ciscodevice.CiscoDevice - Manages interaction with remote Cisco Device
from .config import Configuration
from .ciscodevice import CiscoDevice


class DeviceManager(multiprocessing.Process):
    def __init__(self, device: CiscoDevice, type: str, update_queue: multiprocessing.Queue, log_queue: multiprocessing.Queue):
        """
        This class manages a device connection and corresponding commands related to the specific type of the device.
        It validates the type of the device upon instantiation to ensure compatibility with the management configuration.

        :param device: Represents the connection to the Cisco device.
        :param type: Specifies the type of the device to be managed. It must exist in the SmartRack configuration file.

        :raises ValueError: If the device type does not exist in the SmartRack configuration file.
        """
        super().__init__()
        # Store multiprocessing queue variables
        self.__update_queue = update_queue
        self.__log_queue = log_queue

        # Establish logger for SmartRack class
        self.__log = logging.getLogger('DeviceManager')
        self.__log.addHandler(logging.handlers.QueueHandler(log_queue))
        self.__log.debug(f'Constructing Class')

        # Validate parameters
        if type not in Configuration().manage:
            raise ValueError(f'DeviceManager: type {type} is not supported')

        # Store device connection, device type, and all commands related to managing this device type
        self.__device = device
        self.__type = type
        self.__manage: dict[str, list[str]] = Configuration().manage[type]
        self.__actions: dict[str, Any] = {}

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
        self.__update_queue.put({'task': 'collect', 'message': f'Collecting configurations for {self.name}'})
        self.__log.info(f'Collecting configurations')

        self.__log.debug(f'Creating output directory {out_dir}')
        os.makedirs(out_dir, exist_ok=True)

        for command in self.__manage['collect']:
            self.__log.info(f'Collecting output of command "{command}"')
            filename = command.replace(' ', '_').replace('/', '_').replace('|', '-')
            with open(os.path.join(out_dir, filename), 'w') as file:
                file.write(self.__device.capture_command(command, strip_excess_bangs=command in ['show run', 'sh run', 'sho run']))

    def erase(self) -> None:
        """
        Erases the configuration on the Cisco Device by sending a set of predefined commands.

        NOTE: This method should not be called directly, it should be registered as an action using the register_action method.
        """
        self.__update_queue.put({'task': 'erase', 'message': f'Erasing stored configurations for {self.name}'})
        self.__log.info(f'Erasing {self.__type}')
        self._send_commands(self.__manage['erase'])

    def restart(self) -> None:
        """
        Restarts the Cisco Device by sending a set of predefined commands.

        NOTE: This method should not be called directly, it should be registered as an action using the register_action method.
        """
        self.__update_queue.put({'task': 'restart', 'message': f'Erasing stored configurations for {self.name}'})
        self.__log.info(f'Restarting {self.__type}')
        self._send_commands(self.__manage['restart'])

    def run(self) -> None:
        # Connect to device and update status
        self.__log.info(f'Establishing connection to {self.__type}')
        self.__device.connect()
        self.__update_queue.put({'task': 'connected', 'message': f'Connected to {self.name}'})

        # Set device to enable mode and update status
        self.__log.info(f'Setting device to enable mode')
        self.__device.set_enable_mode([], [])
        self.__update_queue.put({'task': 'enable', 'message': f'{self.name} now in "enable" mode'})

        for action in self.__actions.values():
            self.__log.info(f'Executing action: {action["method"].__name__}')
            action['method'](*action['args'], **action['kwargs'])

        self.__update_queue.put({'task': 'finish', 'message': f'Finished all tasks for {self.name}'})


if __name__ == '__main__':
    try:
        # Create argparse instance and parse command line parameters
        import argparse

        parser = argparse.ArgumentParser(description='DeviceManager Test Suite',
                                         formatter_class=argparse.RawTextHelpFormatter,
                                         allow_abbrev=False
                                         )
        parser.add_argument('-c', '--config-file',
                            help='Specify the smartrack configuration file (default: system configuration)'
                            )
        parser.add_argument('-d', '--debug',
                            default='INFO',
                            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                            help='Set logging level (default: %(default)s)'
                            )
        parser.add_argument('hostname', help='Hostname or IP address of remote Cisco device')
        parser.add_argument('username', help='Username to connect to remote Cisco device')
        parser.add_argument('password', help='Password to connect to remote Cisco device')
        parser.add_argument('port', nargs='?', default=22, type=int, help='Port number of remote Cisco device (default: %(default)s)')
        arguments = parser.parse_args()

        # Create the Rich Console and Rich Logger
        import rich.logging
        import rich.console

        if arguments.config_file: Configuration(arguments.config_file)

        console = rich.console.Console()
        logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                            handlers=[rich.logging.RichHandler(markup=True, console=console)],
                            level=getattr(logging, arguments.debug)
                            )

        logger = logging.getLogger('')

        # This queue holds log messages from the worker threads
        log_queue = multiprocessing.Queue(-1)

        # This queue holds status updates from the worker threads
        progress_queue = multiprocessing.Queue()  # Queue used for reporting progress

        # Create the Cisco Device, set it to enable mode, and capture/print output of "show ip int brief"
        manager = DeviceManager(CiscoDevice(arguments.hostname, arguments.username, arguments.password, arguments.port), 'router', progress_queue, log_queue)

        manager.register_action('collect')
        manager.run()

    except KeyboardInterrupt as err:
        pass
    except (Exception,):
        rich.console.Console().print_exception()

