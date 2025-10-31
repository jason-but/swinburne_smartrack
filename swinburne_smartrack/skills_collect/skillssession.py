# Import System Libraries
import logging
import pathlib
import dialog
import rich
import rich.logging

from rich.panel import Panel

# Import SmartRackLibrary modules
from swinburne_smartrack import SmartRackTUI
from . import SkillsCollect


class SkillsSession:
    def __init__(self, console: rich.console.Console, exam_config: dict, solution_file: pathlib.Path, preset_options: dict[str, str] = None):
        """
        Initializes an instance of the SkillsExam class, which manages the entire Skills Exam Collection process.

        :param console: The application instance of the Rich Console class.
        :param exam_config: Exam configuration dictionary loaded from configuration TOML file.
        :param solution_file: Path to the file containing the exam solution.
        :param preset_options: Exam options configured at the command line to automatically set for all students.
        """
        self.__console = console
        self.__log = logging.getLogger('ExamCollectManager')
        self.__log.info('Constructing Class')

        self.__dialog = dialog.Dialog()

        self.__exam_details = exam_config['details']
        self.__exam_collect_timeout = exam_config['collect']['timeout']
        self.__expected_devices = [name for name in exam_config['collect'] if name != 'timeout']
        self.__exam_extra_commands = {name: exam_config['collect'][name].get('extra', []) for name in self.__expected_devices}
        self.__exam_options = exam_config.get('options', {})
        self.__solution_file = pathlib.Path(solution_file)
        self.__preset_options = preset_options

        self.__devices = {}
        self.__missing_devices = {}

    def _validate_downloaded_devices(self, downloaded_devices: dict[str, dict[str, str]]) -> None:
        """
        Validates the provided filtered device database for correctness.

        Populate self.__devices as a dictionary of device information for exam. Key is student_id mapping to a dictionary. This dictionary maps the exam
        device name to a dictionary that is passed to DeviceManager to manage the device. Dictionary should be filtered to only device names from exam
        configuration file.

        We then validate that self.__devices contains a full suite of device information for all students, missing entries are logged in self.__missing_devices

        :param downloaded_devices: Dictionary as returned by SmartRackTUI of all booked devices. Dictionary should be filtered to only device names from exam
                                   configuration file.
        """
        self.__devices = {}
        for name, details in downloaded_devices.items():
            if details['student'] not in self.__devices: self.__devices[details['student']] = {}
            self.__devices[details['student']][details['nickname']] = details

        self.__missing_devices = {}
        for student, details in self.__devices.items():
            missing = [name for name in self.__expected_devices if name not in details.keys()]
            if len(missing) > 0: self.__missing_devices[student] = missing

    def _retrieve_devices(self) -> dict[str, dict[str, dict[str, str]]]:
        """
        Use SmartRackTUI to access the SmartRack system and download all booked device information. Filter list to match exam configuration in
        self.__expected_devices. Return the database of all booked devices that belong to this Exam session.

        :return: Dictionary of device information for exam. Key is student_id mapping to a dictionary. This dictionary maps the exam device name to
                 a dictionary that is passed to DeviceManager to manage the device.
        """
        while len(self.__devices) == 0 or len(self.__missing_devices) > 0:
            self.__log.info(f'Access SmartRack and download details for all booked devices')
            tui = SmartRackTUI(self.__console)
            smartrack = tui.ui('Please select which rooms this exam will be running in.')
            self._validate_downloaded_devices(smartrack.filter_nickname(self.__expected_devices))

            if len(self.__missing_devices) > 0:
                self.__log.info(f'Not all students have devices booked within SmartRack, try again')
                message: list[str] = ['', 'Some students appear to not have devices booked within SmartRack.', '']
                message.extend([f'{student}: {','.join(details)}' for student, details in self.__missing_devices.items()])
                message.extend(['', 'Please check within SmartRack, and then choose whether to try again.'])

                if self.__dialog.yesno('\n'.join(message), title=' SmartRack Device Booking Problem ', width=40, height=len(message) + 7) != self.__dialog.OK:
                    raise Exception(f'ERROR: Problem with SmartRack Device Booking Problem.')

        self.__log.debug(f'Exam devices: {self.__devices}')
        return self.__devices

    def run_exam(self) -> None:
        """

        :return:
        """
        self.__log.info('Running Exam Collection')
        self._retrieve_devices()

        exam_session = SkillsCollect(device_db=self.__devices, exam_details=self.__exam_details, extra_commands=self.__exam_extra_commands,
                                     solution_file=self.__solution_file, exam_options=self.__exam_options, preset_options=self.__preset_options)

        # Configure the logger
        logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                            handlers=[rich.logging.RichHandler(markup=True, console=self.__console)],
                            )

        # Collect all student work, loop until complete
        while exam_session.pending_collections() > 0:
            self.__log.info(f'Remaining devices to collect {exam_session.pending_collections()}')
            exam_session.collect(self.__exam_collect_timeout)

        self.__console.clear()
        self.__console.print(Panel('Finished collection', style='bold green'))
        self.__console.print()
