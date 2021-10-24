#!/usr/bin/env python

__author__ = "Michael Heise"
__copyright__ = "Copyright (C) 2021 by Michael Heise"
__license__ = "Apache License Version 2.0"
__version__ = "0.0.3"
__date__ = "10/24/2021"

"""MPD/Mopidy client which is controlled by GPIO Zero on Raspberry Pi
"""

#    Copyright 2021 Michael Heise (mikiair)
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

# standard imports
import configparser
import logging
import signal
import socket
import sys
import time
import weakref

# 3rd party imports
import gpiozero
import mpd
from systemd.journal import JournalHandler

# local imports
# - none -


class PersistentMPDClient(mpd.MPDClient):
    def __init__(self, socket=None, host=None, port=None):
        super(PersistentMPDClient, self).__init__()
        self.socket = socket
        self.host = host
        self.port = port

        self.do_connect()
        # get list of available commands from client
        self.command_list = self.commands()

        # commands not to intercept
        self.command_blacklist = ["ping"]

        # wrap all valid MPDClient functions
        # in a ping-connection-retry wrapper
        for cmd in self.command_list:
            if cmd not in self.command_blacklist:
                if hasattr(super(PersistentMPDClient, self), cmd):
                    super_fun = super(PersistentMPDClient, self).__getattribute__(cmd)
                    new_fun = self.try_cmd(super_fun)
                    # print("Setting interceptor for {}".format(cmd))
                    setattr(self, cmd, new_fun)
                else:
                    print("Attr {} not available!".format(cmd))

    # create a wrapper for a function (such as an MPDClient
    # member function) that will verify a connection (and
    # reconnect if necessary) before executing that function.
    # functions wrapped in this way should always succeed
    # (if the server is up)
    # we ping first because we don't want to retry the same
    # function if there's a failure, we want to use the noop
    # to check connectivity
    def try_cmd(self, cmd_fun):
        def fun(*pargs, **kwargs):
            try:
                self.ping()
            except (mpd.ConnectionError, OSError):
                #                print("lost connection.")
                #                print("trying to reconnect.")
                self.do_connect()
            return cmd_fun(*pargs, **kwargs)

        return fun

    # needs a name that does not collide with parent connect() function
    def do_connect(self):
        try:
            try:
                #                print("Attempting to disconnect.")
                self.disconnect()
            # if it's a TCP connection, we'll get a socket error
            # if we try to disconnect when the connection is lost
            except mpd.ConnectionError:
                #                print("Disconnect failed, so what?")
                pass
            # if it's a socket connection, we'll get a BrokenPipeError
            # if we try to disconnect when the connection is lost
            # but we have to retry the disconnect, because we'll get
            # an "Already connected" error if we don't.
            # the second one should succeed.
            except BrokenPipeError:
                #                print("Pipe closed, retrying disconnect.")
                try:
                    #                    print("Retrying disconnect.")
                    self.disconnect()
                except Exception:
                    #                    print("Second disconnect failed, yikes.")
                    #                    print(e)
                    pass
            if self.socket:
                #                print("Connecting to {}".format(self.socket))
                self.connect(self.socket, None)
            else:
                #                print("Connecting to {}:{}".format(self.host, self.port))
                self.connect(self.host, self.port)
        except socket.error:
            print("Connection refused.")


#            print(e)


