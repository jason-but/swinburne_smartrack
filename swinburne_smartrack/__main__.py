"""
This file is executed when the swinburne_smartrack is executed as 'python -m swinburne_smartrack'

Provides a test suite to validate the SmartRack library functionality after installation
"""
# Import System Libraries
import argparse
import logging
import multiprocessing
import re

# Import third-party libraries
import rich.console
import rich.logging
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree

# Import SmartRackLibrary modules
from .configuration import Configuration
from .smartracktui import SmartRackTUI
from .ciscodevice import CiscoDevice
from .devicemanager import DeviceManager, DeviceActionCompleteEnum
from .multidevicemanager import MultiDeviceManager


def display_booked_devices(devices: dict[str, dict[str, str]], console: rich.console) -> None:
    """
    Displays the details of booked devices in a tabular format.

    This function utilises the rich library to render a table containing the details of booked devices. Each row in the table corresponds to one booked
    device and includes information such as the room, device name, server, username, and password. The table is styled for better visibility.

    :param devices: A dictionary (as returned by SmartRack.filter() or SmartRack.filter_nickname()) mapping device identifiers to device data dictionaries.
    :param console: An instance of `rich.console.Console` used to render the output
    """
    console.print()
    console.rule('Displaying booked device details')

    table = Table(show_header=True, header_style="bold green", title="Booked Devices", show_lines=True)
    table.add_column("Room", style="green")
    table.add_column("Device", style="green")
    table.add_column("Server", style="cyan")
    table.add_column("Username", style="cyan")
    table.add_column("Password", style="red")

    for details in devices.values():
        table.add_row(details['room'], details['fullname'], details['server'], details['username'], details['password'])

    console.print(table)


def display_int_brief(interfaces: list[str], console: rich.console) -> None:
    """
    Displays an updated summary of device interface configurations in a tabular format.

    This function takes a list of interface details, where the first element corresponds to the headers for the table columns and the last element
    the router "enable". The data is then presented in a styled, structured  table for easy visualization.

    :param interfaces: List of strings containing interface details, where the first  element is a header row and the last element is discarded.
    :param console: An instance of `rich.console.Console` used to render the output
    """
    console.print()
    console.rule('Displaying updated device interface details')

    # First element in list contains the headers for each column, remove last element(contains router "enable" prompt)
    heading = interfaces.pop(0)
    interfaces.pop()

    # Create and print table
    table = Table(show_header=True, header_style="bold green", title="Interface Configuration", show_lines=True)
    for item in heading.split(): table.add_column(item, style="green")
    for interface in interfaces: table.add_row(*interface.split())
    console.print(table)


def smartrack(arguments: argparse.Namespace, console: rich.console) -> None:
    """
    Function executed when module loaded with 'python -m swinburne_smartrack smartrack' - tests the implementation of SmartRackTUI and SmartRack.

    Creates a SmartRackTUI class to enable user to select a SmartRack server and access booked devices. SmartRackTUI.ui() returns a SmartRack instance
    which is then used to extract the downloaded device details and displayed using display_booked_devices()

    :param arguments: Parsed command-line arguments that configure the application.Expected to include an attribute 'debug' indicating the logging level.
    :param console: A configured Rich Console object used for formatted output in the terminal.
    """
    logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                        handlers=[rich.logging.RichHandler(markup=True, console=console)],
                        level=getattr(logging, arguments.debug)
                        )

    try:
        tui = SmartRackTUI(console)
        smartrack = tui.ui('Please select which rooms you would like to test this library with')
    except SmartRackTUI.TerminateApp:
        console.clear()
        console.print(Panel('Terminating SmartRack Web Site Test Suite', style='bold red'))
        return

    # Retrieve list (no filter, get all devices)
    result = smartrack.filter()

    # Display all devices in table
    display_booked_devices(result, console)


