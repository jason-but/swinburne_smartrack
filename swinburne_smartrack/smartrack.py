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
import dialog
import requests

# Library modules
# config.config - SmartRack system configuration (as loaded from config TOML file)
from .config import Configuration


class SmartRack:
    """
    SmartRack class
    """
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
        self.__dialog = dialog.Dialog(dialog='dialog')

        # Store dictionary of SmartRack server details, and empty list of selected rooms
        self.__rooms = rooms
        self.__selected_rooms: list[str] = []

        # Initialise list holding all device connection details
        self.__devices: dict[str, dict[str, str]] = {}

        # Initialise storage of SmartRack authentication details
        self.__auth_details: dict[str, str] = {}

    def _ask_to_terminate(self, title: str) -> None:
        """
        Ask the user whether they want to terminate the program or not
          - If they choose YES, raise Exception to kill application
          - If they choose NO, return and allow program to continue
        :param title: Application title to display
        """
        self.__log.debug('Terminating Application')
        if self.__dialog.yesno('Are you sure that you want to terminate application?', title=title) == self.__dialog.OK:
            raise Exception('Terminating')

    def _ask_auth_details(self, title: str) -> None:
        """
        Retrieve username/password to access the SmartRack site and save in self.__auth_details
        :param title: Title to display at top of dialog box
        :return:
        """
        while True:
            # Display password entry box, each tuple in elements is:
            #  field label, label y pos, label x pos, initial field value, field y pos, field x pos, field length, input length, 0=plaintext/1=hidden
            code, values = self.__dialog.mixedform('Enter SmartRack Authentication details below:\n',
                                                   title=title,
                                                   elements=[("Username:", 2, 2, "", 2, 15, 50, 50, 0),
                                                             ("Password:", 4, 2, "", 4, 15, 50, 50, 1)],
                                                   cancel_label='Quit',
                                                   insecure=True
                                                   )

            if code == self.__dialog.OK:
                # Username and password provided, save and break out of loop
                self.__auth_details = {'username': values[0], 'password': values[1]}
                break

            # User selected QUIT, confirm termination (will raise exception if user confirms, otherwise continue and try again)
            self._ask_to_terminate(title)

        self.__log.info(f'Authentication details: {self.__auth_details}')

    def select_smartrack_rooms(self, title: str, instructions: str) -> None:
        """
        SelectRooms method
        :return:
        """
        self.__log.debug(f'Ask user to select which rooms to use')

        # Loop forever asking user to select room, when one or more rooms are selected, break out of loop
        while True:
            # Display message box
            code, self.__selected_rooms = self.__dialog.checklist(instructions,
                                                                  choices=[(key, value['description'], False) for key, value in self.__rooms.items()],
                                                                  title=title,
                                                                  cancel_label='Quit'
                                                                  )

            if code == self.__dialog.OK:
                # User selected OK, if at least one room is selected break out of loop, otherwise display error message and try again
                if len(self.__selected_rooms) > 0: break
                self.__log.info(f'No rooms selected: asking again')
                self.__dialog.msgbox('ERROR: You must select at least one room', title=title)
            else:
                # User selected QUIT, confirm termination (will raise exception if user confirms, otherwise continue and try again)
                self._ask_to_terminate(title)

        self.__log.info(f'Selected rooms: {self.__selected_rooms}')

    def fetch_booked_devices(self, title: str) -> None:
        """
        Download all booked devices for all selected rooms, store all connection details in self.__devices.

        Method will ask user for authentication details via a dialog box prior to connecting to SmartRack servers.

        Progress will be displayed to the console, logging is provided via the logger.

        :param title: Title to display at top of dialog box requesting authentication information
        """
        self._ask_auth_details(title)

        self.__console.clear()

        with self.__console.status('[magenta]Downloading SmartRack booked devices', spinner='earth'):
            for room in self.__selected_rooms:
                url = self.__rooms[room]['url']

                self.__console.print(f'Connecting to {room} at {url}')
                self.__log.info(f'Attempting to connect to {room} at {url}')

                r = requests.post(url, data=self.__auth_details)

                self.__log.info(f'HTTP status code: {r.status_code}')
                if r.status_code != 200:
                    raise Exception(f'Unable to connect to {url}. Status code: {r.status_code}')

                while r.content.decode('utf8') == 'Logon error\n':
                    self.__dialog.msgbox('ERROR: Bad username/password combination supplied', title=f' Connecting to {room} ')
                    self._ask_auth_details(title)
                    r = requests.post(url, data=self.__auth_details)

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


# Execute test/validation suite if run as python -m swinburne_smartrack.smartrack
if __name__ == '__main__':
    try:
        # Create argparse instance and parse command line parameters
        import argparse
        parser = argparse.ArgumentParser(description='SmartRack Test Suite',
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
        arguments = parser.parse_args()

        # Create the Rich Console and Rich Logger
        import rich.logging
        console = rich.console.Console()
        logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                            handlers=[rich.logging.RichHandler(markup=True, console=console)],
                            level=getattr(logging, arguments.debug)
                            )

        logger = logging.getLogger('')

        config = Configuration()
        # Create SmartRack instance
        test = SmartRack(console, config.smartrack_servers)

        # Ask user to select rooms
        test.select_smartrack_rooms(' ATC Room Selection ', 'Please select which rooms you would like to test this library with')

        # Download booked devices
        test.fetch_booked_devices(' ATC Website Authentication Information ')

        # Retrieve list (no filter, get all devices)
        result = test.filter()

        # Display all devices in table
        logger.info('Displaying booked device details')
        from rich.table import Table
        table = Table(show_header=True, header_style="bold green", title="Booked Devices", show_lines=True)
        table.add_column("Room", style="green")
        table.add_column("Device", style="green")
        table.add_column("Server", style="cyan")
        table.add_column("Username", style="cyan")
        table.add_column("Password", style="red")

        for details in result.values():
            table.add_row(details['room'], details['fullname'], details['server'], details['username'], details['password'])

        console.print(table)

    except KeyboardInterrupt as err:
        pass
    except (Exception,):
        rich.console.Console().print_exception()
