"""
This module implements the StudentCollect class which is used to manage collection of all configurations for a single student following an exam. The class
creates all support collection files as well.
"""

# Import System Libraries
import logging
import pathlib
import multiprocessing
import re
import shutil
import configparser
import tomlkit
import pyparsing
import dialog

# Import SmartRackLibrary modules
from swinburne_smartrack import Configuration, CiscoDevice, DeviceManager


class StudentCollect:
    """
    Manages exam collection and files in collection directory for a single student

    Maintains a group of DeviceManager instances for each device allocated to the student, also manages setting of exam options and other files to be created
    in the collection directory including 1) Exam options (options.toml), 2) Exam solution (solution.toml), and 3) ....
    """
    def __init__(self, student_id: str, session_dir: pathlib.Path, devices: dict[str, dict[str, str]], log_queue: multiprocessing.Queue, update_queue: multiprocessing.Queue, solution_file: pathlib.Path, extra_commands: dict[str, list[str]], exam_details: dict[str, str], exam_options: dict[str, list[str]] = None, preset_options: dict[str, str] = None):
        """
        Initializes an instance of the StudentCollect class, which manages exam collection for a single student

        :param student_id: String containing the student ID to manage collections for.
        :param session_dir: Base directory where all student collections in this session are stored.
        :param devices: Database of device connection and information details to collect.
        :param update_queue: A multiprocessing Queue to return progress updates to the main process.
        :param log_queue: A multiprocessing Queue for passing log messages handled by the logging system.
        :param solution_file: Path to the file containing the exam solution.
        :param extra_commands: Dictionary mapping exam device name to a list of strings containing additional commands to execute/collect for that device.
        :param exam_details: Exam parameters extracted from the exam configuration file. Contains information to construct directory to collect exam to.
        :param exam_options: Dictionary mapping exam options to allowed values.
        :param preset_options: Dictionary mapping preset options to configured value.
        """
        self.__log = logging.getLogger('StudentCollect')
        self.__log.info('Constructing Class')

        self.__dialog = dialog.Dialog()

        self.__student_id = student_id
        self.__base_collect_dir = pathlib.Path(session_dir, student_id)
        self.__devices = devices
        self.__solution_file = solution_file
        self.__exam_options = exam_options

        # Store exam name for later saving in exam information file
        self.__exam_information = {'Information': {'name': exam_details['name']}}

        # Extract rubric information from the solution file and add to self.__exam_information
        # pyparser class to handle an integer and convert to int type
        int_parser = pyparsing.Word(pyparsing.nums)
        int_parser.setParseAction(lambda x: int(x[0]))

        # pyparser class to handle a label
        label_parser = pyparsing.Word(pyparsing.alphanums + '_')

        # pyparser to handle a comma separated list of colon separated lists
        # - Each colon separated list begins with a label, followed by a list of integers
        parameters_parser = pyparsing.DelimitedList(pyparsing.Group(pyparsing.DelimitedList(int_parser | label_parser, delim=':')))

        # pyparser to handle a line formatted as "label[label] = parameters"
        # - label within [] stored in "rubric" field, parameters stored in "config" field
        rubric_parser = label_parser + '[' + label_parser('rubric') + pyparsing.Word('[] =') + parameters_parser()('config')

        # Find all lines beginning with "rubric[" in the solution file, extract rubric configuration, and add to self.__exam_information
        with open(self.__solution_file, 'r') as file:
            configs = [rubric_parser.parse_string(line).as_dict() for line in file if line.startswith('rubric[')]
            self.__exam_information['Rubrics'] = {rubric['rubric']: {param[0]: param[1] if len(param) == 1 else param[1:] for param in rubric['config']} for rubric in configs}

        self.__options = preset_options.copy() if preset_options is not None else {}

        # This dictionary maps exam device names to a DeviceManager instance used to manage the collection
        self.__processes: dict[str, DeviceManager] = {}
        for device, details in devices.items():
            self.__processes[device] = DeviceManager(device=CiscoDevice(f'{details['server']}.ict.swin.edu.au', details['username'], details['password']),
                                                     device_type=re.search(r'(Router)|^Switch|^ASA', details['device']).group(0).lower(),
                                                     description=f'{details["room"]}:{details["enclosure"]}-{details["kit"]}-{details["device"]}',
                                                     full_description=f'{student_id}({device})\t- {details['room']}: {details['fullname']}',
                                                     update_queue=update_queue,
                                                     log_queue=log_queue,
                                                     usernames=Configuration().manage['usernames'] if 'usernames' in Configuration().manage else [],
                                                     passwords=Configuration().manage['passwords'] if 'passwords' in Configuration().manage else []
                                                     )

            # Register collect, extra_collect(if there are extra commands to collect) and erase actions on newly created process
            self.__processes[device].register_action('collect', out_dir=pathlib.Path(self.__base_collect_dir, device))
            if len(extra_commands[device]) > 0:
                self.__processes[device].register_action('extra_collect', out_dir=pathlib.Path(self.__base_collect_dir, device), command_list=extra_commands[device])
            self.__processes[device].register_action('erase')

    def _copy_solution(self) -> None:
        """
        Copy the provided exam solution configuration file to the student collection directory.
        """
        self.__log.info(f'Copying Solution file "{self.__solution_file}" to "{self.__base_collect_dir}"')
        shutil.copyfile(self.__solution_file, pathlib.Path(self.__base_collect_dir, Configuration().skills['requirements_file']))

    def _save_options(self) -> None:
        """
        Save user configured exam options to options.toml in student collection directory.
        """
        # Only save options if they exist
        if self.__options is None: return

        self.__log.info(f'Saving options {self.__options} for student {self.__student_id}')

        self.__log.info('Creating INI file')
        config = configparser.ConfigParser()
        config['Student Options'] = self.__options
        with open(pathlib.Path(self.__base_collect_dir, 'options.ini'), 'w') as file:
            config.write(file)

        # Append options to existing exam_information for saving
        self.__exam_information['Options'] = self.__options

        self.__log.info('Creating TOML file')
        with open(pathlib.Path(self.__base_collect_dir, Configuration().skills['information_file']), 'wb') as file:
            tomlkit.dump(self.__exam_information, file)

    def clean_complete_processes(self) -> None:
        """
        Clean the dictionary of DeviceManager instances to only contain entries for failed collections.

        After DeviceManager processes are run, they cannot be re-executed if collection failed or timed-out. All existing entries in self.__processes
        are deleted and replaced with copies **IF** the process did not successfully complete.
        """
        self.__log.info('Removing successful collections from DeviceManager list')
        self.__processes = {device: proc.recreate() for device, proc in self.__processes.items() if not proc.process_complete}

    def update_options(self) -> None:
        """
        Ask user via radio list dialog box to set each available exam option value:
         - Options from self.__exam_options
         - User results stored in self.__options
        """
        self.__log.info(f'Querying exam options for {self.__student_id}')
        for option, possible in self.__exam_options.items():
            self.__log.debug(f'{option}: Possible values({possible})')
            if self.__options.get(option) is not None: self.__log.debug(f'Current value: {option} = {self.__options[option]}')
            while True:
                code, value = self.__dialog.radiolist(f'Select exam configuration details for "{option}"',
                                                      title=f'Exam options for {self.__student_id}',
                                                      no_cancel=True,
                                                      choices=[(item, item, any([True for k, v in self.__options.items() if k == option and v == item])) for item in possible]
                                                      )

                # Exit loop if valid option is set
                if code == self.__dialog.OK and value in possible: break

            # Store selected option
            self.__log.debug(f'New value: {option} = {value}')
            self.__options[option] = value

    def finalise(self) -> None:
        """
        Finalise collection information, copies the solution file **AND** saves selected options to the student collection directory
        """
        self.__log.info('Finalising files in student collection directory')
        self._copy_solution()
        self._save_options()

    @property
    def devices_to_collect(self) -> list[str]:
        """
        Getter for devices to collect.
        :return: List of device names (as strings) not collected for this student.
        """
        return [device for device in self.__processes.keys()]

    @property
    def processes(self) -> list[DeviceManager]:
        """
        Getter for processes to run in MultiDeviceManager. Values (not keys) of self.__processes contains all DeviceManager instances for uncollected devices.
        :return: List of all DeviceManager instances for this student
        """
        return [proc for proc in self.__processes.values()]

    @property
    def get_option_count(self) -> int:
        """
        Number of exam options set. Allows ordering of student numbers based whether options have been configured or not.
        :return: Number of exam options set for this student collection.
        """
        return len(self.__options)

    @property
    def options(self) -> str:
        """
        Representation of student exam options for display purposes.
        :return: String representation of configured exam options.
        """
        if len(self.__options) == 0: return '--- Not set ---'
        return ' '.join([f'{option}({value})' for option, value in self.__options.items()])
