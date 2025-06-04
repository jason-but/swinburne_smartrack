import logging
import pathlib
import multiprocessing
import re
import shutil
import configparser

import tomli_w
import dialog

from swinburne_smartrack import Configuration, CiscoDevice, DeviceManager

class StudentCollect:
    def __init__(self, student_id: str, session_dir: pathlib.Path, devices: dict[str, dict[str, str]], log_queue: multiprocessing.Queue, update_queue: multiprocessing.Queue, exam_options: dict[str, list[str]] = None, preset_options: dict[str, str] = None):
        """

        :param student_id: String containing the student ID to manage collections for.
        :param session_dir: Base directory where all student collections in this session are stored.
        :param devices: Database of device connection and information details to collect.
        :param update_queue: A multiprocessing Queue to return progress updates to the main process.
        :param log_queue: A multiprocessing Queue for passing log messages handled by the logging system.
        :param exam_options: Dictionary mapping exam options to allowed values.
        :param preset_options: Dictionary mapping preset options to configured value.
        """
        self.__log = logging.getLogger('StudentCollect')
        self.__log.info('Constructing Class')

        self.__dialog = dialog.Dialog()

        self.__student_id = student_id
        self.__base_collect_dir = pathlib.Path(session_dir, student_id)
        self.__devices = devices
        self.__exam_options = exam_options

        self.__options = preset_options if preset_options is not None else {}

        self.__processes: dict[str, DeviceManager] = {}
        for device, details in devices.items():
            self.__processes[device] = DeviceManager(device=CiscoDevice(f'{details['server']}.ict.swin.edu.au', details['username'], details['password']),
                                                     device_type=re.search(r'(Router)|^Switch|^ASA', details['device']).group(0).lower(),
                                                     description=f'{details["room"]}:{details["enclosure"]}-{details["kit"]}-{details["device"]}',
                                                     full_description=f'{student_id}({device})\t- {details['room']}: {details['fullname']}',
                                                     update_queue=update_queue,
                                                     log_queue=log_queue,
                                                     usernames=Configuration().manage['usernames'] if 'usernames' in Configuration().manage else None,
                                                     passwords=Configuration().manage['passwords'] if 'passwords' in Configuration().manage else None
                                                     )

            # Register to actions on newly created process
            self.__processes[device].register_action('collect', out_dir=pathlib.Path(self.__base_collect_dir, device))
            self.__processes[device].register_action('erase')

    def _copy_solution(self, solution: pathlib.Path) -> None:
        """
        Copy the provided exam solution configuration file to the student collection directory.

        :param solution: Path of solution configuration file to copy to student collection directory.
        """
        self.__log.info(f'Copying Solution file "{solution}" to "{self.__base_collect_dir}"')
        shutil.copyfile(solution, pathlib.Path(self.__base_collect_dir, 'solution.ini'))

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

        self.__log.info('Creating TOML file')
        with open(pathlib.Path(self.__base_collect_dir, 'options.toml'), 'wb') as file:
            tomli_w.dump(self.__options, file)

    def clean_complete_processes(self) -> None:
        self.__processes = {device: proc.recreate() for device, proc in self.__processes.items() if not proc.finished}

    def ask_options(self) -> None:
        """
        Ask user via radio list dialog box to set each available exam option value:
         - Options from self.__exam_options
         - Pre-set option from self.__options not queried
         - User results stored in self.__options
        """
        for option, possible in self.__exam_options.items():
            # If option pre-set, continue
            if option in self.__options: continue

            while True:
                code, value = self.__dialog.radiolist(f'Select exam configuration details for "{option}"',
                                                      title=f'Exam options for {self.__student_id}',
                                                      no_cancel=True,
                                                      choices=[(opt, opt, False) for opt in possible]
                                                      )

                # Exit loop if valid option is set
                if code == self.__dialog.OK and value in possible: break;

            # Store selected option
            self.__options[option] = value

    def finalise(self, solution: pathlib.Path) -> None:
        """
        :param solution: Path of solution configuration file to copy to student collection directory.
        """
        self.__log.info('Finalising files in student collection directory')
        self._copy_solution(solution)
        self._save_options()

    @property
    def devices_to_collect(self) -> list[str]:
        return [device for device in self.__processes.keys()]

    @property
    def processes(self) -> list[DeviceManager]:
        return [proc for proc in self.__processes.values()]

    @property
    def options(self) -> str:
        if self.__options is None: return '--- Not set ---'
        return ' '.join([f'{option}({value})' for option, value in self.__options.items()])