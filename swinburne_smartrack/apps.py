import argparse
import logging
import os
import re
import multiprocessing
import calendar
from argparse import ArgumentTypeError

import rich
import rich.logging
from rich import box
from rich.panel import Panel
from rich.tree import Tree
from rich.console import Group
from rich.syntax import Syntax
from rich.table import Table

from swinburne_smartrack import Configuration, SmartRackTUI, CiscoDevice, DeviceManager, MultiDeviceManager
from swinburne_smartrack.devicemanager import DeviceActionCompleteEnum
from swinburne_smartrack.skills_collect import SkillsSession, validate_exam_toml, ValidateError


# ---------- ArgParse Validators ----------
class ValidFile:
    """
    Provides a callable object to validate if a given file path exists.

    This class is designed to be used for validating file paths in the context of command-line argument parsing. When an instance of this class is called
    with a file path, it checks if the file exists on the filesystem. If the file does not exist, it raises an error suitable for argument parsing utilities.
    """
    def __call__(self, arg) -> str:
        if not os.path.isfile(arg): raise argparse.ArgumentTypeError(f'Nominated file "{arg}" does not exist.')
        return arg


class ArgParseDictAppend(argparse.Action):
    """
    Provides a callable object to create a new ArgParse action. ArgParseDictAppend will parse a CLI option of the form "key=value". The key/value pair will be
    appended to a dictionary for the nominated option.
    """
    def __call__(self, parser, namespace, values, option_string=None):
        """
        Parse command line option as key=value and append to dictionary for name.

        :param parser: ArgParse instance, used to send errors back to the parser.
        :param namespace: Current parsed parameters.
        :param values: Current option being parsed.
        :param option_string: Actual option (e.g. --option)
        """
        # Get the pre-existing parameter dictionary
        current_values = getattr(namespace, self.dest)
        # If no dictionary (current_values == None), create an empty dictionary
        if current_values is None: current_values = {}
        # Split parameter to key=value pair and add to dictionary
        try:
            key, value = values.split('=', 1)
            current_values[key] = value
        except ValueError:
            parser.error(f'Invalid parameter "{option_string} {values}" is invalid (should be "{option_string} key=value").')

        # Save dictionary back to namespace
        setattr(namespace, self.dest, current_values)


# ---------- APPLICATION: smartrack_config ----------
def smartrack_config_argparse() -> argparse.Namespace:
    """
    Parses and returns the command-line arguments for the smartrack_config application.

    Configured parameters:
     - config-file: The path to the configuration file to be used by the application, defaults to system configuration.

    :returns: argparse.Namespace: A Namespace object containing the parsed command-line arguments.

    :raises: This function will raise errors related to incorrect command-line argument parsing using argparse.ArgumentParser.
    """
    # Create the main parser with global CLI parameters
    parser = argparse.ArgumentParser(description='Swinburne SmartRack Config\n\nDisplay default configuration information for SmartRack applications',
                                     formatter_class=argparse.RawTextHelpFormatter,
                                     allow_abbrev=False,
                                     epilog='This is a utility program in the swinburne_smartrack Python package.'
                                     )
    parser.add_argument('-c', '--config-file', type=ValidFile(), help='specify the smartrack configuration file (default: system configuration)')

    return parser.parse_args()


