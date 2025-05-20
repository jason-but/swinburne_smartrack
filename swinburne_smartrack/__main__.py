import argparse
# Import Libraries
# re           - Regular Expressions
# logging      - Python logging module
# rich.console - Text UI Console (from rich package)
# dialog       - System dialog wrapper (from pythondialog package)
# requests     - HTTP/HTTPS Client
import re
import logging

import dialog

from .config import Configuration
from .smartrack import SmartRack
import rich.console
from rich.table import Table
from rich.panel import Panel

# TODO: Clean up imports
# TODO: Add parser for devicemanager and "all"
# TODO: Re-write smartrack test command to extract UI from SmartRack class
# TODO: Think about how logging is handled in this file


def smartrack(arguments: argparse.Namespace, console: rich.console) -> None:
    def confirm_termination(title: str) -> None:
        """
        Ask the user if they wish to terminate the test suite, if so print message to screen and terminate, otherwise return.

        :param title: Namespace object containing parsed command-line
                          arguments for the application.
        :param console: Rich console instance used to format and display output.
        :return: None
        """
        if __dialog.yesno('Are you sure that you want to terminate application?', title=title) == __dialog.OK:
            console.clear()
            console.print(Panel('Terminating SmartRack Web Site Test Suite', style='bold red'))
            exit(0)

    def select_servers(title: str, instructions: str) -> list[str]:
        """
        Select one or more servers from a checklist dialog.

        This function presents a checklist dialog box to the user, allowing them to select one or more servers from the list in the
        system SmartRack configuration file. It loops until the user makes a valid selection or confirms quitting. If the user selects OK, but no
        servers are chosen, an error message is displayed, prompting them to try again.

        :param title: The title to display at the top of the checklist dialog.
        :param instructions: Instructions displayed to the user in the checklist dialog.
        :return: A list of server identifiers chosen by the user.
        """
        # Loop forever asking user to select room, when one or more rooms are selected, break out of loop
        while True:
            # Display message box
            code, selected_rooms = __dialog.checklist(instructions,
                                                      choices=[(key, value['description'], False) for key, value in Configuration().smartrack_servers.items()],
                                                      title=title,
                                                      cancel_label='Quit'
                                                      )

            if code == __dialog.OK:
                # User selected OK, if at least one room is selected break out of loop, otherwise display error message and try again
                if len(selected_rooms) > 0: return selected_rooms
                __dialog.msgbox('ERROR: You must select at least one room', title=title)
            else:
                # User selected QUIT, confirm termination (will raise exception if user confirms, otherwise continue and try again)
                confirm_termination(title)

    def ask_auth_details(title: str) -> dict[str, str]:
        """
        Prompt the user to input authentication details for SmartRack. The function displays a dialog box for the user to input a username
        and password, the password field is hidden The dialog allows the user to quit. If "Quit" is selected, the function will
        confirm termination of the test.

        :param title: The title displayed on the authentication dialog box.
        :return: A dictionary containing the username and password provided by the user, with keys `'username'` and `'password'` respectively.
        """
        while True:
            # Display password entry box, each tuple in elements is:
            #  field label, label y pos, label x pos, initial field value, field y pos, field x pos, field length, input length, 0=plaintext/1=hidden
            code, values = __dialog.mixedform('Enter SmartRack Authentication details below:\n',
                                              title=title,
                                              elements=[("Username:", 2, 2, "", 2, 15, 50, 50, 0),
                                                        ("Password:", 4, 2, "", 4, 15, 50, 50, 1)],
                                              cancel_label='Quit',
                                              insecure=True
                                              )

            if code == __dialog.OK: return {'username': values[0], 'password': values[1]}

            # User selected QUIT, confirm termination (will raise exception if user confirms, otherwise continue and try again)
            confirm_termination(title)

    # Actual function starts here
    import rich.logging
    logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                        handlers=[rich.logging.RichHandler(markup=True, console=console)],
                        level=getattr(logging, arguments.debug)
                        )

    logger = logging.getLogger('')

    __dialog = dialog.Dialog(dialog='dialog')
    servers = select_servers(' ATC Room Selection ', 'Please select which rooms you would like to test this library with')
    smartrack = SmartRack(console, Configuration().smartrack_servers)

    while True:
        try:
            auth_details = ask_auth_details(' ATC Website Authentication Information ')

            console.clear()
            console.print(Panel('SmartRack Web Site Test Suite', style='bold green'))
            console.print()
            console.rule('Retrieving Booked Devices from SmartRack Website')
            smartrack.fetch_booked_devices(servers, auth_details)
            break
        except SmartRack.AuthError as e:
            __dialog.msgbox(f'ERROR: {e}', title='Authentication Error')

    # Retrieve list (no filter, get all devices)
    result = smartrack.filter()

    # Display all devices in table
    console.print()
    console.rule('Displaying booked device details')
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


