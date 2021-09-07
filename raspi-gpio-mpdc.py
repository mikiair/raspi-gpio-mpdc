#!/usr/bin/env python

__author__ = "Michael Heise"
__copyright__ = "Copyright (C) 2021 by Michael Heise"
__license__ = "Apache License Version 2.0"
__version__ = "0.0.2"
__date__ = "09/07/2021"

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
import sys
import weakref
import signal
import logging

# 3rd party imports
import gpiozero
from systemd.journal import JournalHandler
from mpd import MPDClient

# local imports
# - none -


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

        self.isValidGPIO = False

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
        log.setLevel(logging.INFO)
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

            if not configMPD:
                host = "localhost"
            else:
                host = configMPD["mpdhost"]

            self.mpd = MPDClient()
            self.mpd.timeout = 10
            self.mpd.idletimeout = None
            self.mpd.connect(host, 6600)
            self.mpd.close()
            self.mpd.disconnect()
        except Exception as e:
            self._log.error(f"Connection to MPD failed! ({e})")

    def configButton(self, buttonConfig):
        """configure one button"""
        pudMode = checkResistor(buttonConfig[1])
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
        if not checkTriggeredEvent(triggered_event):
            return False

        if len(buttonConfig) == 5:
            try:
                bouncetime = int(buttonConfig[4])
            except:
                self._log.error("Invalid bounce time! (only integer >0 allowed)")
                return False
        else:
            bouncetime = 100

        return setupButton(
            buttonConfig[0], pud, active, event, triggered_event, bouncetime
        )

    def setupButton(self, pin, pull, active, event, triggered_event):
        """setup GPIOZero object for button"""
        try:
            button = gpiozero.Button(
                int(pin),
                pull_up=pull,
                active_state=active,
                bounce_time=0.001 * bouncetime,
            )
            event_func = getattr(self, triggered_event)
            if event:
                button.when_pressed = event_func
            else:
                button.when_released = event_func
            return True
        except Except as e:
            self._log.error("Error while setting up GPIO input for button! ({e})")
            return False

    def configRotEnc(self, rotencConfig):
        """Configure one rotary encoder"""
        pass

    def setupRotEnc(self, pinA, pinB, pull, triggered_ccw_event, triggered_cw_event):
        """Setup GPIOZero rotary encoder object"""
        pass

    def checkResistor(self, pudStr):
        """Return index if string is found in pre-defined values for pull resistor types"""
        try:
            return self.VALUES_PULLUPDNUPDN.index(pudStr)
        except:
            self._log.error(
                "Invalid resistor configuration! Only one of {0} allowed!".format(
                    self.VALUES_PULLUPDNUPDN.join("/")
                )
            )
            return -1

    def checkButtonEvent(self, buttonEvent):
        """Return if string is in pre-defined values for button events"""
        if not buttonEvent in self.VALUES_PRESSRELEASE:
            self._log.error(
                "Invalid event configuration! Only 'PRESS' or 'RELEASE' allowed!"
            )
            return False
        return True

    def checkTriggeredEvent(self, triggeredEvent):
        """Return true if string..."""
        if not triggeredEvent in self.VALUES_TRIGGERED_EVENTS:
            self._log.error(
                "Invalid event! Only one of {0} allowed!".format(
                    self.VALUES_TRIGGERED_EVENTS.join("/")
                )
            )
            return False
        return True

    def initGPIO(self):
        """evaluate the data read from config file to set the GPIO inputs"""
        self._log.info("Init GPIO configuration.")
        configGPIO = self.config["GPIO"]

        self._vol_step = 5

        for key, value in configGPIO:
            if key.starts_with("Button"):
                self._log.info(f"Button configuration '{key} = {value}'")
                if not self.configButton(value.lower().split(",")):
                    return False
                continue

            if key.starts_with("RotEnc"):
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
        if self.mpd.status()["state"] == "play":
            self.mpd.pause()
        else:
            self.mpd.play()

    def play_stop(self):
        if self.mpd.status()["state"] == "play":
            self.mpd.stop()
        else:
            self.mpd.play()

    def prev_track(self):
        self.mpd.previous()

    def next_track(self):
        self.mpd.next()

    def mute(self):
        self.mpd.toggleoutput(0)

    def vol_dn(self):
        self.mpd.volume(-self._vol_step)

    def vol_up(self):
        self.mpd.volue(+self._vol_step)

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

    if not mpdclient.initGPIO():
        log.error("Init GPIO failed!")
        sys.exit(-3)

    log.info("Enter service loop...")
    while True:
        pass

except Exception as e:
    if log:
        log.exception("Unhandled exception: {0}".format(e.args[0]))
    sys.exit(-1)
finally:
    if mpdclient and mpdclient.isConnected:
        if log:
            log.info("Disconnect from MPD.")
        mpdclient.disconnect()