def smartrack_config() -> None:
    """
    Function executed when installed application smartrack_config is executed

    Displays default SmartRack configuration information.
     - Loads the configuration file
     - Uses Rich to display information in a neatly organized way.

    """
    console = rich.console.Console()

    try:
        # Parse all command line arguments, if the '-c' argument exists load the Configuration file now, otherwise it will be loaded by the submodules using default properties
        arguments = smartrack_config_argparse()
        if arguments.config_file: Configuration(arguments.config_file)

        console.print(Panel('Cisco Smartrack Configuration', style='bold green'))
        console.print()

        # Display server information
        console.rule('SmartRack Servers descriptions and URLs')
        for server, value in Configuration().smartrack_servers.items():
            server_tree = Tree(f'⚙️ {server} ({value['description']})')
            server_tree.add(f':earth_asia: {value['url']}')
            console.print(server_tree)
        console.print()

        # Display Device Management information
        console.rule('Automated Cisco Device Management')

        # Authentication configuration
        auth_config = [(device_type, parameters) for device_type, parameters in Configuration().manage.items() if device_type in ['usernames', 'passwords']]
        action_config = [(device_type, parameters) for device_type, parameters in Configuration().manage.items() if device_type not in ['usernames', 'passwords']]

        if len(auth_config) > 0:
            auth_tree = Tree('🔒 Default authentication parameters')
            if 'usernames' in Configuration().manage:
                auth_tree.add(Group(f'👨‍ Usernames:', Syntax('\n'.join(Configuration().manage["usernames"]), 'null', theme='monokai', line_numbers=True)))
            if 'passwords' in Configuration().manage:
                auth_tree.add(Group(f'🔑 Passwords:', Syntax('\n'.join(Configuration().manage["passwords"]), 'null', theme='monokai', line_numbers=True)))
            console.print(auth_tree)
            console.print()

        if len(action_config) > 0:
            action_tree = Tree('🏃 Default action commands for device types')
            for device_type, parameters in Configuration().manage.items():
                if device_type in ['usernames', 'passwords']: continue
                m_branch = action_tree.add(f'🔀 {device_type}')
                cmd_table = Table(show_lines=True, expand=True)
                for action in parameters.keys(): cmd_table.add_column(action, ratio=1)

                cmd_table.add_row(*[Syntax('\n'.join(cmd), 'null', theme='monokai', line_numbers=True) for cmd in parameters.values()])

                m_branch.add(cmd_table)

            console.print(action_tree)
        else:
            console.print(Panel('ERROR: No device actions configured in system configuration', style='bold red'))

        console.print()

        # Display Skills Exam information
        console.rule('Skills Collection Configuration')

        # Display Collection Directories
        directory_table = Table('Option Name', 'Possible Values', title='📂 Collected file locations', title_style='bold yellow',
                                title_justify="left", show_lines=False, box=box.HORIZONTALS)

        directory_table.add_row('[bold green] 📂 Base directory for exam collection:',
                                Configuration().skills.get('base_dir', '❗ [bold red]ERROR: No \'base_dir\' value configured in \[skills] section of system configuration'))

        directory_table.add_row('[bold green] 👨‍🎓 Student collection sub-folder:',
                                '<unit_name>/<year_sem>/<shortname>/<session_name>/<student_id>')

        directory_table.add_row('[bold green] 💡 File containing exam solution/requirements:',
                                Configuration().skills.get('requirements_file', '❗ [bold red]ERROR: No \'requirements_file\' value configured in \[skills] section of system configuration'))

        directory_table.add_row('[bold green] 📝 File containing exam details:',
                                Configuration().skills.get('information_file', '❗ [bold red]ERROR: No \'information_file\' value configured in \[skills] section of system configuration'))

        console.print(directory_table)
        console.print()

        # Display Semester Mapping Calendar
        if 'semester_map' in Configuration().skills:
            semester_tree = Tree(':calendar: Semester Suffix in collection directory based on current Month')
            semester_table = Table('[bold green]Month:', *list(calendar.month_abbr)[1:], show_lines=True)
            semester_tree.add(semester_table)
            semester_table.add_row('[bold green]Suffix:', *Configuration().skills['semester_map'])
            console.print(semester_tree)
        else:
            console.print(Panel('ERROR: No \'semester_map\' value configured in [skills] section of system configuration', style='bold red'))

        console.print()

    except (Exception,):
        # Use the rich console to display any other exceptions
        console.print_exception()


# ---------- APPLICATION: smartrack_clean ----------
def smartrack_clean_argparse() -> argparse.Namespace:
    """
    Parses and returns the command-line arguments for the smartrack_clean application.

    Configured parameters:
     - config-file: The path to the configuration file to be used by the application, defaults to system configuration.
     - timeout: The timeout in seconds for the clean operation, defaults to 120 seconds.

    :returns: argparse.Namespace: A Namespace object containing the parsed command-line arguments.

    :raises: This function will raise errors related to incorrect command-line argument parsing using argparse.ArgumentParser.
    """
    # Create the main parser with global CLI parameters
    parser = argparse.ArgumentParser(description='Swinburne SmartRack Clean\n\nDelete all stored configurations on all booked devices',
                                     formatter_class=argparse.RawTextHelpFormatter,
                                     allow_abbrev=False,
                                     epilog='This is a utility program in the swinburne_smartrack Python package.'
                                     )
    parser.add_argument('-c', '--config-file', type=ValidFile(), help='specify the smartrack configuration file (default: system configuration)')
    parser.add_argument('-t', '--timeout', type=int, default=120, help='timeout in seconds to clean devices (default: %(default)s) seconds')

    return parser.parse_args()


