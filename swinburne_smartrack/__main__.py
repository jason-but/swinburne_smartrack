import argparse
# Import Libraries
# re           - Regular Expressions
# logging      - Python logging module
# rich.console - Text UI Console (from rich package)
# dialog       - System dialog wrapper (from pythondialog package)
# requests     - HTTP/HTTPS Client
import re
import logging
from .config import Configuration
from .smartrack import SmartRack
import rich.console
#import dialog
#import requests
from rich.table import Table
from rich.panel import Panel

# TODO: Clean up imports
# TODO: Add parser for devicemanager and "all"
# TODO: Re-write smartrack test command to extract UI from SmartRack class
# TODO: Think about how logging is handled in this file

def smartrack(arguments: argparse.Namespace):
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

    return parser.parse_args()


if __name__ == '__main__':
    console = rich.console.Console()
    try:
        arguments = parse_arguments()
        if arguments.config_file: Configuration(arguments.config_file)

        arguments.func(arguments, console)

        print(arguments.debug)
    except KeyboardInterrupt as err:
        pass
    except (Exception,):
        rich.console.Console().print_exception()