def ciscodevice(arguments: argparse.Namespace, console: rich.console) -> None:
    """
    Function executed when module loaded with 'python -m swinburne_smartrack ciscodevice' - tests the implementation of CiscoDevice.

    Test the functionality of the CiscoDevice class by connecting to a Cisco network device, switching to enable mode, and performing
    specific configurations and data retrieval.

    The test will:
     - Connect to the device using connection parameters in arguments
     - Place the device into enable mode
     - Capture the output of "sh ip int brief" and display as a table
     - Create a Loopback interface and set an IP address
     - Re-capture the output of "sh ip int brief" and display as a table

    Progress is logged to the console using the rich logging module.

    :param arguments: Parsed command-line arguments containing parameters to connect to device including hostname, username, password and port
    :param console: A rich console object used to display the output and logs in a styled format.
    """
    # Test the CiscoDevice class, connect to device, put in enable mode, configure a Loopback interface
    logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                        handlers=[rich.logging.RichHandler(markup=True, console=console)],
                        level=getattr(logging, arguments.debug)
                        )

    console.print(Panel('Cisco Device Test Suite', style='bold green'))
    console.print()
    console.rule('Connecting to Cisco Device in enable mode')
    test_device = CiscoDevice(arguments.hostname, arguments.username, arguments.password, arguments.port)
    test_device.connect()
    test_device.set_enable_mode(usernames=['dragi', 'jason'], passwords=['bad_pass', 'pass', 'ena_pass'])

    console.print()
    console.rule('Capturing Interface Configuration')
    interfaces = [s for s in test_device.capture_command("show ip int brief", False).splitlines() if s != '']
    display_int_brief(interfaces, console)

    console.print()
    console.rule('Configuring Loopback Interface')
    test_device.upload_config(["hostname test_new_name", 'interface Loopback0', 'ip address 105.9.5.129 255.255.255.224', '!'])

    console.print()
    console.rule('Re-entering enable mode')
    test_device.set_enable_mode(usernames=[], passwords=[])

    console.print()
    console.rule('Capturing Updated Interface Configuration')
    interfaces = [s for s in test_device.capture_command("show ip int brief", False).splitlines() if s != '']
    display_int_brief(interfaces, console)


def devicemanager(arguments: argparse.Namespace, console: rich.console) -> None:
    """
    Function executed when module loaded with 'python -m swinburne_smartrack devicemanager' - tests the implementation of DeviceManager.

    Manages the execution of a device testing workflow using a DeviceManager process. DeviceManager runs as a sub-process, so we need to create
    multiprocessing Queue objects to enable communication of progress updates and log messages from the sub-process back to the main process.
    The function sets up and starts the DeviceManager process, using the arguments parameter to determine the device type (router or switch) and the
    directory to store captured output to. The process will:
     - Connect to the device using connection parameters in arguments
     - Place the device into enable mode
     - Run the "collect" task on the device, capturing output of the commands configured in the configuration file
     - Display a progress message as each sub-task completes
     - Cleans up and destroys the sub-process upon completion

    :param arguments: Parsed command-line arguments containing parameters to connect to device including hostname, username, password, port, device type and output directory.
    :param console: A rich console object used to display the output and logs in a styled format.
    """
    console.print(Panel('Device Manager Test Suite', style='bold green'))

    # This queue holds log messages from the worker tasks
    log_queue = multiprocessing.Queue(-1)

    # This queue holds status updates from the worker tasks
    progress_queue = multiprocessing.Queue()

    process = DeviceManager(CiscoDevice(arguments.hostname, arguments.username, arguments.password, arguments.port),
                            device_type=arguments.type,
                            description='',
                            full_description='',
                            update_queue=progress_queue,
                            log_queue=log_queue)

    process.register_action('collect', out_dir=arguments.output_dir)

    # Test the CiscoDevice class, connect to device, put in enable mode, configure a Loopback interface
    logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                        handlers=[rich.logging.RichHandler(markup=True, console=console)],
                        level=getattr(logging, arguments.debug)
                        )

    logger = logging.getLogger('')

    console.print()
    console.rule('Launching DeviceManager Process in background')
    logger.info(f'Starting DeviceManager')
    process.start()

    while process.is_alive():
        # Process messages regarding progress from the sub-process
        if not progress_queue.empty():
            update = progress_queue.get()
            console.print(f':thumbs_up: [bold blue]\\[{update["task"]}]:[/] {update["message"]}')

        while not log_queue.empty():
            record = log_queue.get()
            logger.handle(record)

    logger.info('Process clean-up via join()')
    process.join()
    logger.info(f'DeviceManager has terminated')