def smartrack_clean() -> None:
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
    """
    console = rich.console.Console()

    try:
        # Parse all command line arguments, if the '-c' argument exists load the Configuration file now, otherwise it will be loaded by the submodules using default properties
        arguments = smartrack_clean_argparse()
        if arguments.config_file: Configuration(arguments.config_file)

        # Access SmartRack and download details for all booked devices
        tui = SmartRackTUI(console)
        smartrack = tui.ui('Please select which rooms with booked devices you would like to clean.')
        devices = smartrack.filter()

        console.print()
        console.print(f' :fast_forward: Downloaded connection information for {len(devices)} devices')

        # This queue holds log messages from the worker threads
        log_queue = multiprocessing.Queue(-1)

        # This queue holds status updates from the worker threads
        progress_queue = multiprocessing.Queue()  # Queue used for reporting progress

        # Create a DeviceManager sub-process in the processes list IF the device name starts with "Router", "Switch", or "ASA"
        processes = [DeviceManager(device=CiscoDevice(f'{dev['server']}.ict.swin.edu.au', dev['username'], dev['password'], ),
                                   device_type=re.search(r'(Router)|^Switch|^ASA', dev['device']).group(0).lower(),
                                   description=f'{dev["room"]}:{dev["enclosure"]}-{dev["kit"]}-{dev["device"]}',
                                   full_description=f'{dev['room']}: {dev['fullname']}',
                                   log_queue=log_queue,
                                   update_queue=progress_queue,
                                   usernames=Configuration().manage['usernames'] if 'usernames' in Configuration().manage else [],
                                   passwords=Configuration().manage['passwords'] if 'passwords' in Configuration().manage else []
                                   )
                     for dev in devices.values() if any(map(dev['device'].startswith, ['Router', 'Switch', 'ASA']))]

        # Register to delete all configurations for all processes
        for process in processes: process.register_action('erase')

        # Configure the logger
        logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                            handlers=[rich.logging.RichHandler(markup=True, console=console)],
                            )

        # Create the MultiDeviceManager instance and execute all processes in loop until complete
        manager = MultiDeviceManager(console, log_queue=log_queue, progress_queue=progress_queue)
        manager.set_process_list(processes)
        manager.execute_processes(timeout=arguments.timeout,
                                  title='Cleaning Devices',
                                  action='clean',
                                  run_once=False,
                                  ui_action_items=[DeviceActionCompleteEnum.CONNECTED, DeviceActionCompleteEnum.ENABLE, DeviceActionCompleteEnum.ERASED, DeviceActionCompleteEnum.FINISHED]
                                  )

    except SmartRackTUI.TerminateApp:
        # User terminated application while providing SmartRack details
        console.clear()
        console.print(Panel('Terminating SmartRack Device Cleaning Application', style='bold red'))

    except MultiDeviceManager.TerminateManager as e:
        # User terminated application after some processes failed
        console.clear()
        console.print(Panel(e.args[0], style='bold red'))
        console.print()
        console.print('[bold red]Unsuccessful devices:')
        for msg in e.args[1]: console.print(f' :computer: {msg}')
        console.print()

    except KeyboardInterrupt:
        # Ignore keyboard interrupt
        pass

    except (Exception,):
        # Use the rich console to display any other exceptions
        console.print_exception()


# ---------- APPLICATION: skills_validate_config ----------
def skills_validate_config_argparse() -> argparse.Namespace:
    """
    Parses and returns the command-line arguments for the skills_validate_config application.

    Configured parameters:
     - exam-config: The path to the Exam TOML configuration file to be validated.

    :returns: argparse.Namespace: A Namespace object containing the parsed command-line arguments.

    :raises: This function will raise errors related to incorrect command-line argument parsing using argparse.ArgumentParser.
    """
    # Create the main parser with global CLI parameters
    parser = argparse.ArgumentParser(description='Swinburne Skills Exam\n\nCollect student configurations for the Cisco Skills Assessments',
                                     formatter_class=argparse.RawTextHelpFormatter,
                                     allow_abbrev=False,
                                     epilog='This is a utility program in the swinburne_smartrack Python package.'
                                     )
    parser.add_argument('exam_config', type=ValidFile(), help='exam configuration file to be used for student collection - toml format')

    return parser.parse_args()


def skills_validate_config() -> None:
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
    """
    console = rich.console.Console()

    try:
        # Parse all command line arguments
        arguments = skills_validate_config_argparse()

        # Parse the Exam configuration file and extract device nicknames to collect
        exam_config = validate_exam_toml(arguments.exam_config)

        console.print(Panel(f'SmartRack Exam Configuration File Validation - "{arguments.exam_config}"', style='bold green'))
        console.print()

        console.rule('Exam Information')
        console.print()

        # Table with basic exam information
        details_table = Table(title='📓 Exam Details', title_style='bold yellow', title_justify="left", show_lines=False, show_header=False, box=box.HORIZONTALS)
        details_table.add_row('[bold green]Exam Name:', exam_config['details']['name'])
        details_table.add_row('[bold green]Unit Code:', exam_config['details']['unitcode'])
        details_table.add_row('[bold green]Exam Short Name:', exam_config['details']['shortname'])
        console.print(details_table)

        console.print()

        # If options are present, table with option information
        if 'options' in exam_config:
            options_table = Table('Option Name', 'Possible Values', title='❓ Exam Options', title_style='bold yellow', title_justify="left", show_lines=False, box=box.HORIZONTALS)
            for option, values in exam_config['options'].items():
                options_table.add_row(f'[bold green]{option}', ', '.join(values))

            console.print(options_table)
            console.print()

        console.rule('Device Collection Information')
        console.print()

        # Collection timeout
        console.print(f'⏰ [bold yellow]Collection timeout:[/] {exam_config["collect"]["timeout"]} seconds.')
        console.print()

        # Device collection information
        device_tree = Tree('⚙️ [bold yellow]Devices to collect')
        for device_name, parameters in exam_config['collect'].items():
            if device_name == 'timeout': continue
            device_node = device_tree.add(f'🔀 [bold blue]{device_name}[/] (type=[bold green]{parameters["type"]}[/])')
            if 'extra' in parameters:
                device_node.add(Group('🔤 [bold blue]Extra commands to collect', Syntax('\n'.join(parameters['extra']), 'null', theme='monokai', line_numbers=True)))

        console.print(device_tree)
        console.print()

    except KeyboardInterrupt:
        # Ignore keyboard interrupt
        pass

    except ArgumentTypeError as err:
        console.print(f'[bold red]ERROR: {err}')

    except ValidateError as err:
        console.print(f'[bold red]Validation Error:', err)

    except (Exception,):
        # Use rich to display any other exceptions
        console.print_exception()


