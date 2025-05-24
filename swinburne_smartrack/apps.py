import argparse
import logging
import re
import multiprocessing

import rich
import rich.logging
from rich.panel import Panel
from rich.tree import Tree

from swinburne_smartrack import Configuration, SmartRack, SmartRackTUI, CiscoDevice, DeviceManager, MultiDeviceManager
from swinburne_smartrack.devicemanager import DeviceActionCompleteEnum


def clean_devices(manager: MultiDeviceManager, processes: list[DeviceManager], timeout: int, console: rich.console) -> list[DeviceManager]:
    console.print()
    console.rule('Cleaning Devices')
    console.print(f' :computer: Attempting to clean {len(processes)} devices')
    console.print(f' :alarm_clock: Timeout = {timeout} seconds')
    console.print()

    # Run all processes with the specified timeout
    manager.set_process_list(processes)
    successful, unsuccessful = manager.run_processes(timeout,
                                                     [DeviceActionCompleteEnum.CONNECTED, DeviceActionCompleteEnum.ENABLE, DeviceActionCompleteEnum.ERASED, DeviceActionCompleteEnum.FINISHED]
                                                     )

    # Print successful outcomes
    console.print()
    console.print(f' :crying_face: [bold red]No devices were successfully cleaned' if len(successful) == 0 else f' :thumbs_up: [bold green]{len(successful)} devices were successfully cleaned')

    if len(unsuccessful) > 0:
        # Display unsuccessful outcomes
        console.print()
        console.print('[bold red]Unsuccessful devices:')
        for task in unsuccessful: console.print(f' :computer: {task.full_description}')
        console.print()

    return [process.recreate() for process in unsuccessful]


def smartrack_clean(arguments: argparse.Namespace, console: rich.console) -> None:
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
        smartrack = tui.ui('Please select which rooms with booked devices you would like to clean.')
        devices = smartrack.filter()
    except SmartRackTUI.TerminateApp:
        console.clear()
        console.print(Panel('Terminating SmartRack Device Cleaning Application', style='bold red'))
        return

    console.print()
    console.print(f' :fast_forward: Downloaded connection information for {len(devices)} devices')

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
                 for dev in devices.values() if any(map(dev['device'].startswith, ['Router', 'Switch', 'ASA']))]

    for p in processes: p.register_action('erase')

    logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                        handlers=[rich.logging.RichHandler(markup=True, console=console)],
                        )

    for i in range(2):
        # Execute all processes using the MultiDeviceManager with a timeout of 30 seconds, list of unsuccessful processes is used to replace processes
        processes = clean_devices(MultiDeviceManager(console, log_queue=log_queue, progress_queue=progress_queue),
                                  processes,
                                  arguments.timeout,
                                  console
                                  )

        for p in processes: p.register_action('erase')


def parse_arguments() -> argparse.Namespace:
    """
    Parses and returns the command-line arguments for the application.

    Configured parameters:
     - config-file: The path to the configuration file to be used by the application, defaults to system configuration.
     - timeout: The timeout in seconds for the clean operation, defaults to 120 seconds.

    :returns: argparse.Namespace: A Namespace object containing the parsed command-line arguments.

    :raises: This function will raise errors related to incorrect command-line argument parsing using argparse.ArgumentParser.
    """
    # Create the main parser with global CLI parameters
    parser = argparse.ArgumentParser(description='Swinburne SmartRack Clean All Devices',
                                     formatter_class=argparse.RawTextHelpFormatter,
                                     allow_abbrev=False
                                     )
    parser.add_argument('-c', '--config-file',
                        help='Specify the smartrack configuration file (default: system configuration)'
                        )
    parser.add_argument('-t', '--timeout', type=int, default=120, help='Timeout in seconds to clean devices (default: %(default)s)')

    return parser.parse_args()


if __name__ == '__main__':
    console = rich.console.Console()
    try:
        # Parse all command line arguments, if the '-c' argument exists, load the Configuration file now, otherwise it will be loaded by the submodules using default properties
        arguments = parse_arguments()
        if arguments.config_file: Configuration(arguments.config_file)

        # Run the test module as indicated by func
        smartrack_clean(arguments, console)

    except KeyboardInterrupt as err:
        pass
    except (Exception,):
        rich.console.Console().print_exception()