def multidevice(arguments: argparse.Namespace, console: rich.console) -> None:
    """
    Function executed when module loaded with 'python -m swinburne_smartrack multidevice' - tests the implementation of all library components.

    Brings everything together into a mini-application.
     - Uses SmartRackTUI and SmartRack to extract connection information for all devices booked by the user.
     - Creates a list of DeviceManager processes to connect to each booked device.
     - Registers each DeviceManager process to execute the "erase" task to delete any saved configurations.
     - Creates a MultiDeviceManager instance and tasks it to run all DeviceManager processes with a timeout of 30 seconds
     - Separately lists all devices that successfully, and unsuccessfully, completed the tasks.

    The function initializes the user interface for the SmartRack system to allow room
    selection, retrieves all devices in the selected rooms, and displays them to the
    user. Devices that match specific types are then processed in parallel by creating
    sub-processes to perform an erase operation, and their progress and results are
    managed and displayed.

    :param arguments: Parsed command-line arguments containing parameters.
    :param console: A rich console object used to display the output and logs in a styled format.
    """
    try:
        tui = SmartRackTUI(console)
        smartrack = tui.ui('Please select which rooms you would like to test this library with')

        # Retrieve list (no filter, get all devices)
        result = smartrack.filter()

        # Display all devices in table
        display_booked_devices(result, console)

        console.print()
        console.rule('Test Suite - sending erase command to all devices')

        # This queue holds log messages from the worker threads
        log_queue = multiprocessing.Queue(-1)

        # This queue holds status updates from the worker threads
        progress_queue = multiprocessing.Queue()  # Queue used for reporting progress

        # Create a DeviceManager sub-process in processes list IF the device name starts with "Router", "Switch", or "ASA"
        processes = [DeviceManager(device=CiscoDevice(f'{dev['server']}.ict.swin.edu.au', dev['username'], dev['password']),
                                   device_type=re.search(r'(Router)|^Switch|^ASA', dev['device']).group(0).lower(),
                                   description=f'{dev["room"]}:{dev["enclosure"]}-{dev["kit"]}-{dev["device"]}',
                                   full_description=f'{dev['room']}: {dev['fullname']}',
                                   log_queue=log_queue,
                                   update_queue=progress_queue)
                     for dev in result.values() if any(map(dev['device'].startswith, ['Router', 'Switch', 'ASA']))]

        for p in processes: p.register_action('erase')

        logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                            handlers=[rich.logging.RichHandler(markup=True, console=console)],
                            level=getattr(logging, arguments.debug)
                            )

        # Execute all processes using the MultiDeviceManager with a timeout of 30 seconds
        test = MultiDeviceManager(console, log_queue=log_queue, progress_queue=progress_queue)
        test.set_process_list(processes)
        test.execute_processes(30,
                               'Multi Device Test',
                               'test',
                               True,
                               )

    except SmartRackTUI.TerminateApp:
        console.clear()
        console.print(Panel('Terminating SmartRack Multi-Device Control Test Suite', style='bold red'))

    except MultiDeviceManager.TerminateManager as e:
        # Not all devices passed the test
        console.print()
        console.rule(e.args[0])
        outcome_tree = Tree(':thumbs_down: [bold red]Failed tasks')
        for msg in e.args[1]: outcome_tree.add(f' :computer: {msg}')
        console.print(outcome_tree)


def parse_arguments() -> argparse.Namespace:
    """
    Parses and returns the command-line arguments for the Swinburne SmartRack Test Suite.

    This function defines the main argument parser for the SmartRack Test Suite, including global and module-specific subcommand configurations.
    :returns: argparse.Namespace: A Namespace object containing the parsed command-line arguments.

    :raises: This function will raise errors related to incorrect command-line argument parsing using argparse.ArgumentParser.
    """
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

    # Create the sub-parsers module
    subparsers = parser.add_subparsers(title='test modules', help='Run one of the following sub-commands to test a particular component of the SmartRack library', required=True)

    # Create individual sub-parsers and extra parameters
    subparsers.add_parser('smartrack', help='Test SmartRack website access', argument_default=smartrack).set_defaults(func=smartrack)
    subparsers.add_parser('ciscodevice', help='Test Cisco Device connection', parents=[connection_parser]).set_defaults(func=ciscodevice)
    dmparser = subparsers.add_parser('devicemanager', help='Test single device collection in sub-process', parents=[connection_parser])
    dmparser.set_defaults(func=devicemanager)
    dmparser.add_argument('-t', '--type', choices=['router', 'switch'], default='router', help='Specify the type of device to test collection (default: %(default)s)')
    dmparser.add_argument('-o', '--output_dir', default='test_collect', help='Directory to store captured output to (default: %(default)s)')
    subparsers.add_parser('multidevice', help='Test connecting to - and working with - multiple devices in parallel', argument_default=smartrack).set_defaults(func=multidevice)

    return parser.parse_args()


if __name__ == '__main__':
    console = rich.console.Console()
    try:
        # Parse all command line arguments, if the '-c' argument exists, load the Configuration file now, otherwise it will be loaded by the submodules using default properties
        arguments = parse_arguments()
        if arguments.config_file: Configuration(arguments.config_file)

        # Run the test module as indicated by func
        arguments.func(arguments, console)

    except KeyboardInterrupt as err:
        pass
    except CiscoDevice.AuthError as err:
        console.print()
        console.print(Panel(f'ERROR: {err}', style='bold red'))
    except (Exception,):
        console.print_exception()
