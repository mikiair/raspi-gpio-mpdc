raspi-gpio-mpdc
===============
This is a configurable Python service to run on `Raspberry Pi <https://www.raspberrypi.org>`_.

**raspi-gpio-mpdc** runs a Python script as a service on Raspberry Pi. It uses the `GPIO Zero <https://github.com/gpiozero/gpiozero>`_ package which allows 
selecting among various underlying pin factories. Tested with `pigpio <http://abyz.me.uk/rpi/pigpio/index.html>`_ library only.

Various GPIO inputs can be configured to trigger certain events to control a MPD/Mopidy server. For that purpose, `python-mpd2 <https://pypi.org/project/python-mpd2/>`_ package is used as MPD client interface.

Requires
--------
* `Mopidy <https://mopidy.com/>`_ with `Mopidy-MPD <https://mopidy.com/ext/mpd>`_ extension (or any other MPD server)
* pigpiod (or any other supported pin factory package)
* Raspi GPIO Zero
* python-mpd2
* python-systemd

Installation
------------
Automated installation is not yet supported. Follow the manual steps below instead.

1. Install pigpio (or any other of the supported `pin-factories <https://gpiozero.readthedocs.io/en/stable/api_pins.html#changing-the-pin-factory>`_):

   | ``sudo apt update``
   | ``sudo apt install python3-pigpio``
  
#. To set pigpio as the default pin factory, add the following line to the end of your **~/bash.rc** file:
   
   ``export GPIOZERO_PIN_FACTORY=pigpio``

#. Reboot

#. Install GPIO Zero (if not included as a default in your OS distribution)
   
   ``sudo apt install python3-gpiozero``
   
#. Install python-systemd package

   ``sudo apt install python3-systemd``

#. Download raspi-gpio-mpdc (you most likely did this already)

   | ``wget https://github.com/mikiair/raspi-gpio-mdpc/archive/main.zip``
   | ``unzip main.zip -d ~/raspi-gpio-mpdc``

#. Configure the service according to your external circuit set-up (see Configuration_).

#. Copy the service file to **/lib/systemd/system** folder
   
   ``sudo cp ~/raspi-gpio-mpdc/raspi-gpio-mpdc.service /lib/systemd/system``
   
#. If not already included, add the *pi* user to the *gpio* group (check with ``groups pi`` command)

   ``sudo usermod -a -G gpio mopidy``
   
#. Enable the service to persist after reboot

   ``sudo systemctl enable raspi-gpio-mpdc``

Configuration
-------------

The configuration is defined in the file ``raspi-gpio-mpdc.conf``. It requires a section ``[GPIO]`` with unique keys of the pattern ``ButtonN`` or ``RotEncN`` where N is an integer number. 

1) The ``ButtonN`` key-value-pairs must be created based on this pattern:

   ``Button = input_pin_number,up|dn|upex|dnex,press|release,trigger_event[,bouncetime_ms]``

   * ``input_pin_number``
     The GPIO pin in BCM format to which a button is connected.
   * ``up|dn|upex|dnex``
     Selects the pull-up or pull-down resistor for the pin which can use Raspi internal ones, or *ex*ternal resistor provided by your circuit.
   * ``press|release``
     Determines the button event for triggering the MPD event, namely when button is *pressed* or *released*.
   * ``trigger_event``
     The MPD event to trigger. One of:
  
     * play_pause - toggle playback state between *play* and *pause*
     * play_stop - toggle playback state between *play* and *stop*
     * prev - select previous track
     * next - select next track
     * mute - toggle output state between *mute* and *unmute*
     * vol_up - increase output volume
     * vol_dn - decrease output volume
  
   * ``bouncetime_ms``
     (*optional*) Defines the time in milliseconds during which subsequent button events will be ignored.

   e.g.

   ``Button0 = 9,upex,press,mute,100``

   configures pin GPIO9 as input expecting an external pull-up resistor, and acting when button is pressed with a bounce time of 100ms, to mute/unmute the output

#) The ``RotEncN`` key-value-pairs must be created based on this pattern:

   ``RotEncN = input_pin_A,input_pin_B,rot_ccw_event,rot_cw_event``

   * ``input_pin_A,input_pin_B``
     The GPIO pins to which a rotary encoder is connected. The sequence of high-low-high transitions determines the rotation direction.
   * ``rot_ccw_event``
     The event to trigger when the rotary encoder is turned counter-clockwise. Same as for buttons.
   * ``rot_cw_event``
     The event to trigger when the rotary encoder is turned clockwise. Same as for buttons.
     
   e.g.
   
   ``RotEnc0 = 18,19,vol_dn,vol_up``
   
   configures pins GPIO18 and GPIO19 to act as inputs from a rotary encoder which turns volume down and up, respectively.
