# Import System Libraries
import logging
import pathlib
import multiprocessing
import dialog
import datetime
import getpass

import rich
from rich.panel import Panel

# Import SmartRackLibrary modules
from swinburne_smartrack import Configuration, MultiDeviceManager
from swinburne_smartrack.devicemanager import DeviceActionCompleteEnum

from . import StudentCollect


class SkillsCollect:
    """
    Manages exam collection for an exam session.

    Maintains a group of StudentCollect instances for each student, also manages collection and exam option setting logic for overall exam management.
    """
    class TerminateSkills(Exception):
        """
        This exception is raised when a user chooses to terminate the application.
        """
        pass

    def __init__(self, device_db: dict[str, dict[str, dict[str, str]]], exam_details: dict[str, str], extra_commands: dict[str, list[str]], solution_file: pathlib.Path, exam_options: dict[str, list[str]] = None, preset_options: dict[str, str] = None):
        """
        Initializes an instance of the SkillsCollect class, which manages collection for an entire exam session.

        :param device_db: Dictionary of device information for exam. Key is student_id mapping to a dictionary. This dictionary maps the exam device name to
                          a dictionary that is passed to DeviceManager to manage the device.
        :param exam_details: Exam parameters extracted from the exam configuration file. Contains information to construct directory to collect exam to.
        :param extra_commands: Dictionary mapping exam device name to a list of strings containing additional commands to execute/collect for that device..
        :param solution_file: Path to the file containing the exam solution.
        :param exam_options: Per-student configurable options for the exam.
        :param preset_options: Exam options configured at the command line to automatically set for all students.
        """
        self.__log = logging.getLogger('SkillsCollect')
        self.__log.info('Constructing Class')

        self.__dialog = dialog.Dialog()

        self.__console = rich.console.Console()

        # Set the session name, create default and then ask user. If exam in one room then <room>_<username>_<day>_<time> otherwise <username>_<day>_<time>
        rooms = list(set([f'{details['room']}_' for devs in device_db.values() for details in devs.values()]))
        self.__session_name = self._get_session_name(f'{rooms[0] if len(rooms) == 1 else ''}{getpass.getuser().split('@', 1)[0]}_{datetime.datetime.now().strftime("%a_%H00")}')

        # Define base collection directory for the session
        self.__base_collect_dir = pathlib.Path(Configuration().skills['base_dir'],
                                               exam_details['unitcode'],
                                               f'{datetime.datetime.now().year}_{Configuration().skills['semester_map'][datetime.datetime.now().month - 1]}',
                                               exam_details['shortname'],
                                               self.__session_name
                                               )

        self.__log.info(f'Collection directory for exam: {self.__base_collect_dir}')

        self.__num_devices = len([dev_name for dev in device_db.values() for dev_name in dev.keys()])
        self.__num_students = len(device_db)
        self.__num_options = len(exam_options)

        # This queue holds log messages from the worker threads
        self.__log_queue = multiprocessing.Queue(-1)

        # This queue holds status updates from the worker threads
        self.__progress_queue = multiprocessing.Queue()  # Queue used for reporting progress

        # self.__ui_action_items lists all actions we need to complete. Insert EXTRACOLLECTED after COLLECTED if at least one device has extra commands to collect
        self.__ui_action_items = [DeviceActionCompleteEnum.CONNECTED, DeviceActionCompleteEnum.ENABLE, DeviceActionCompleteEnum.COLLECTED,
                                  DeviceActionCompleteEnum.ERASED, DeviceActionCompleteEnum.FINISHED]
        if sum(len(commands) for commands in extra_commands.values()) > 0:
            self.__ui_action_items.insert(3, DeviceActionCompleteEnum.EXTRACOLLECTED)

        # self.__student_collect is a dictionary mapping one student ID to a StudentCollect object
        self.__student_collect: dict[str, StudentCollect] = {}

        # StudentCollect object is initialized with (student id, base collection directory, dictionary of all devices for THIS student, multi-proc queues and other options
        for student_id, devices in device_db.items():
            self.__student_collect[student_id] = StudentCollect(student_id=student_id,
                                                                session_dir=self.__base_collect_dir,
                                                                devices=devices,
                                                                log_queue=self.__log_queue,
                                                                update_queue=self.__progress_queue,
                                                                solution_file=solution_file,
                                                                extra_commands=extra_commands,
                                                                exam_details=exam_details,
                                                                exam_options=exam_options,
                                                                preset_options=preset_options
                                                                )

        self.__console.clear()

    def _get_session_name(self, default: str) -> str:
        """
        Ask the user if they want to change the default session name. Returns the default or updated name.
        :param default: Default value for the session name.
        :return: String containing the new session name.
        """
        code, result = self.__dialog.inputbox('Please modify the default session name below',
                                              title='Skills Exam Session Name',
                                              width=60,
                                              init=default
                                              )

        if code == self.__dialog.OK: return result
        return default

    def _select_students(self) -> list[str]:
        """
        Ask user to select which students we will try to collect exam configurations for.

        Create a check-list dialog box with all students who have at least one device uncollected. Three options are available on dialog box.

        1) OK - Return a list of selected student IDs to the calling method.
        2) Clear/Select All - Toggle selections for all students.
        3) Quit Application - Raise an exception to terminate collection.
        :return: List of selected student IDs - Method only returns when "OK" is chosen.
        """
        self.__log.info('Select students to collect on this pass')
        select_all: bool = False
        while True:
            code, result = self.__dialog.checklist('Select students to collect work for',
                                                   title=f'Collect Student Configurations',
                                                   width=60,
                                                   choices=[(student_id, ', '.join(student.devices_to_collect), select_all) for student_id, student in
                                                            self.__student_collect.items() if len(student.devices_to_collect) > 0],
                                                   extra_button=True,
                                                   cancel_label='Quit application',
                                                   extra_label='Clear All...' if select_all else 'Select All...'
                                                   )

            # Return list of selected student IDs
            if code == self.__dialog.OK == code and len(result) > 0:
                self.__log.info(f'Selected students {result}')
                return result

            # Collection canceled, raise Exception to caller
            if code == self.__dialog.CANCEL:
                self.__log.info(f'Collection cancelled - terminating collection')
                missing_devices = [f' - {student_id}: ' + ', '.join(student.devices_to_collect) for student_id, student in self.__student_collect.items() if
                                   len(student.devices_to_collect) > 0]
                raise SkillsCollect.TerminateSkills(f'User selected to terminate application, not all devices collected:\n{'\n'.join(missing_devices)}')

            # User chose to select/deselect all students in list
            if code == self.__dialog.EXTRA: select_all = not select_all

    def _set_options(self, student_list: list[str]) -> None:
        """
        Ask user to enter/provide exam options for all students in the provided list of students.

        Create a sorted menu dialog box listing all students sorted by whether exam options have been entered or not. Upon selection of a student, use the
        student StudentCollect instance to query for the actual exam options for that student.

        Once all students have options set, enable a "Finished" button to allow the method to terminate and return to the caller.

        :param student_list: List of students to collect exam options for.
        """
        self.__log.info('Setting exam options for completed collections')
        while True:
            # Create list of tuples containing count of options set and student_id (for id in student_list)
            # Sort will sort by entered options first, then ID
            # Create list of tuples for menu display
            option_details = [(self.__student_collect[student_id].get_option_count, student_id) for student_id in student_list]
            option_details.sort()
            all_entered = sum(self.__num_options in item for item in option_details) == len(student_list)

            code, result = self.__dialog.menu('Select students to collect work for',
                                              title=f'Collect Student Configurations',
                                              width=60,
                                              choices=[(student_id, self.__student_collect[student_id].options) for _, student_id in option_details],
                                              ok_label='Enter details',
                                              no_cancel=not all_entered,
                                              cancel_label='Finished',
                                              )

            # Student selected, allow user to enter/update options
            if code == self.__dialog.OK == code: self.__student_collect[result].update_options()

            # User finished, return to calling function
            if code == self.__dialog.CANCEL:
                self.__log.info('All students have been configured')
                return

    def pending_collections(self) -> int:
        """
        Return number of devices that are yet to be collected.
        :return: Count of uncollected devices - sum of uncollected devices for each student.
        """
        return sum([len(student.devices_to_collect) for student in self.__student_collect.values()])

    def collect(self, timeout: int) -> None:
        # Get list of student IDs to collect on this round, return if no students to collect
        students_to_collect: list[str] = self._select_students()

        self.__console.clear()

        # Create list of DeviceManager processes for selected students
        # - Inner list comprehension returns list containing lists of DeviceManager instances (where student is selected)
        # - Outer list comprehension unrolls the list of lists into a single list
        processes = [item for sublist in [student.processes for student_id, student in self.__student_collect.items() if student_id in students_to_collect] for item in sublist]

        # Create a MultiDeviceManager to collect ALL selected devices, loop until all collected OR user chooses to cancel (following timeout)
        try:
            self.__log.info(f'Running MultiDeviceManager to collect for {len(processes)} students')
            manager = MultiDeviceManager(self.__console, log_queue=self.__log_queue, progress_queue=self.__progress_queue)
            manager.set_process_list(processes)
            manager.execute_processes(timeout=timeout,
                                      title='Collecting Skills Exam',
                                      action='collect',
                                      run_once=False,
                                      extra_info=f'📂 Collect directory: {self.__base_collect_dir}',
                                      ui_action_items=self.__ui_action_items
                                      )
        except MultiDeviceManager.TerminateManager as e:
            # User terminated collection after some processes failed
            self.__log.info(f'User terminated while some collections failed')
            self.__console.clear()
            self.__console.print(Panel(e.args[0], style='bold red'))
            self.__console.print()
            self.__console.print('[bold red]Unsuccessful devices:')
            for msg in e.args[1]: self.__console.print(f' :computer: {msg}')
            self.__console.print()

        self.__log.info('Removing all completed DeviceManager instances for all students where collection was successfully completed')
        for student_id in students_to_collect: self.__student_collect[student_id].clean_complete_processes()

        # Get list of all students with fully collected configurations
        successful_students = [student_id for student_id in students_to_collect if len(self.__student_collect[student_id].devices_to_collect) == 0]

        if self.__num_options > 0:
            self.__log.info(f'Exam has configurable options - querying for options for students ({', '.join(successful_students)})')
            self._set_options(successful_students)

        self.__log.info(f'Finalising collections for students ({', '.join(successful_students)})')
        for student_id in successful_students:
            self.__student_collect[student_id].finalise()
