import argparse
# Import Libraries
# re           - Regular Expressions
# logging      - Python logging module
# rich.console - Text UI Console (from rich package)
# dialog       - System dialog wrapper (from pythondialog package)
# requests     - HTTP/HTTPS Client
import re
import logging

import multiprocessing

from swinburne_smartrack import MultiDeviceManager
# Import swinburne_smartrack submodules
from .config import Configuration
from .devicemanager import DeviceManager, DeviceActionCompleteEnum
from .ciscodevice import CiscoDevice
from .smartracktui import SmartRackTUI

import rich.console
import rich.logging
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree


# TODO: Clean up imports
# TODO: Add  "all"
# TODO: Think about how logging is handled in this file

def display_booked_devices(result: dict[str, dict[str, str]], console: rich.console) -> None:
    console.print()
    console.rule('Displaying booked device details')

    table = Table(show_header=True, header_style="bold green", title="Booked Devices", show_lines=True)
    table.add_column("Room", style="green")
    table.add_column("Device", style="green")
    table.add_column("Server", style="cyan")
    table.add_column("Username", style="cyan")
    table.add_column("Password", style="red")

    for details in result.values():
        table.add_row(details['room'], details['fullname'], details['server'], details['username'], details['password'])

    console.print(table)


def smartrack(arguments: argparse.Namespace, console: rich.console) -> None:
    logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                        handlers=[rich.logging.RichHandler(markup=True, console=console)],
                        level=getattr(logging, arguments.debug)
                        )

    logger = logging.getLogger('')

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
    try:
        tui = SmartRackTUI(console)
        smartrack = tui.ui('Please select which rooms you would like to test this library with')
    except SmartRackTUI.TerminateApp:
        console.clear()
        console.print(Panel('Terminating SmartRack Multi-Device Control Test Suite', style='bold red'))
        return

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

    logger = logging.getLogger('')

    test = MultiDeviceManager(console, log_queue=log_queue, progress_queue=progress_queue)
    test.set_process_list(processes)

    success, unsuccess = test.run_processes(15,
                                            [DeviceActionCompleteEnum.CONNECTED, DeviceActionCompleteEnum.ENABLE, DeviceActionCompleteEnum.ERASED, DeviceActionCompleteEnum.FINISHED]
                                            )

    console.print()
    console.rule('Test Complete - Displaying Results')

    outcome_tree = Tree(':checkered_flag: [bold blue]Test Results')

    s = outcome_tree.add(':thumbs_up: [bold green]Successful completions')
    if len(success) == 0:
        s.add(':crying_face: [red]None')
    else:
        for task in success: s.add(f':computer: {task.full_description}')

    u = outcome_tree.add(':thumbs_down: [bold red]Failed tasks')
    if len(success) == 0:
        u.add(':beaming_face_with_smiling_eyes: [bold yellow]None')
    else:
        for task in unsuccess: u.add(f':computer: {task.full_description}')

    console.print(outcome_tree)


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
    dmparser = subparsers.add_parser('devicemanager', help='Test single device collection in sub-process', parents=[connection_parser])
    dmparser.set_defaults(func=devicemanager)
    dmparser.add_argument('-t', '--type', choices=['router', 'switch'], default='router', help='Specify the type of device to test collection (default: %(default)s)')
    dmparser.add_argument('-o', '--output_dir', default='test_collect', help='Directory to store captured output to (default: %(default)s)')
    subparsers.add_parser('multidevice', help='Test connecting to - and working with - multiple devices in parallel', argument_default=smartrack).set_defaults(func=multidevice)

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
