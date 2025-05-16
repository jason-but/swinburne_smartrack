"""
This module implements the CiscoDevice class which is used to manage control of a Cisco Device in the SmartRack system

The CiscoDevice class contains methods that:
  - Place the device in enable mode
  - Send commands to the device
  - Capture responses from the device
  - Upload configurations to the device

Running the module directly will run a test suite allowing verification of functionality.
"""

# Import Libraries
# time    - Access system time functions
# re      - Regular Expressions
# logging - Python logging module
# paramiko - ssh library to support remote connections
import time
import re
import logging
import paramiko


class CiscoDevice:
    """
    Manages interaction with a Cisco network device via an SSH connection.

    This class provides utilities for managing network devices, including sending commands, enabling privileged mode,
    capturing responses, and uploading configurations. It aims to streamline communication and execution of
    commands on Cisco devices while maintaining proper internal states.
    """

    prompts = {'>': 'ena\r\n',
               'Would you like to enter the initial configuration dialog? [yes/no]: ': 'no\r\n',
               'Would you like to terminate autoinstall? [yes]:': 'yes\r\n',
               'Press RETURN to get started!': '\r\n',
               'tcl)#': 'exit\r\n',
               ')#': 'end\r\n',
               '--More--': 'q',
               '<--- More --->': 'q'
               }

    def __init__(self, hostname: str, username: str, password: str, port: int = 22):
        """
        Class representing a Cisco network device, establishing connections and managing device interactions. This class
        is responsible for initializing a connection with the device and setting up configurations for further device operations.

        :param hostname: The hostname or IP address of the SSH server. Must be a valid URL.
        :param username: The username for authenticating to the SSH server.
        :param password: The password for authenticating to the SSH server.
        :param port: The port number to connect to on the SSH server. Default is 22.

        :raises ValueError: If the hostname is not a valid URL.
        :raises ValueError: If the username is not provided.
        :raises ValueError: If the password is not provided.
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
        :return: The accumulated input read from the channel up to the specified wait string or until the timeout occurs.
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
        Obtains the current device prompt by continuously reading all available text from a device connection. It attempts to
        trigger output from the device if no text is received by sending a carriage return. The last non-empty line of the
        received text is interpreted as the current prompt.

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
        if not self.__connection:
            raise Exception('CiscoDevice: connection is not established')

        self.__log.info(f'Sending command to device: "{command}"')
        self._send_text(f'{command}\r\n')

    def set_enable_mode(self, usernames: list[str], passwords: list[str]) -> None:

        if not self.__connection:
            raise Exception('CiscoDevice: connection is not established')

        self.__log.info('Trying to put device into enable mode (wait 5 seconds)')
        time.sleep(5)

        self.__log.info('Waking up device')
        self._send_text('\r\n')

        next_username = 0
        next_password = 0

        while True:
            current_prompt = self._obtain_current_prompt()
            self.__log.info(f'Current Prompt: "{current_prompt}"')

            prompt_response = [(prompt, response) for prompt, response in CiscoDevice.prompts.items() if current_prompt.endswith(prompt)]

            if len(prompt_response) > 0:
                prompt, response = prompt_response[0]
                self.__log.info(f'Current Prompt ends with "{prompt}", sending response: "{response}"'.replace('\n', '\\n'))
                self._send_text(response)
                continue

            # Device is asking for a username, try the next one in the list
            if current_prompt.endswith('username'):
                try_username = usernames[next_username] if len(usernames) > 0 else ''
                next_username += 1 if next_username < len(usernames) else 0
                self.__log.info('Device is asking for a username, trying {try_username}')
                self.send_command(try_username)

            # Device is asking for a password, try the next one in the list
            if current_prompt.endswith('Password:'):
                try_password = passwords[next_password] if len(passwords) > 0 else ''
                next_password += 1 if next_password < len(passwords) else 0
                self.__log.info('Device is asking for a username, trying {try_password}')
                self.send_command(try_password)

            # No matching prompt for state machine to handle, if prompt ends with #, we are in enable mode and we can return
            if current_prompt.endswith('#'):
                self.__log.info('Device is in enable mode')
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

    def capture_response_until(self, command: str, end_response: str) -> str:
        """
        Captures the response sent by the device in reaction to a given command until a specified ending response (prompt) is
        received. In case the ending response is not received within a given timeout period, the function attempts re-capturing
        by sending additional inputs to wake the connected device.

        :param command: The command string to send to the device.
        :param end_response: Stop capturing when this response is seen.
        :return: The complete captured response text from the device including the ending prompt.

        :raises Exception: If the remote device is not connected
        """
        if not self.__connection:
            raise Exception('CiscoDevice: connection is not established')

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

    def capture_command(self, command: str, strip_excess_bangs: bool = True) -> str:
        """
        Captures a command's response until a specific prompt is encountered. Allows optional stripping of
        excess exclamation marks ('!') from the captured output.

        :param command: The command whose response needs to be captured.
        :param strip_excess_bangs: If True, excess consecutive exclamation marks in the response will be reduced to a single one. Default is True.
        :return: The captured response as a string, with or without excess exclamation marks depending on the `strip_excess_bangs` flag.

        :raises Exception: If the remote device is not connected
        """
        if not self.__connection:
            raise Exception('CiscoDevice: connection is not established')

        self.__log.info(f'Capturing command: "{command}"')
        result = self.capture_response_until(command, f'\r\n{self.__enable_prompt}')

        if strip_excess_bangs:
            self.__log.info('Stripping excess bangs from captured command')
            result = re.sub('(\r\n!)+', '\r\n!', result)

        return result

    def upload_config(self, config: list[str]) -> None:
        """
        Uploads a list of configuration commands to a terminal session.

        The method puts the device into configuration mode before iterating  over the provided configuration lines, uploading
        each non-empty line to the terminal session. It ensures each command is fully processed by waiting until the configuration
        prompt is detected. After all lines are uploaded, the method exits the configuration mode.

        :param config: A list of strings containing configuration commands to be uploaded to the terminal.

        :raises Exception: If the remote device is not connected
        """
        if not self.__connection:
            raise Exception('CiscoDevice: connection is not established')

        self.__log.info('Uploading configuration')

        self.send_command('configure terminal')
        for line in config:
            if len(line) > 0:
                self.__log.info(f'Uploading config line: "{line}"')
                self.capture_response_until(line, f')#')

        self.send_command('end')


# Execute test/validation suite if run as python -m swinburne_smartrack.ciscodevice
if __name__ == '__main__':
    try:
        # Create argparse instance and parse command line parameters
        import argparse
        parser = argparse.ArgumentParser(description='CiscoDevice Test Suite',
                                         formatter_class=argparse.RawTextHelpFormatter,
                                         allow_abbrev=False
                                         )
        parser.add_argument('-d', '--debug',
                            default='INFO',
                            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                            help='Set logging level (default: %(default)s)'
                            )
        parser.add_argument('hostname', help='Hostname or IP address of remote Cisco device')
        parser.add_argument('username', help='Username to connect to remote Cisco device')
        parser.add_argument('password', help='Password to connect to remote Cisco device')
        parser.add_argument('port', nargs='?', default=22, type=int, help='Port number of remote Cisco device (default: %(default)s)')
        arguments = parser.parse_args()

        # Create the Rich Console and Rich Logger
        import rich.logging
        import rich.console
        console = rich.console.Console()
        logging.basicConfig(format='%(name)s.%(funcName)s() - %(message)s',
                            handlers=[rich.logging.RichHandler(markup=True, console=console)],
                            level=getattr(logging, arguments.debug)
                            )

        logger = logging.getLogger('')

        # Create the Cisco Device, set it to enable mode, and capture/print output of "show ip int brief"
        test_device = CiscoDevice(arguments.hostname, arguments.username, arguments.password, arguments.port)
        test_device.connect()
        test_device.set_enable_mode(usernames=[], passwords=[])

        # Capture output of interface configuration
        interfaces = [s for s in test_device.capture_command("show ip int brief", False).splitlines() if s != '']
        heading = interfaces.pop(0)
        interfaces.pop()

        logger.info('Displaying device interface details')
        from rich.table import Table
        table = Table(show_header=True, header_style="bold green", title="Interface Configuration", show_lines=True)
        for item in heading.split(): table.add_column(item, style="green")
        for interface in interfaces: table.add_row(*interface.split())
        console.print(table)

        # Change hostname and configure loopback device, then recapture interface configuration
        test_device.upload_config(["hostname test_new_name", 'interface Loopback0', 'ip address 105.9.5.129 255.255.255.224', '!'])
        test_device.set_enable_mode(usernames=[], passwords=[])

        interfaces = [s for s in test_device.capture_command("show ip int brief", False).splitlines() if s != '']
        heading = interfaces.pop(0)
        interfaces.pop()

        logger.info('Displaying device interface details')
        from rich.table import Table
        table = Table(show_header=True, header_style="bold green", title="Interface Configuration", show_lines=True)
        for item in heading.split(): table.add_column(item, style="green")
        for interface in interfaces: table.add_row(*interface.split())
        console.print(table)

    except KeyboardInterrupt as err:
        pass
    except (Exception,):
        rich.console.Console().print_exception()
