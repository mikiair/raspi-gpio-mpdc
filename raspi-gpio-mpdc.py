#!/usr/bin/env python

__author__ = "Michael Heise"
__copyright__ = "Copyright (C) 2022-2025 by Michael Heise"
__license__ = "Apache License Version 2.0"
__version__ = "1.0.1"
__date__ = "06/14/2025"

"""MPD/Mopidy client which is controlled by GPIO Zero on Raspberry Pi
"""

#    Copyright 2022-2025 Michael Heise (mikiair)
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
import logging
import signal
import sys
import time

# 3rd party imports
import gpiozero

# local imports
from raspimpdc import RaspiBaseMPDClient


class RaspiGPIOMPDClient(RaspiBaseMPDClient):
    VALUES_PULLUPDN = ["up", "dn", "upex", "dnex"]
    VALUES_PRESSRELEASE = ["press", "release"]

    PUD_SWITCHER = {
        0: (True, None),
        1: (False, None),
        2: (None, False),
        3: (None, True),
    }

    def __init__(self):
        super().__init__()

        self._buttons = []
        self._rotencs = []
        self._usedpins = []

        self.isValidGPIO = False

    def initLogging(self, log=None):
        """Initialize logging to journal"""
        super().initLogging(log)

        pinf = type(gpiozero.Device._default_pin_factory()).__name__
        self._log.info(f"GPIO Zero default pin factory: {pinf}")

    def checkConfig(self):
        """Return True if the configuration has mandatory section GPIO."""
        return self.config.has_section("GPIO")

    def configButton(self, buttonConfig):
        """Configure one button"""
        pin = self.getButtonPin(buttonConfig[0])
        if pin == -1:
            return False

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
            bouncetime = 50

        return self.setupButton(pin, pud, active, event, triggered_event, bouncetime)

    def setupButton(self, pin, pull, active, event, triggered_event, bouncetime):
        """Setup GPIOZero object for button"""
        try:
            button = gpiozero.Button(
                pin,
                pull_up=pull,
                active_state=active,
                bounce_time=0.001 * bouncetime,
            )
            self._usedpins.append(pin)

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
        pinA, pinB = self.getRotEncPins(rotencConfig[0], rotencConfig[1])
        if pinA == -1 or pinB == -1:
            return False

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
            bouncetime = 20

        return self.setupRotEnc(
            pinA,
            pinB,
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
                pinA, pinB, bounce_time=0.001 * bouncetime, max_steps=50
            )

            self._usedpins.append(pinA)
            self._usedpins.append(pinB)

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

    def getButtonPin(self, pinStr):
        """Return the BCM pin number of a button if this was not used before.

        Otherwise return -1."""
        try:
            pin = int(pinStr)

            if pin in self._usedpins:
                self._log.error(f"Pin {pin} already in use!")
                return -1

            return pin
        except Exception as e:
            self._log.error(f"Invalid pin configuration! ({e})")
            return -1

    def getRotEncPins(self, pinAStr, pinBStr):
        """Return the BCM pin numbers of a rotary encoder if these were not used before.

        Otherwise return -1 for the wrong pin."""
        try:
            pinA = int(pinAStr)
            pinB = int(pinBStr)

            if pinA == pinB:
                self._log.error("Pins must be different for rotary encoder!")
                return -1, -1

            if pinA in self._usedpins:
                self._log.error(f"Pin {pinA} already in use!")
                return -1, 0

            if pinB in self._usedpins:
                self._log.error(f"Pin {pinB} already in use!")
                return 0, -1

            return pinA, pinB
        except Exception as e:
            self._log.error(f"Invalid pin configuration! ({e})")
            return -1, -1

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

    def initGPIO(self):
        """Evaluate the data read from config file to set the GPIO inputs"""
        self._log.info("Init GPIO configuration.")
        configGPIO = self.config["GPIO"]

        self._vol_step = 1

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


def sigterm_handler(_signo, _stack_frame):
    """Clean exit on SIGTERM signal (when systemd stops the process)"""
    sys.exit(0)


def main():
    # install handler
    signal.signal(signal.SIGTERM, sigterm_handler)

    log = None
    mpdclient = None

    try:
        log = logging.getLogger(__name__)

        mpdclient = RaspiGPIOMPDClient()
        if log:
            mpdclient.initLogging(log)

        if not mpdclient.readConfigFile():
            sys.exit(-2)

        if not mpdclient.checkConfig():
            log.error("Invalid configuration file! (section [GPIO] missing)")
            sys.exit(-3)

        mpdclient.setLogLevel()

        if not mpdclient.initGPIO():
            log.error("Init GPIO failed!")
            sys.exit(-3)

        if not mpdclient.initMPD():
            log.error("Init MPD connection failed!")
            sys.exit(-4)

        if not mpdclient.isConnected and not mpdclient.connectMPD():
            log.error("Could not connect to MPD server - possibly timed out!")
            sys.exit(-5)

        log.info("Enter raspi-gpio-mpdc service loop...")
        while True:
            time.sleep(0.1)

    except Exception as e:
        if log:
            log.exception(f"Unhandled exception: {e}")
        sys.exit(-1)
    finally:
        if mpdclient and mpdclient.isConnected:
            if log:
                log.info("Disconnect from MPD.")
            mpdclient.mpd.disconnect()


# run as script only
if __name__ == "__main__":
    main()
