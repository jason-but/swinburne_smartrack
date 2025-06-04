"""
This module implements the CiscoDevice class which is used to manage the connection to a Cisco Device in the SmartRack system
"""

# Import System Libraries
import time
import re
import logging
import paramiko
import itertools
from enum import Enum, auto

# TODO: username/password parsing in set_enable_mode()
# TODO: Implement comments for set_enable_mode()


class CiscoDevice:
    """
    Manages interaction with a Cisco network device via an SSH connection.

    This class provides utilities for managing network devices, including sending commands, enabling privileged mode, capturing responses,
    and uploading configurations. It aims to streamline communication and execution of commands on Cisco devices while maintaining proper internal states.
    """
    class AuthError(Exception):
        """
        This exception is raised when there is an issue with user authentication or authorization. It is intended to encapsulate information related to
        authentication errors and can be used to signal problems with access control or identity validation.
        """
        pass

    class ConsoleState(Enum):
        """
        The ConsoleState class implements an enumeration of console states. Used to identify the specific state of the connected device.

        :ivar ConsoleUnknown: Initial state - the current state of the connected console is unknown.
        :ivar ConsoleUser: The connected console is in user mode ">".
        :ivar ConsoleEnable: The connected console is in user mode "#".
        :ivar ConsoleConfig: The connected console is in a configuration or sub-configuration mode ")#".
        :ivar ConsoleAuthUser: The connected console attempting to enter user mode ">".
        :ivar ConsoleAuthEnable: The connected console attempting to enter enable mode "#".
        """
        ConsoleUnknown = auto()
        ConsoleUser = auto()
        ConsoleEnable = auto()
        ConsoleConfig = auto()
        ConsoleAuthUser = auto()
        ConsoleAuthEnable = auto()

    # Static variable containing lookup tables for responses to prompts to help state machine progress the connection into "enable" mode
    prompts = {'>': 'ena\r\n',
               'Would you like to enter the initial configuration dialog? [yes/no]: ': 'no\r\n',
               'Would you like to terminate autoinstall? [yes]:': 'yes\r\n',
               'Press RETURN to get started.': '\r\n',
               'tcl)#': 'exit\r\n',
               ')#': 'end\r\n',
               '--More--': 'q',
               '<--- More --->': 'q'
               }

    prompt_state_machine = {'>': ConsoleState.ConsoleUser,
                            'Would you like to enter the initial configuration dialog? [yes/no]: ': ConsoleState.ConsoleUnknown,
                            'Would you like to terminate autoinstall? [yes]:': ConsoleState.ConsoleUnknown,
                            'Press RETURN to get started.': ConsoleState.ConsoleUnknown,
                            'tcl)#': ConsoleState.ConsoleConfig,
                            ')#': ConsoleState.ConsoleConfig,
                            '--More--': ConsoleState.ConsoleConfig,
                            '<--- More --->': ConsoleState.ConsoleConfig
                            }

    def __init__(self, hostname: str, username: str, password: str, port: int = 22):
        """
        Class representing a Cisco network device, establishing connections and managing device interactions. This class
        is responsible for initializing a connection with the device and setting up configurations for further device operations.

        :param hostname: The hostname or IP address of the SSH server. Must be a valid URL.
        :param username: The username for authenticating to the SSH server.
        :param password: The password for authenticating to the SSH server.
        :param port: The port number to connect to on the SSH server. Default is 22.

        :raises ValueError: If the hostname is not a valid URL, or the username or password is not provided.
        """
        # Establish logger for SmartRack class
        self.__log = logging.getLogger('CiscoDevice')
        self.__log.debug(f'Constructing Class')

        # Validate parameters
        url_pattern = r'^((?!-)[A-Za-z\d-]{1,63}(?<!-)\.)+[A-Za-z]{2,}$'
        if not re.match(url_pattern, hostname): raise ValueError(f'CiscoDevice: hostname {hostname} must be a valid URL')

        if not username: raise ValueError('CiscoDevice: username must be provided')
        if not password: raise ValueError('CiscoDevice: password must be provided')

        # Store connection details
        self.__hostname = hostname
        self.__port = port
        self.__username = username
        self.__password = password

        # Create the SSH client and set to accept remote key/certificate
        self.__log.debug('Creating SSH object')
        self.__sshclient = paramiko.SSHClient()
        self.__sshclient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.__connection = None

        # Create the variable to hold the device enable prompt
        self.__enable_prompt = ''
        self.__console_state = CiscoDevice.ConsoleState.ConsoleUnknown

    ##########
    # PRIVATE METHODS
    ##########
    def _send_text(self, text: str) -> None:
        """
        Sends a given text to a connected device through the established channel.

        This method encodes the provided text in ASCII format and transmits it via the communication channel. It also logs the action,
        replacing newline characters with their escaped representation for cleaner logging output.

        :param text: The text message to be sent to the device.
        """
        self.__log.debug(f'Sending text to device: "{text.replace('\r\n', '\\r\\n')}"')
        self.__connection.send(text.encode('ascii'))

    def _read_all_text(self, timeout: int = 2) -> str:
        """
        Reads all input from the channel until the timeout period has passed with no input.

        This method reads data from the channel in a loop and appends it to the result string until the specified conditions are met.

        :param timeout: The timeout value in seconds. Specifies how long the method should attempt to read input before returning.

        :return: The accumulated input read from the channel until the timeout occurs.
        """
        self.__log.debug(f'Reading all text from device with a timeout of {timeout} seconds')

        while True:
            last_read = time.time()
            result = ''

            # Append one character at a time to result until the timeout has expired
            while time.time() - last_read < float(timeout):
                if self.__connection.recv_ready():
                    data = self.__connection.recv(1)
                    result += data.decode('ascii')
                    last_read = time.time()

            # Timeout has expired, if result is non-empty return string
            if result:
                self.__log.debug(f'Timeout expired, returning ({result})')
                return result

            # Nothing read from device in timeout period, prod the device to wakeup
            self.__log.info('Timeout expired, nothing read, prodding device to wakeup')
            self._send_text('\r\n')

    def _read_all_text_until(self, wait_string: str = '', timeout: int = 2) -> str:
        """
        Reads all input from the channel until the specified wait string is seen or the timeout period is reached.

        This method reads data from the channel in a loop and appends it to the result string until the specified conditions are met.

        :param wait_string: The string to stop flushing the input. If the wait string is empty, the method will return an empty string immediately.
        :param timeout: The timeout value in seconds. Specifies how long the method should attempt to flush input before returning.

        :return: The accumulated input read from the channel up to the specified wait string or until the timeout occurs.
        """
        # If we want to read an empty string, return immediately
        if not wait_string: return ''

        self.__log.debug(f'Flushing input until "{wait_string.replace("\r\n", "\\r\\n")}" is seen, timeout is {timeout} seconds')
        last_read = time.time()
        result = ''

        while time.time() - last_read < float(timeout) and wait_string not in result:
            if self.__connection.recv_ready():
                data = self.__connection.recv(1)
                result += data.decode('ascii')
                last_read = time.time()

        return result

    def _obtain_current_prompt(self) -> str:
        """
        Obtains the current device prompt by continuously reading all available text from a device connection. It attempts to trigger output from
        the device if no text is received by sending a carriage return. The last non-empty line of the received text is interpreted as the current prompt.

        :return: The last non-empty line of text from the device, indicating the current prompt.
        """
        self.__log.info('Obtaining current prompt')

        while True:
            # Retrieve all text from device as a list of lines, removing empty lines
            all_text = [s for s in self._read_all_text(timeout=2).splitlines() if s != '']

            # We received some text, return the last line
            if len(all_text) > 0:
                self.__log.debug(f'Returning prompt: ({all_text[-1]})')
                return all_text[-1]

            # Nothing received, try to trigger output by sending a carriage return
            self._send_text('\r\n')

    def _capture_response_until(self, command: str, end_response: str) -> str:
        """
        Captures the response sent by the device in reaction to a given command until a specified ending response (prompt) is received. In case
        the ending response is not received within a given timeout period, the function attempts re-capturing by sending additional inputs to
        wake the connected device.

        :param command: The command string to send to the device.
        :param end_response: Stop capturing when this response is seen.
        :return: The complete captured response text from the device including the ending prompt.

        :raises Exception: If the remote device is not connected
        """
        if not self.__connection: raise Exception('CiscoDevice: connection is not established')

        self.__log.debug(f'Capturing response to "{command}" until prompt "{end_response.replace("\r\n", "\\r\\n")}"')

        # Send the command text to the device then discard all input up to and including the command just sent
        self.send_command(command)
        self._read_all_text_until(command, 2)

        # Capture text up to and including end_response, timeout after 5 seconds
        result = self._read_all_text_until(end_response, 5)

        # If we timed-out without detecting end_response, wake the router with a couple of returns before trying again
        while end_response not in result:
            self._send_text('\r\n')
            self._send_text('\r\n')
            result += self._read_all_text_until(end_response, 5)

        return result

    ##########
    # PUBLIC METHODS
    ##########
    def connect(self) -> None:
        """
        Connects to a remote host via SSH and establishes a session.

        This method uses provided connection details to establish an SSH session and open a shell channel for communication with the remote
        host. It ensures that a successful connection is achieved and flushes the input until a specific prompt is detected.

        :raises paramiko.ssh_exception.SSHException: If there is an error in establishing the connection.
        """
        self.__log.info(f'Connecting to {self.__hostname} at port {self.__port} with username {self.__username} and password {self.__password}')

        # Connect to the remote host
        self.__sshclient.connect(self.__hostname, port=self.__port, username=self.__username, password=self.__password)
        self.__log.info('Connection established')

        # Open an SSH session
        self.__connection = self.__sshclient.invoke_shell()
        self.__log.info('Successful connection')

        # Flush input until we see the SmartRack "Console>" response
        self.__log.info('Waiting to see "Console>" prompt')
        self._read_all_text_until('Console>', 2)

    def send_command(self, command: str) -> None:
        """
        Sends a command to the connected device.

        This function logs the command being sent and then transmits it to the device via the established connection.

        :param command: The command string to send to the connected device.

        :raises Exception: If the remote device is not connected
        """
        if not self.__connection: raise Exception('CiscoDevice: connection is not established')

        self.__log.info(f'Sending command to device: "{command}"')
        self._send_text(f'{command}\r\n')

    def set_enable_mode(self, usernames: list[str], passwords: list[str]) -> None:
        """
        Attempts to place the connected Cisco device in "enable mode".

        This involves handling various prompts presented by the device and sending appropriate responses, such as usernames, passwords, or other
        necessary commands. The method executes a state machine until the device reaches enable mode, indicated by a prompt ending with '#'.
        Once in enable mode, it configures certain terminal settings and disables unnecessary debugging messages.

        :param usernames: A list of username strings to attempt if authentication is required.
        :param passwords: A list of password strings to attempt if authentication is required.

        :raises Exception: If the remote device is not connected
        """
        if not self.__connection: raise Exception('CiscoDevice: connection is not established')

        self.__log.info('Trying to put device into enable mode (wait 5 seconds)')
        time.sleep(5)

        self.__log.info('Waking up device')
        self._send_text('\r\n')

        auth_attempts = {CiscoDevice.ConsoleState.ConsoleUnknown: iter(passwords.copy()),
                         CiscoDevice.ConsoleState.ConsoleAuthUser: itertools.product(usernames.copy(), passwords.copy()),
                         CiscoDevice.ConsoleState.ConsoleAuthEnable: iter(passwords.copy())}
        user_password = None

        self.__log.info(f'Initial console state: {self.__console_state}')
        while True:
            current_prompt = self._obtain_current_prompt()
            self.__log.info(f'Current Prompt: "{current_prompt}"')

            prompt_state = [new_state for prompt, new_state in CiscoDevice.prompt_state_machine.items() if current_prompt.endswith(prompt)]
            prompt_response = [(prompt, response) for prompt, response in CiscoDevice.prompts.items() if current_prompt.endswith(prompt)]

            if len(prompt_response) > 0:
                self.__console_state = prompt_state[0]
                self.__log.info(f'Console state: {self.__console_state}')
                prompt, response = prompt_response[0]
                self.__log.info(f'Current Prompt ends with "{prompt}", sending response: "{response}"'.replace('\n', '\\n'))
                self._send_text(response)
                continue

            # Device is asking for a username
            if current_prompt.endswith('Username: '):
                try:
                    # Only happens when NOT in user or enable mode and a console username/password account is in use, set state
                    self.__console_state = CiscoDevice.ConsoleState.ConsoleAuthUser
                    self.__log.info(f'Console state: {self.__console_state}')

                    # Get the next combination of usernames/passwords, store password as we will need it for next loop
                    try_username, user_password = next(auth_attempts[self.__console_state])
                    self.__log.info(f'Device is asking for a username, next username/password attempt is "{try_username}"/"{user_password}"')
                    self.send_command(try_username)
                    continue
                except StopIteration:
                    # No more username/password combinationss to try
                    self.__log.error(f'Provided username/password list exhausted')
                    raise CiscoDevice.AuthError('Authentication error attempting to put device in enable mode')

            # Device is asking for a password
            if current_prompt.endswith('Password: '):
                try:
                    # If we were in ConsoleUser(>) mode, we have sent "ena" and the device has an enable password, therefore we are now in ConsoleAuthEnable mode
                    if self.__console_state == CiscoDevice.ConsoleState.ConsoleUser:
                        self.__console_state = CiscoDevice.ConsoleState.ConsoleAuthEnable
                        self.__log.info(f'Console state: {self.__console_state}')

                    # user_password is set if we were in ConsoleAuthMode and have entered username, otherwise we get the next password in the list and reset user_password
                    try_password = user_password or next(auth_attempts[self.__console_state])
                    user_password = None

                    # Sending password
                    self.__log.info(f'Device is asking for a password, trying "{try_password}"')
                    self.send_command(try_password)
                    continue
                except KeyError:
                    # Bug in the state machine
                    self.__log.error(f'Device is asking for a password, but cannot handle state {self.__console_state}')
                    raise CiscoDevice.AuthError('Authentication error attempting to put device in enable mode')
                except StopIteration:
                    # No more passwords to try
                    self.__log.error(f'Provided password list exhausted')
                    raise CiscoDevice.AuthError('Authentication error attempting to put device in enable mode')

            # No matching prompt for state machine to handle, if prompt ends with #, we are in enable mode and we can return
            if current_prompt.endswith('#'):
                self.__console_state = CiscoDevice.ConsoleState.ConsoleEnable
                self.__log.info(f'Current console state: {self.__console_state}')
                self.__enable_prompt = current_prompt
                self.__log.info(f'Storing Enable Prompt: "{self.__enable_prompt}"')
                self.__log.info('Disabling paging and debug commands')
                self.send_command('terminal length 0')
                self.send_command('terminal pager 0')
                self.send_command('undebug all')
                return

            # Unknown prompt, send a carriage return to prod device to output something else and try again
            self.__log.info('Unknown prompt, trying again')
            self.send_command('')

    def capture_command(self, command: str, strip_excess_bangs: bool = True) -> str:
        """
        Captures a command's response until the enable prompt is output from the device. Allows optional stripping of excess exclamation marks ('!')
        from the captured output.

        :param command: The command whose response needs to be captured.
        :param strip_excess_bangs: If True, excess consecutive exclamation marks in the response will be reduced to a single one. Default is True.
        :return: The captured response as a string, with or without excess exclamation marks depending on the `strip_excess_bangs` flag.

        :raises Exception: If the remote device is not connected
        """
        if not self.__connection: raise Exception('CiscoDevice: connection is not established')

        self.__log.info(f'Capturing command: "{command}"')
        result = self._capture_response_until(command, f'\r\n{self.__enable_prompt}')

        if strip_excess_bangs:
            self.__log.info('Stripping excess bangs from captured command')
            result = re.sub('(\r\n!)+', '\r\n!', result)

        return result

    def upload_config(self, config: list[str]) -> None:
        """
        Uploads a list of configuration commands to a terminal session.

        The method puts the device into configuration mode before iterating  over the provided configuration lines, uploading each non-empty
        line to the terminal session. It ensures each command is fully processed by waiting until the configuration prompt is detected. After
        all lines are uploaded, the method exits the configuration mode.

        :param config: A list of strings containing configuration commands to be uploaded to the terminal.

        :raises Exception: If the remote device is not connected
        """
        if not self.__connection: raise Exception('CiscoDevice: connection is not established')

        self.__log.info('Uploading configuration')

        self.send_command('configure terminal')
        for line in config:
            if len(line) > 0:
                self.__log.info(f'Uploading config line: "{line}"')
                self._capture_response_until(line, f')#')

        self.send_command('end')
