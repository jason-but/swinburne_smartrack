import time
import multiprocessing
import logging
import rich
import rich.progress
import rich.live

from .devicemanager import DeviceManager
from .devicemanager import DeviceActionCompleteEnum


class MultiDeviceManager:
    """
    Manages multiple DeviceManager tasks using multiprocessing, enabling parallel execution of tasks. The class uses a provided list of `DeviceManager`
    processes along with multiprocessing queues to handle task progress updates and logging. It facilitates execution with a specified timeout and ensures
    task management with visual feedback using Rich console components.
    """
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

        # Create the two multiprocessing queues, worker processes queue all log messages to log queue and queue progress updates to progress queue
        self.__log_queue: multiprocessing.Queue = log_queue
        self.__progress_queue: multiprocessing.Queue = progress_queue

        # List of worker processes
        self.__processes: list[DeviceManager] = []

        self.__start_time: int = 0

    def _keep_running(self, timeout: int) -> bool:
        """
        Checks whether the manager task should keep running based on the elapsed time and the specified timeout value. If the timeout value is zero, the process
        is set to run indefinitely.

        :param timeout: The maximum duration (in seconds) the process is allowed to keep running. A value of 0 indicates that the process should run indefinitely.
        :return: True if the manager should keep running (timeout has not expired or timeout is 0).
        """
        if timeout == 0: return True
        return time.time() - self.__start_time <= timeout

    def set_process_list(self, process_list: list[DeviceManager]) -> None:
        """
        Stores the list of processes for the manager to execute to the internal process list

        :param process_list: A list of TaskProcess objects to be managed by the class instance.
        """
        self.__processes = process_list

    def run_processes(self, timeout: int) -> tuple[list[DeviceManager], list[DeviceManager]]:
        """
        Runs multiple processes with a specified timeout and manages their progress and logging.

        The method initiates all processes, monitors their progress using a visual console status and progress bar, and checks if processes complete
        successfully within the timeout. If processes remain alive past the timeout, they are terminated. The method also monitors log messages from the worker
        processes.

        :param timeout: The maximum duration in seconds for which the processes will be allowed to run. If set to zero, the processes will run indefinitely until all are completed.

        :return: A tuple containing two lists:
                 - The first list contains all successfully completed processes.
                 - The second list contains the processes that were unsuccessful or terminated before completion.

        :raises ValueError: If the `timeout` parameter is less than zero.
        """
        # Validate timeout parameter
        if timeout < 0: raise ValueError('Timeout must be greater than 0')

        if len(self.__processes) == 0:
            self.__log.warning('No processes to run!')
            return [], []

        self.__log.info(f'Running processes for {timeout} seconds' if timeout > 0 else 'Running processes until all are complete')

        # Create user interfaces
        console_status = self.__console.status("[magenta]Programming multiple devices!")
        console_progress = rich.progress.Progress('[progress.description]{task.description}', rich.progress.BarColumn(),
                                                  '{task.completed} of {task.total} devices completed')
        progress_bars = {task: console_progress.add_task(task.value, total=len(self.__processes)) for task in DeviceActionCompleteEnum}

        self.__start_time = time.time()

        self.__log.info(f'Starting {len(self.__processes)} processes')
        for process in self.__processes: process.start()

        with (rich.live.Live(rich.console.Group(console_progress, console_status), console=self.__console)):
            # Loop until the timeout has expired
            while self._keep_running(timeout):
                # If processes are running or there are still messages to process in the queue
                if any(p.is_alive() for p in self.__processes) or not self.__progress_queue.empty():
                    # Process next progress updates from worker processes
                    if not self.__progress_queue.empty():
                        update = self.__progress_queue.get()
                        if update['task'] in progress_bars:
                            console_progress.update(progress_bars[update['task']], advance=1)
                        console_status.update(f'[magenta]{update["message"]}')



                        # message, stage = self.__progress_queue.get()
                        # if stage < len(progress_bars): console_progress.update(progress_bars[stage], advance=1)
                        # console_status.update(f'[magenta]{message}')

                    # Process any log messages from all worker processes
                    while not self.__log_queue.empty():
                        record = self.__log_queue.get()
                        self.__log.handle(record)

                else:
                    self.__log.info("All tasks and stages are complete AND no messages left in queue! Exiting loop..!")
                    console_status.update(f'[bold green]All Device Tasks are complete!')
                    successful_processes = self.__processes
                    unsuccessful_processes = []
                    break
            else:
                # Only do while else if while loop finished normally - ie timeout
                self.__log.info("Timeout period has expired! Exiting loop..!")
                successful_processes = [p for p in self.__processes if not p.is_alive()]
                unsuccessful_processes = [p for p in self.__processes if p.is_alive()]
                for process in [p for p in unsuccessful_processes if p.is_alive()]:
                    self.__log.info(f"Terminating process {process.name}...")
                    process.terminate()
                console_status.update(f'[bold red]Not all Devices completed in time!')

            # Ensure all processes finish
            self.__log.info("Process cleanup via join()")
            for process in self.__processes: process.join()
            self.__log.info("All processes joined!")

            return successful_processes, unsuccessful_processes
