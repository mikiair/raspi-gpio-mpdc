# standard imports
import socket

# 3rd party imports
import mpd


class PersistentMPDClient(mpd.MPDClient):
    """MPD client which tries to re-connect when connection has timed-out.

    Based on original class found at
        https://github.com/schamp/PersistentMPDClient
        Copyright (c) 2015 Andrew Schamp (MIT License)

    Added documentation, created new methods, renaming for clarification.
    Added log output.
    """

    def __init__(self, socket=None, host=None, port=None, log=None):
        super(PersistentMPDClient, self).__init__()
        self.socket = socket
        self.host = host
        self.port = port
        self.log = log

        self.command_blacklist = ["ping"]

        self.connection_established = False
        self.establish_connection()

    def establish_connection(self):
        """Establish the connection to the MPD server by trying to connect,
        and if not yet connected before (= not established),
        then read out the command list and dereference to auto-connect commands
        """
        try:
            if self.log is not None:
                self.log.debug("establish_connection")

            if not self.do_connect(False):
                return

            if not self.connection_established:
                self.establish_commandlist()
        except Exception as e:
            if self.log is not None:
                self.log.error(f"Error when establishing connection to MPD server: {e}")

    def establish_commandlist(self):
        """Wrap all valid MPDClient functions so that each may reconnect to server.

        Query the list of valid commands, and wrap valid commands ping-connection-retry
        method block.
        """

        command_list = self.commands()

        for cmd in command_list:
            if cmd not in self.command_blacklist:
                if hasattr(super(PersistentMPDClient, self), cmd):
                    super_func = super(PersistentMPDClient, self).__getattribute__(cmd)
                    new_func = self.try_cmd(super_func)
                    setattr(self, cmd, new_func)
                else:
                    if self.log is not None:
                        self.log.debug("Unknown command attribute '{cmd}'!")
                    pass

        self.connection_established = True

    # create a wrapper for a function (such as a MPDClient member function) that will
    # verify a connection (and reconnect if necessary) before executing that function.
    # Functions wrapped in this way should always succeed (if the server is up).
    # We ping first because we don't want to retry the same function if there's a
    # failure, we want to use the noop to check connectivity.

    def try_cmd(self, cmd_func):
        """Wrapper function which pings the MPD server and
        in case of failure tries to re-connect before carrying out the actual command.
        """

        def func(*pargs, **kwargs):
            try:
                self.ping()
            except (mpd.ConnectionError, OSError):
                self.do_connect()
            return cmd_func(*pargs, **kwargs)

        return func

    # needs a name that does not collide with parent connect() function
    def do_connect(self, log_exception=True):
        try:
            try:
                # Attempting to disconnect
                self.disconnect()
            # if it's a TCP connection, we'll get a socket error
            # if we try to disconnect when the connection is lost
            except mpd.ConnectionError:
                pass
            # if it's a socket connection, we'll get a BrokenPipeError
            # if we try to disconnect when the connection is lost
            # but we have to retry the disconnect, because we'll get
            # an "Already connected" error if we don't.
            # the second one should succeed.
            except BrokenPipeError:
                try:
                    self.disconnect()
                except Exception:
                    pass

            if self.socket:
                self.connect(self.socket, None)
            else:
                self.connect(self.host, self.port)
            return True
        except socket.error:
            if self.log is not None and log_exception:
                self.log.error("MPD Server: connection refused!")
            return False