def ciscodevice(arguments: argparse.Namespace, console: rich.console) -> None:
    """
    Test the functionality of the CiscoDevice class by connecting to a Cisco network device, switching to enable mode, and performing
    specific configurations and data retrieval.

    The test will:
     - Connect to the device using connection parameters in arguments
     - Place the device into enable mode
     - Capture the output of "sh ip int brief" and display as a table
     - Create a Loopback interface and set an IP address
     - Re-capture the output of "sh ip int brief" and display as a table

    Progress is logged to the console using the rich logging module.

    :param arguments: Parsed command-line arguments containing parameters to connect to device including hostname, username,password and port
    :param console: A rich console object used to display the output and logs in a styled format.
    :type console: rich.console.Console
    """
    # Test the CiscoDevice class, connect to device, put in enable mode, configure a Loopback interface
    import rich.logging
    logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                        handlers=[rich.logging.RichHandler(markup=True, console=console)],
                        level=getattr(logging, arguments.debug)
                        )

    logger = logging.getLogger('')

    from .ciscodevice import CiscoDevice

    console.print(Panel('Cisco Device Test Suite', style='bold green'))
    console.print()
    console.rule('Connecting to Cisco Device in enable mode')
    test_device = CiscoDevice(arguments.hostname, arguments.username, arguments.password, arguments.port)
    test_device.connect()
    test_device.set_enable_mode(usernames=[], passwords=[])

    console.print()
    console.rule('Capturing Interface Configuration')
    interfaces = [s for s in test_device.capture_command("show ip int brief", False).splitlines() if s != '']
    heading = interfaces.pop(0)
    interfaces.pop()

    console.print()
    console.rule('Displaying device interface details')
    table = Table(show_header=True, header_style="bold green", title="Interface Configuration", show_lines=True)
    for item in heading.split(): table.add_column(item, style="green")
    for interface in interfaces: table.add_row(*interface.split())
    console.print(table)

    console.print()
    console.rule('Configuring Loopback Interface')
    test_device.upload_config(["hostname test_new_name", 'interface Loopback0', 'ip address 105.9.5.129 255.255.255.224', '!'])

    console.print()
    console.rule('Re-entering enable mode')
    test_device.set_enable_mode(usernames=[], passwords=[])

    console.print()
    console.rule('Capturing Updated Interface Configuration')
    interfaces = [s for s in test_device.capture_command("show ip int brief", False).splitlines() if s != '']
    heading = interfaces.pop(0)
    interfaces.pop()

    console.print()
    console.rule('Displaying updated device interface details')
    table = Table(show_header=True, header_style="bold green", title="Interface Configuration", show_lines=True)
    for item in heading.split(): table.add_column(item, style="green")
    for interface in interfaces: table.add_row(*interface.split())
    console.print(table)


def devicemanager(arguments: argparse.Namespace, console: rich.console) -> None:
    pass


def parse_arguments() -> argparse.Namespace:
    # Create the main parser with global CLI parameters
    parser = argparse.ArgumentParser(description='Swinburne SmartRack Test Suite',
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

    # Create parameter template for ciscodevice and devicemanager module
    connection_parser = argparse.ArgumentParser(add_help=False)
    connection_parser.add_argument('hostname', help='Hostname or IP address of remote Cisco device')
    connection_parser.add_argument('username', help='Username to connect to remote Cisco device')
    connection_parser.add_argument('password', help='Password to connect to remote Cisco device')
    connection_parser.add_argument('port', nargs='?', default=22, type=int, help='Port number of remote Cisco device (default: %(default)s)')

    subparsers = parser.add_subparsers(title='test modules', help='Run one of the following sub-commands to test a particular component of the SmartRack library', required=True)

    subparsers.add_parser('smartrack', help='Test SmartRack website access', argument_default=smartrack).set_defaults(func=smartrack)
    subparsers.add_parser('ciscodevice', help='Test Cisco Device connection', parents=[connection_parser]).set_defaults(func=ciscodevice)
    subparsers.add_parser('devicemanager', help='Test single device collection in sub-process', parents=[connection_parser]).set_defaults(func=devicemanager)

    return parser.parse_args()


if __name__ == '__main__':
    console = rich.console.Console()
    try:
        arguments = parse_arguments()
        if arguments.config_file: Configuration(arguments.config_file)

        arguments.func(arguments, console)

    except KeyboardInterrupt as err:
        pass
    except (Exception,):
        rich.console.Console().print_exception()


