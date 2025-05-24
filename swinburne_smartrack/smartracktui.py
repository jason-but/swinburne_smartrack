"""
This module implements the SmartRackTUI class which provides a text-based user interface to prompt the user to access the SmartRack system to download booked
device information. Returns a SmartRack instance containing the booked devices retrieved from the SmartRack system.
"""

# Import System Libraries
import dialog
import rich
import logging

# Import SmartRackLibrary modules
from .configuration import Configuration
from .smartrack import SmartRack


class SmartRackTUI:
    """
    Provides a text-based console User Interface allowing the user to select from a list of SmartRack servers from the configuration file, and to provide
    username/password authentication to access the SmartRack servers.
    """
    class TerminateApp(Exception):
        """
        This exception is raised when there is an issue with user authentication or authorization. It is intended to encapsulate information related to
        authentication errors and can be used to signal problems with access control or identity validation.
        """
        pass

    def __init__(self, console: rich.console.Console, server_menu_title: str = None, auth_form_title: str = None, confirm_terminate_title: str = None):
        """
        Implements a User Interface to manage console-based interactions using the dialog library to manage user-input. On running the ui() method, will
        return a SmartRack instance containing device information for all booked devices on the selected SmartRack servers.

        :param console: A rich.console.Console instance used for rendering formatted console output.
        :type console: rich.console.Console
        :param server_menu_title: A string providing the title for the server selection dialog. (default = ' ATC Room Selection ' )
        :param auth_form_title: A string providing the title for the authentication dialog. (default = ' ATC Website Authentication Information ' )
        :param confirm_terminate_title: A string providing the title for the termination confirmation dialog. (default = ' Terminate Application ' )
        """
        self.__console = console
        self.__log = logging.getLogger('SmartRackTUI')
        self.__log.info(f'Constructing Class')

        self.__dialog = dialog.Dialog(dialog='dialog')
        self.__server_menu_title = server_menu_title or ' ATC Room Selection '
        self.__auth_form_title = auth_form_title or ' ATC Website Authentication Information '
        self.__confirm_terminate_title = confirm_terminate_title or ' Terminate Application '

        self.__selected_rooms: list[str] = []
        self.__auth_details: dict[str, str] = {}

    ##########
    # PRIVATE METHODS
    ##########
    def _confirm_termination(self) -> None:
        """
        Ask the user if they wish to terminate the UI (and application), if so raise TerminateApp() Exception, otherwise return.

        :raises TerminateApp: If the user chooses to Quit.
        """
        if self.__dialog.yesno('Are you sure that you want to terminate application?', title=self.__confirm_terminate_title) != self.__dialog.OK: return

        raise SmartRackTUI.TerminateApp('Terminating from SmartRack User Interface')

    def _select_servers(self, instructions: str) -> None:
        """
        Select one or more servers from a checklist dialog.

        This function presents a checklist dialog box to the user, allowing them to select one or more servers from the list in the system SmartRack
        configuration file. It loops until the user makes a valid selection or confirms quitting. If the user selects OK, but no servers are chosen,
        an error message is displayed, prompting them to try again.

        If servers are chosen, they will be stored in the __selected_rooms list.

        :param instructions: Instructions displayed to the user in the checklist dialog.
        """
        # Loop forever asking user to select room, when one or more rooms are selected, break out of loop
        while True:
            # Display message box
            code, self.__selected_rooms = self.__dialog.checklist(instructions,
                                                                  choices=[(key, value['description'], False) for key, value in Configuration().smartrack_servers.items()],
                                                                  title=self.__server_menu_title,
                                                                  cancel_label='Quit'
                                                                  )

            if code == self.__dialog.OK:
                # User selected OK, if at least one room is selected break out of loop, otherwise display error message and try again
                if len(self.__selected_rooms) > 0: return
                self.__dialog.msgbox('ERROR: You must select at least one room/server', title=self.__server_menu_title)
            else:
                # User selected QUIT, confirm termination (will raise exception if user confirms, otherwise continue and try again)
                self._confirm_termination()

    def _ask_auth_details(self) -> None:
        """
        Prompt the user to input authentication details for SmartRack. The function displays a dialog box for the user to input a username
        and password, the password field is hidden The dialog allows the user to quit. If "Quit" is selected, confirmation of termination will be
        sought from the user.

        If parameters are provided, they will be stored in the __auth_details dictionary., with keys `'username'` and `'password'` respectively.
        """
        while True:
            # Display password entry box, each tuple in elements is:
            #  field label, label y pos, label x pos, initial field value, field y pos, field x pos, field length, input length, 0=plaintext/1=hidden
            code, values = self.__dialog.mixedform('Enter SmartRack Authentication details below:\n',
                                                   title=self.__auth_form_title,
                                                   elements=[("Username:", 2, 2, "", 2, 15, 50, 50, 0),
                                                             ("Password:", 4, 2, "", 4, 15, 50, 50, 1)],
                                                   cancel_label='Quit',
                                                   insecure=True
                                                   )

            if code == self.__dialog.OK:
                self.__auth_details = {'username': values[0], 'password': values[1]}
                return

            # User selected QUIT, confirm termination (will raise exception if user confirms, otherwise continue and try again)
            self._confirm_termination()

    ##########
    # PUBLIC METHODS
    ##########
    def ui(self, select_server_instructions: str) -> SmartRack:
        """
        Runs a User Interface to select a set of servers and obtain authentication information. Then creates a SmartRack system to retrieve booked devices.
        Repeatedly asks for user authentication details on authentication error.

        :param select_server_instructions: Instructions provided to the user to specify server selection criteria.

        :return: An instance of SmartRack containing the booked devices retrieved from the SmartRack system.
        """
        self._select_servers(select_server_instructions)
        smartrack = SmartRack(self.__console)

        while True:
            try:
                self._ask_auth_details()

                self.__console.clear()
                self.__console.print()
                self.__console.rule('Retrieving Booked Devices from SmartRack Website')

                smartrack.fetch_booked_devices(self.__selected_rooms, self.__auth_details)
                return smartrack

            except SmartRack.AuthError as e:
                self.__dialog.msgbox(f'ERROR: {e}', title='Authentication Error')
