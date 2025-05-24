"""
This module implements the SmartRack class which is used to access the SmartRack system to download booked device information. This information can then be
used to connect to remote Cisco devices to manage individual devices.
"""

# Import System Libraries
import re
import logging
import rich.console
import requests

# Import SmartRackLibrary modules
from .configuration import Configuration


class SmartRack:
    """
    Manages downloading of remote device access information from the SmartRack system. After downloading into an internal database, enables retrieval
    using a filter to selectively access device information.
    """
    class AuthError(Exception):
        """
        This exception is raised when there is an issue with user authentication or authorization. It is intended to encapsulate information related to
        authentication errors and can be used to signal problems with access control or identity validation.
        """
        pass

    def __init__(self, console: rich.console.Console):
        """
        Construct the SmartRack class instance.

        Creates a logger for the SmartRack class, and initialises all the class internal variables. After creation, use methods to access the SmartRack servers.

        :param console: The application instance of the Rich Console class
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
        Fetches and processes details of booked devices from SmartRack servers for the given rooms.

        This method connects to the SmartRack servers (using auth_details) for each specified room, and retrieves the device login information for
        all equipment booked by the user. Each device's details are parsed, sanitized, and stored in an internal dictionary for further use. It logs
        all significant actions and handles errors related to connection, authentication, and data parsing.

        :param selected_rooms: A list of room identifiers for which the devices need to be fetched, room URLs in configuration file.
        :param auth_details: Dictionary containing authentication details to access the SmartRack servers, e.g. {'username': 'myusername', 'password': '<PASSWORD>'}..

        :raises AuthError: If the authentication details fail to access SmartRack.
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
                        sub_details = re.search(r'^[\w\s]+\((?P<enclosure>\w+)\) (?P<device>[\w\s]+)', details[5])
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
                                                   'kit':       sub_details.group('kit') if 'kit' in sub_details.groupdict() else '',
                                                   'device':    sub_details.group('device'),
                                                   'student':   student,
                                                   'nickname':  nickname
                                                   }
                    self.__log.info(f'{unique_name}')
                    self.__log.debug(f'Details: {self.__devices[unique_name]}')

    def filter(self, enclosures: list[str] = ['Black', 'Red', 'Blue', 'Green', 'Yellow'], kits: list[str] = ['Yellow', 'Green', 'Orange', 'Purple', 'White', ''], devices: list[str] = ['Switch 1', 'Switch 2', 'Switch 3', 'Switch 4', 'Router 1', 'Router 2', 'Router 3', 'Router 4', 'ASA 1', 'ASA 2', 'ASA 3', 'ASA 4', 'ASA 5']) -> dict[str, dict[str, str]]:
        """
        Filters the internal `__devices` dictionary based on the specified criteria. The method checks if the enclosure, kit, and device of each item
        in the dictionary match with the provided lists of allowed values. Only the items that satisfy all conditions will be included in the result.

        :param enclosures: List of acceptable enclosure names. Each device in the resulting dictionary must have its enclosure present in this list.
        :param kits: List of acceptable kit names. Each device in the resulting dictionary must have its kit present in this list.
        :param devices: List of acceptable device names. Each device in the resulting dictionary must have its device name present in this list.

        :return: A filtered dictionary mapping device identifiers to device data dictionaries, filtered based on the provided parameters.
        """
        return {key: value for key, value in self.__devices.items() if value['enclosure'] in enclosures and value['kit'] in kits and value['device'] in devices}

    def filter_nickname(self, match: list[str]) -> dict[str, dict[str, str]]:
        """
        Filters the device list based on a specified list of nicknames. Only items with the provided nicknames will be included in the result.

        :param match: A list containing nicknames to filter the device list by.

        :return: A filtered dictionary mapping device identifiers to device data dictionaries, filtered based on the provided parameters.
        """
        self.__log.info(f'Filtering device list where nickname is one of {match}')
        return {key: value for key, value in self.__devices.items() if value['nickname'] in match}