class RaspiGPIOMPDClient:
    CONFIGFILE = "/etc/raspi-gpio-mpdc.conf"

    VALUES_PULLUPDN = ["up", "dn", "upex", "dnex"]
    VALUES_PRESSRELEASE = ["press", "release"]
    VALUES_TRIGGERED_EVENTS = [
        "none",
        "play_stop",
        "play_pause",
        "prev_track",
        "next_track",
        "mute",
        "vol_dn",
        "vol_up",
        "prev_src",
        "next_src",
    ]

    PUD_SWITCHER = {
        0: (True, None),
        1: (False, None),
        2: (None, False),
        3: (None, True),
    }

    def __init__(self):
        self._finalizer = weakref.finalize(self, self.finalize)
        self._buttons = []
        self._rotencs = []

        self.isValidGPIO = False
        self.isConnected = False

        self.config = None
        self.mpd = None

        self.btn_held = {}

    def remove(self):
        self._finalizer()

    @property
    def removed(self):
        return not self._finalizer.alive

    def finalize(self):
        if self.mpd:
            self.mpd.disconnect()

    def initLogging(self, log):
        """initialize logging to journal"""
        log_fmt = logging.Formatter("%(levelname)s %(message)s")
        logHandler = JournalHandler()
        logHandler.setFormatter(log_fmt)
        log.addHandler(logHandler)
        # log.setLevel(logging.INFO)
        log.setLevel(logging.DEBUG)
        self._log = log
        self._log.info("Initialized logging.")

        pinf = type(gpiozero.Device._default_pin_factory()).__name__
        self._log.info(f"GPIO Zero default pin factory: {pinf}")
        return

    def readConfigFile(self):
        """read the config file"""
        try:
            self._log.info(f"Reading configuration file... '{self.CONFIGFILE}")
            self.config = configparser.ConfigParser()
            self.config.read(self.CONFIGFILE)
            return True
        except Exception:
            self._log.error(f"Accessing config file '{self.CONFIGFILE}' failed!")
            return False

    def initMPD(self):
        """establish the connection to MPD server"""
        try:
            self._log.info("Connect to MPD.")
            configMPD = self.config["MPD"]

            if (
                not configMPD
                or "mpdhost" not in configMPD
                or configMPD["mpdhost"] == ""
            ):
                host = "localhost"
            else:
                host = configMPD["mpdhost"]

            if (
                not configMPD
                or "mpdport" not in configMPD
                or configMPD["mpdport"] == ""
            ):
                port = 6600
            else:
                port = configMPD["mpdport"]

            self._log.info(f"Host: {host}@{port}")

            self.mpd = PersistentMPDClient(host=host, port=port)

            self._log.debug(self.mpd.status())

            self.isConnected = True
            return True
        except Exception as e:
            self._log.error(f"Connection to MPD failed! ({e})")
            return False

    def configButton(self, buttonConfig):
        """configure one button"""
        pudMode = self.checkResistor(buttonConfig[1])
        if pudMode == -1:
            return False

        try:
            pud, active = self.PUD_SWITCHER[pudMode]
        except Exception as e:
            self._log.error(f"Could not convert pull resistor configuration! ({e})")
            return False

        eventStr = buttonConfig[2]
        if not self.checkButtonEvent(eventStr):
            return False

        event = True if eventStr == "press" else False

        triggered_event = buttonConfig[3]
        if not self.checkTriggeredEvent(triggered_event):
            return False

        if len(buttonConfig) == 5:
            try:
                bouncetime = int(buttonConfig[4])
            except Exception:
                self._log.error("Invalid bounce time! (only integer >0 allowed)")
                return False
        else:
            bouncetime = 100

        return self.setupButton(
            buttonConfig[0], pud, active, event, triggered_event, bouncetime
        )

    def setupButton(self, pin, pull, active, event, triggered_event, bouncetime):
        """setup GPIOZero object for button"""
        try:
            button = gpiozero.Button(
                int(pin),
                pull_up=pull,
                active_state=active,
                bounce_time=0.001 * bouncetime,
            )

            event_func = getattr(self, triggered_event)

            if not event_func:
                raise ValueError("Could not determine event function!")

            if event:
                button.when_pressed = event_func
            else:
                button.when_released = event_func

            self._buttons.append(button)
            return True
        except Exception as e:
            self._log.error(f"Error while setting up GPIO input for button! ({e})")
            return False

    def configRotEnc(self, rotencConfig):
        """Configure one rotary encoder"""
        pudMode = self.checkResistor(rotencConfig[2])
        if pudMode == -1:
            return False

        try:
            pud, active = self.PUD_SWITCHER[pudMode]
        except Exception as e:
            self._log.error(f"Could not convert pull resistor configuration! ({e})")
            return False

        triggered_event_ccw = rotencConfig[3]
        if not self.checkTriggeredEvent(triggered_event_ccw):
            return False

        triggered_event_cw = rotencConfig[4]
        if not self.checkTriggeredEvent(triggered_event_cw):
            return False

        if len(rotencConfig) == 6:
            try:
                bouncetime = int(rotencConfig[5])
            except Exception:
                self._log.error("Invalid bounce time! (only integer >0 allowed)")
                return False
        else:
            bouncetime = 100

        return self.setupRotEnc(
            rotencConfig[0],
            rotencConfig[1],
            pud,
            triggered_event_ccw,
            triggered_event_cw,
            bouncetime,
        )

    def setupRotEnc(
        self, pinA, pinB, pull, triggered_ccw_event, triggered_cw_event, bouncetime
    ):
        """Setup GPIOZero rotary encoder object"""
        try:
            rotenc = gpiozero.RotaryEncoder(
                int(pinA), int(pinB), bounce_time=0.001 * bouncetime, max_steps=50
            )

            event_func_ccw = getattr(self, triggered_ccw_event)
            if not event_func_ccw:
                raise ValueError("Could not determine event function!")

            event_func_cw = getattr(self, triggered_cw_event)
            if not event_func_cw:
                raise ValueError("Could not determine event function!")

            rotenc.when_rotated_counter_clockwise = event_func_ccw
            rotenc.when_rotated_clockwise = event_func_cw

            self._rotencs.append(rotenc)
            return True
        except Exception as e:
            self._log.error(
                f"Error while setting up GPIO input for rotary encoder! ({e})"
            )
            return False

    def checkResistor(self, pudStr):
        """Return index if string is found in pre-defined values for pull resistor types"""
        try:
            return self.VALUES_PULLUPDN.index(pudStr)
        except Exception:
            self._log.error(
                "Invalid resistor configuration! Only one of {0} allowed!".format(
                    "/".join(self.VALUES_PULLUPDN)
                )
            )
            return -1

    def checkButtonEvent(self, buttonEvent):
        """Return if string is in pre-defined values for button events"""
        if buttonEvent not in self.VALUES_PRESSRELEASE:
            self._log.error(
                "Invalid event configuration! Only 'PRESS' or 'RELEASE' allowed!"
            )
            return False
        return True

    def checkTriggeredEvent(self, triggeredEvent):
        """Return true if string..."""
        if triggeredEvent not in self.VALUES_TRIGGERED_EVENTS:
            self._log.error(
                "Invalid event! Only one of {0} allowed!".format(
                    "/".join(self.VALUES_TRIGGERED_EVENTS)
                )
            )
            return False
        return True

    def initGPIO(self):
        """evaluate the data read from config file to set the GPIO inputs"""
        self._log.info("Init GPIO configuration.")
        configGPIO = self.config["GPIO"]

        self._vol_step = 5

        for key, value in configGPIO.items():
            if key.startswith("button"):
                self._log.info(f"Button configuration '{key} = {value}'")
                if not self.configButton(value.lower().split(",")):
                    return False
                continue

            if key.startswith("rotenc"):
                self._log.info(f"RotEnc configuration '{key} = {value}'")
                if not self.configRotEnc(value.lower().split(",")):
                    return False
                continue

            self._log.info(f"Invalid key '{key}'!")
            return False

        self.isValidGPIO = True
        return True

    # trigger event handlers

    def none(self):
        pass

    def play_pause(self):
        self._log.debug("play_pause: ")
        prev_state = self.mpd.status()["state"]
        if prev_state == "play":
            self.mpd.pause()
        else:
            self.mpd.play()
        self._log.debug(prev_state + "->" + self.mpd.status()["state"])

    def play_stop(self):
        self._log.debug("play_stop: ")
        prev_state = self.mpd.status()["state"]
        if prev_state == "play":
            self.mpd.stop()
        else:
            self.mpd.play()
        self._log.debug(prev_state + "->" + self.mpd.status()["state"])

    def prev_track(self):
        self._log.debug("prev_track")
        self.mpd.previous()
        self._log.debug(self.mpd.status())

    def next_track(self):
        self._log.debug("next_track")
        self.mpd.next()
        self._log.debug(self.mpd.status())

    def mute(self):
        self._log.debug("mute")
        self.mpd.toggleoutput(0)
        self._log.debug(self.mpd.status())

    def vol_dn(self):
        self._log.debug("vol_dn")
        prev_vol = int(self.mpd.status()["volume"])
        if prev_vol > 0:
            if prev_vol >= self._vol_step:
                self.mpd.volume(-self._vol_step)
            else:
                self.mpd.volume(0)
            self._log.debug(str(prev_vol) + "->" + str(self.mpd.status()["volume"]))

    def vol_up(self):
        self._log.debug("vol_up")
        prev_vol = int(self.mpd.status()["volume"])
        if prev_vol < 100:
            if prev_vol + self._vol_step <= 100:
                self.mpd.volume(+self._vol_step)
            else:
                self.mpd.volume(100)
            self._log.debug(str(prev_vol) + "->" + str(self.mpd.status()["volume"]))

    def prev_src(self):
        pass

    def next_src(self):
        pass


def sigterm_handler(_signo, _stack_frame):
    """clean exit on SIGTERM signal (when systemd stops the process)"""
    sys.exit(0)


# install handler
signal.signal(signal.SIGTERM, sigterm_handler)

log = None
mpdclient = None

try:
    log = logging.getLogger(__name__)

    mpdclient = RaspiGPIOMPDClient()
    mpdclient.initLogging(log)

    if not mpdclient.readConfigFile():
        sys.exit(-2)

    if not mpdclient.config["GPIO"]:
        log.error("Invalid configuration file! (No [GPIO] section)")
        sys.exit(-3)

    if not mpdclient.initMPD():
        log.error("Init MPD connection failed!")
        sys.exit(-4)

    if not mpdclient.initGPIO():
        log.error("Init GPIO failed!")
        sys.exit(-3)

    log.info("Enter raspi-gpio-mpdc service loop...")
    while True:
        time.sleep(1)

except Exception as e:
    if log:
        log.exception(f"Unhandled exception: {e}")
    sys.exit(-1)
finally:
    if mpdclient and mpdclient.isConnected:
        if log:
            log.info("Disconnect from MPD.")
        mpdclient.mpd.disconnect()
