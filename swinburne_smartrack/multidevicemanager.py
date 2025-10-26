"""
This module implements the MultiDeviceManager class which is used to run multiple DeviceManager instances in parallel.
"""

# Import System Libraries
import time
import multiprocessing
import logging

import rich
import rich.progress
import rich.live
import dialog

# Import SmartRackLibrary modules
from .devicemanager import DeviceManager
from .devicemanager import DeviceActionCompleteEnum


class MultiDeviceManager:
    """
    Manages multiple DeviceManager tasks using multiprocessing, enabling parallel execution of tasks. The class uses a provided list of `DeviceManager`
    processes along with multiprocessing queues to handle task progress updates and logging. It facilitates execution with a specified timeout and ensures
    task management with visual feedback using Rich console components.
    """
    class TerminateManager(Exception):
        """
        This exception is raised when the user chooses to terminate the application as a signal to cancel any further actions.
        """
        pass

    def __init__(self, console: rich.console.Console, log_queue: multiprocessing.Queue, progress_queue: multiprocessing.Queue):
        """
        This class handles the management of multiple device tasks using multiprocessing. It uses a provided list of DeviceManager processes, coupled
        with two multiprocessing Queues to manage progress updates and logging. The class supports attempting to run multiple DeviceManager classes in
        parallel with a timeout.

        :param console: Rich Console instance for managing rich text output.
        :param log_queue: Queue to store log messages from worker processes.
        :param progress_queue: Queue to store progress updates from worker processes.
        """
        # Establish logger for MultiDeviceManager class
        self.__log = logging.getLogger('MultiDeviceManager')
        self.__log.info(f'Constructing Class')

        # Local variable for the console, also for the pythondialog instance
        self.__console: rich.console.Console = console
        self.__dialog = dialog.Dialog(dialog='dialog')

        # Store the two multiprocessing queues, worker processes queue all log messages to log queue and queue progress updates to progress queue
        self.__log_queue: multiprocessing.Queue = log_queue
        self.__progress_queue: multiprocessing.Queue = progress_queue

        # List of worker processes to manage
        self.__processes: list[DeviceManager] = []

        # Variable to track start time to manage timeout
        self.__start_time: int = 0

    ##########
    # PRIVATE METHODS
    ##########
    def _confirm_continue(self, action: str) -> None:
        """
        Prompt the user for confirmation to continue processing unsuccessful devices and handle the response accordingly. Method ensures that the user
        is informed about unsuccessful processes and provides them with a choice to either retry the operation or terminate the application.

        :param action: The action being performed to incorporate into message to be displayed.

        :raises MultiDeviceManager.TerminateManager: When the user chooses to terminate the application, contains list of unsuccessful devices.
        """
        message: list[str] = ['', f'Please try to repair the following devices, and then select whether we should try to {action} them again', '']

        message.extend([task.full_description for task in self.__processes])

        if self.__dialog.yesno('\n'.join(message), title=' Unsuccessful Devices ', no_collapse=True, width=80, height=len(message) + 7) != self.__dialog.OK:
            raise MultiDeviceManager.TerminateManager('Terminating application - User chose to terminate the application prior to completion of all tasks.',
                                                      [task.full_description for task in self.__processes]
                                                      )

    def _keep_running(self, timeout: int) -> bool:
        """
        Checks whether the manager task should keep running based on the elapsed time and the specified timeout value. If the timeout value is zero, the process
        is set to run indefinitely.

        :param timeout: The maximum duration (in seconds) the process is allowed to keep running. A value of 0 indicates that the process should run indefinitely.
        :return: True if the manager should keep running (timeout has not expired or timeout is 0).
        """
        if timeout == 0: return True
        return time.time() - self.__start_time <= timeout

    def _run_processes(self, timeout: int, action_items: list[DeviceActionCompleteEnum] = None) -> int:
        """
        Runs multiple processes with a specified timeout and manages their progress and logging.

        NOTE: Parameters are validated by calling method.

        The method initiates all processes, monitors their progress using a visual console status and progress bar, and checks if processes complete
        successfully within the timeout. If processes remain alive past the timeout, they are terminated. The method also monitors log messages from the worker
        processes. Successful completion of tasks is indicated by the console status and progress bar.

        :param timeout: The maximum duration, in seconds, for the processes to run. If set to zero, the processes will continue to run until all are complete.
        :param action_items: A list of DeviceActionCompleteEnum values indicating various states or tasks to track during process execution.
            If not specified, all possible DeviceActionCompleteEnum states are used.

        :return: Count of the number of processes that successfully finished (unsuccessful processes are recreated in self.__processes and primed to be run again).

        :raises ValueError: Raised when the `timeout` is specified as a negative integer.
        """
        # Create user interfaces
        console_status = self.__console.status("[magenta]Initiating connection to multiple devices!")
        console_progress = rich.progress.Progress('[progress.description]{task.description}',
                                                  rich.progress.BarColumn(bar_width=None),
                                                  '{task.completed} of {task.total} devices completed', expand=True)
        progress_bars = {task: console_progress.add_task(task.value, total=len(self.__processes)) for task in action_items}

        # Set the start time to enable the timeout
        self.__start_time = time.time()

        self.__log.info(f'Starting {len(self.__processes)} processes')
        for process in self.__processes: process.start()

        with (rich.live.Live(rich.console.Group(console_progress, console_status), console=self.__console)):
            # Loop until the timeout has expired
            while self._keep_running(timeout):
                # If processes are running or there are still messages to process in the queue
                if any(p.is_alive() for p in self.__processes) or not self.__progress_queue.empty():
                    # Process next progress update from any DeviceManager processes
                    if not self.__progress_queue.empty():
                        update = self.__progress_queue.get()
                        if update['task'] in progress_bars:
                            console_progress.update(progress_bars[update['task']], advance=1)
                        console_status.update(f'[magenta]{update["message"]}')

                    # Process any log messages from all DeviceManager processes
                    while not self.__log_queue.empty():
                        record = self.__log_queue.get()
                        self.__log.handle(record)

                else:
                    # No updates in the progress queue and no DeviceManager processes running
                    self.__log.info("All tasks and stages are complete AND no messages left in queue! Exiting loop..!")
                    console_status.update(f'[bold green]All Device Tasks are complete!')
                    successful_count = len(self.__processes)
                    unsuccessful_processes = []
                    break
            else:
                # This block only runs if the while loop above finished normally - ie timeout has occurred
                self.__log.info("Timeout period has expired! Exiting loop..!")
                successful_count = len([p for p in self.__processes if not p.is_alive()])
                unsuccessful_processes = [p for p in self.__processes if p.is_alive()]
                for process in [p for p in unsuccessful_processes if p.is_alive()]:
                    self.__log.info(f"Terminating process {process.description}...")
                    process.terminate()
                console_status.update(f'[bold red]Not all Devices completed in time!')

            # Ensure all processes finish
            self.__log.info("Process cleanup via join()")
            for process in self.__processes: process.join()
            self.__log.info("All processes joined!")

            # The internal process list is set to all unsuccessful processes, however we need to re-create them to be able to run again
            self.__processes = [p.recreate() for p in unsuccessful_processes]

            return successful_count

    ##########
    # PUBLIC METHODS
    ##########
    def set_process_list(self, process_list: list[DeviceManager]) -> None:
        """
        Stores the list of processes for the manager to execute to the internal process list

        :param process_list: A list of DeviceManager objects to be managed by the class instance.
        """
        self.__processes = process_list

    def execute_processes(self, timeout: int, title: str, action: str, run_once: bool = True, extra_info: str = '', ui_action_items: list[DeviceActionCompleteEnum] = None) -> None:
        """
        Executes multiple processes in parallel, allowing for re-attempts for failed devices.

        This method loops trying to execute all registered processes within the timeout. If any processes fail, the user is queried whether to try again or
        not. Method terminates when all processes successfully complete, or user chooses to not continue.

        :param timeout: The maximum duration, in seconds, for the processes to run. If set to zero, the processes will continue to run until all are complete.
        :param title: String heading displayed in the console to identify the current process batch or operation title.
        :param action: String representation of the action to perform on the devices, also displayed in the console to identify the action being performed.
        :param run_once: Boolean flag indicating whether the function should stop after one execution loop (`True`) or keep running until all tasks are completed
            (`False`). Default is `True`.
        :param extra_info: If provided, display this extra information message to the console while running processes.
        :param ui_action_items: A list of DeviceActionCompleteEnum values indicating various states or tasks to track during process execution.
            If not specified, all possible DeviceActionCompleteEnum states are used.
        """
        # Validate timeout parameter and process list
        if timeout < 0: raise ValueError('Timeout must be greater than 0')

        if len(self.__processes) == 0:
            self.__console.print(' :warning: [bold yellow]No processes to run!')
            self.__log.warning('No processes to run!')
            return

        self.__log.info(f'Running processes for {timeout} seconds' if timeout > 0 else 'Running processes until all are complete')

        action_items: list[DeviceActionCompleteEnum] = ui_action_items or list(DeviceActionCompleteEnum)

        # Loop until there are no more processes to run
        while len(self.__processes) > 0:
            self.__console.print()
            self.__console.rule(title)
            self.__console.print(f' :computer: Attempting to {action} {len(self.__processes)} devices')
            if len(extra_info) > 0: self.__console.print(f' {extra_info}')
            self.__console.print(f' :alarm_clock: Timeout = {timeout} seconds')
            self.__console.print()

            # Run all processes with the specified timeout
            successful = self._run_processes(timeout, action_items)

            # Print successful outcomes
            self.__console.print()
            self.__console.print(f' :crying_face: [bold red]No devices were successfully {action}ed' if successful == 0 else f' :thumbs_up: [bold green]{successful} devices were successfully {action}ed')
            self.__console.print()

            # If any processes were unsuccessful
            if len(self.__processes) > 0:
                # Terminate after first loop if run_once is True
                if run_once: raise MultiDeviceManager.TerminateManager('Not all tasks successful', [task.full_description for task in self.__processes])

                # Confirm whether to continue
                self._confirm_continue(action)

                # Display unsuccessful outcomes
                self.__console.clear()
                self.__console.rule('Not all tasks successful')
                self.__console.print('[bold red]Unsuccessful devices:')
                for task in self.__processes: self.__console.print(f' :computer: {task.full_description}')
