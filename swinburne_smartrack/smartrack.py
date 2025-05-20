"""
This module implements the SmartRack class which is used to access the SmartRack system to download booked device information. This information can then be
used to connect to remote Cisco devices to manage individual devices.

The SmartRack class contains methods that:
  - Query the user for information about the SmartRack servers
  - Download device information
  - Allow the user to filter the devices to a shortlist

Running the module directly will run a test suite allowing verification of functionality.
"""

# Import Libraries
# re           - Regular Expressions
# logging      - Python logging module
# rich.console - Text UI Console (from rich package)
# dialog       - System dialog wrapper (from pythondialog package)
# requests     - HTTP/HTTPS Client
import re
import logging
import rich.console
import requests

# Library modules
# config.config - SmartRack system configuration (as loaded from config TOML file)
from .config import Configuration


class SmartRack:
    """
    SmartRack class
    """
    class AuthError(Exception):
        pass

    def __init__(self, console: rich.console.Console, rooms: dict[str, dict[str, str]]):
        """
        Construct the SmartRack class instance.

        Creates a logger for the SmartRack class, and initialises all the class internal variables.

        After creation, use Class methods to access the SmartRack servers.

        :param console: The application instance of the Rich Console class
        :param rooms: Information about SmartRack servers maps room short-name to dictionary item mapping 'description' to long-name and 'url' to server URL
        """
        # Establish logger for SmartRack class
        self.__log = logging.getLogger('SmartRack')
        self.__log.info(f'Constructing Class')

        # Local variable for the console, also for the pythondialog instance
        self.__console = console

        # Initialise list holding all device connection details
        self.__devices: dict[str, dict[str, str]] = {}

    def fetch_booked_devices(self, selected_rooms: list[str], auth_details: dict[str, str]) -> None:
        """
        Download all booked devices for all selected rooms, store all connection details in self.__devices.

        Method will ask user for authentication details via a dialog box prior to connecting to SmartRack servers.

        Progress will be displayed to the console, logging is provided via the logger.

        :param title: Title to display at top of dialog box requesting authentication information
        """
        with self.__console.status('[magenta]Downloading SmartRack booked devices', spinner='earth'):
            for room in selected_rooms:
                url = Configuration().smartrack_servers[room]['url']

                self.__console.print(f'Connecting to {room} at {url}')
                self.__log.info(f'Attempting to connect to {room} at {url}')

                r = requests.post(url, data=auth_details)

                self.__log.info(f'HTTP status code: {r.status_code}')
                if r.status_code != 200:
                    raise Exception(f'Unable to connect to {url}. Status code: {r.status_code}')

                if r.content.decode('utf8') == 'Logon error\n':
                    raise SmartRack.AuthError('Bad username/password combination supplied')

                split_response = r.content.decode('utf-8').splitlines()
                self.__log.debug(f'Received device login information {split_response}')
                for device in split_response:
                    details = device.split(':')
                    unique_name = f'{room} {details[5]}'

                    # Split as '*****(<enclosure>)*****(<kit>) <device>'
                    sub_details = re.search(r'^[\w\s]+\((?P<enclosure>\w+)[)\w\s]+\((?P<kit>\w+)\) (?P<device>[\w\s]+)', details[5])
                    if sub_details is None:
                        self.__log.warning(f'Cannot extract device details from: {unique_name}')
                        continue

                    if '_' in details[7]:
                        student, nickname = details[7].split('_', maxsplit=1)
                    else:
                        student, nickname = '', ''

                    self.__devices[unique_name] = {'room':      room,
                                                   'server':    details[1],
                                                   'username':  details[2],
                                                   'password':  details[3],
                                                   'fullname':  details[5],
                                                   'enclosure': sub_details.group('enclosure'),
                                                   'kit':       sub_details.group('kit'),
                                                   'device':    sub_details.group('device'),
                                                   'student':   student,
                                                   'nickname':  nickname
                                                   }
                    self.__log.info(f'{unique_name}')
                    self.__log.debug(f'Details: {self.__devices[unique_name]}')

                self.__console.print(f'Retrieved {len(split_response)} devices for {room}')

    def filter(self, enclosures: list[str] = ['Black', 'Red', 'Blue', 'Green', 'Yellow'], kits: list[str] = ['Yellow', 'Green', 'Orange', 'Purple', 'White'], devices: list[str] = ['Switch 1', 'Switch 2', 'Switch 3', 'Switch 4', 'Router 1', 'Router 2', 'Router 3', 'Router 4']) -> dict[str, dict[str, str]]:
        """
        :param enclosures: List of strings of Enclosures we are interested in
        :param kits: List of strings of Kits we are interested in
        :param devices: List of strings of Devices we are interested in
        :return:
        """
        return {key: value for key, value in self.__devices.items() if value['enclosure'] in enclosures and value['kit'] in kits and value['device'] in devices}

    def filter_nickname(self, match: list[str]) -> dict[str, dict[str, str]]:
        """
        Filter devices where nickname is one of the items in list and return the list of devices
        :param match: List of strings of nicknames we are interested in
        :return:
        """
        self.__log.info(f'Filtering device list where nickname is one of {match}')
        return {key: value for key, value in self.__devices.items() if value['nickname'] in match}