# ---------- APPLICATION: skills_collect ----------
def skills_collect_argparse() -> argparse.Namespace:
    """
    Parses and returns the command-line arguments for the smartrack_clean application.

    Configured parameters:
     - config-file: The path to the configuration file to be used by the application, defaults to system configuration.
     - timeout: The timeout in seconds for the clean operation, defaults to 120 seconds.

    :returns: argparse.Namespace: A Namespace object containing the parsed command-line arguments.

    :raises: This function will raise errors related to incorrect command-line argument parsing using argparse.ArgumentParser.
    """
    # Create the main parser with global CLI parameters
    parser = argparse.ArgumentParser(description='Swinburne Skills Exam\n\nCollect student configurations for the Cisco Skills Assessments',
                                     formatter_class=argparse.RawTextHelpFormatter,
                                     allow_abbrev=False,
                                     epilog='This is a utility program in the swinburne_smartrack Python package.'
                                     )
    parser.add_argument('-c', '--config-file', type=ValidFile(), help='specify the smartrack configuration file (default: system configuration)')
    parser.add_argument('-o', '--options', action=ArgParseDictAppend, metavar='option=value', help='specify pre-set values for exam options for all students')
    parser.add_argument('exam_config', type=ValidFile(), help='exam configuration file to be used for student collection - toml format')
    parser.add_argument('solution', type=ValidFile(), help='exam solution file to be placed in collection directory')

    return parser.parse_args()


def skills_collect() -> None:
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
    """
    console = rich.console.Console()

    try:
        # Parse all command line arguments, if the '-c' argument exists load the Configuration file now, otherwise it will be loaded by the submodules using default properties
        arguments = skills_collect_argparse()

        if arguments.config_file: Configuration(arguments.config_file)

        # Parse the Exam configuration file and extract device nicknames to collect
        exam_config = validate_exam_toml(arguments.exam_config)

        if arguments.options is not None:
            assert 'options' in exam_config, f'Exam option specified but EXAM TOML Configuration file does not contain [options] section'

            for key, value in arguments.options.items():
                assert key in exam_config['options'], f'Option key "{key}" does not exist in EXAM TOML Configuration file'
                assert value in exam_config['options'][
                    key], f'Option value "{value}" is not an allowed value for key "{key}", allowed values are {', '.join(exam_config['options'][key])}'

        skills_session = SkillsSession(console, exam_config, arguments.solution, arguments.options)
        skills_session.run_exam()

    except SmartRackTUI.TerminateApp:
        # User terminated application while providing SmartRack details
        console.clear()
        console.print(Panel('Terminating Skills Exam Collection', style='bold red'))

    except KeyboardInterrupt:
        # Ignore keyboard interrupt
        pass

    except ArgumentTypeError as err:
        console.print(f'[bold red]ERROR: {err}')

    except ValidateError as err:
        console.print(f'[bold red]Validation Error:', err)

    except (Exception,):
        # Use rich to display any other exceptions
        console.print_exception()


if __name__ == '__main__':
    try:
        # For testing purposes, we launch the smartrack_config applications
        smartrack_config()

    except KeyboardInterrupt as err:
        pass
    except (Exception,):
        rich.console.Console().print_exception()
