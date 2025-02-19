#!/usr/bin/env python3

# This is the Drew hack v0.1 10/01/22 of the Pimoroni Enviro+ Code.
# It ditches the screen and the temperature compensate.

import requests
import time
from bme280 import BME280
from pms5003 import PMS5003, ReadTimeoutError, ChecksumMismatchError
from subprocess import check_output

try:
    from smbus2 import SMBus
except ImportError:
    from smbus import SMBus
import logging

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

logging.info("""luftdaten.py - Reads temperature, pressure, humidity,
#PM2.5, and PM10 and sends data to Luftdaten / sensor.community,
#the citizen science air quality project.

#Note: you'll need to register with Sensor Community at:
#https://devices.sensor.community/ and enter your Raspberry Pi
#serial number (from Terminal) before the data appears on the
#Sensor Community map.

#Press Ctrl+C to exit!

#""")

bus = SMBus(1)

bme280 = BME280(i2c_dev=bus)
pms5003 = PMS5003()


# Read values from BME280 and PMS5003 and return as dict
def read_values():
    values = {}
    raw_temp = bme280.get_temperature()
    comp_temp = raw_temp 
    values["temperature"] = "{:.2f}".format(comp_temp)
    values["pressure"] = "{:.2f}".format(bme280.get_pressure() * 100)
    values["humidity"] = "{:.2f}".format(bme280.get_humidity())
    try:
        pm_values = pms5003.read()
        values["P2"] = str(pm_values.pm_ug_per_m3(2.5))
        values["P1"] = str(pm_values.pm_ug_per_m3(10))
    except(ReadTimeoutError, ChecksumMismatchError):
        logging.info("Failed to read PMS5003. Reseting and retrying.")
        pms5003.reset()
        pm_values = pms5003.read()
        values["P2"] = str(pm_values.pm_ug_per_m3(2.5))
        values["P1"] = str(pm_values.pm_ug_per_m3(10))
    return values


# Get Raspberry Pi serial number to use as ID
def get_serial_number():
    with open('/proc/cpuinfo', 'r') as f:
        for line in f:
            if line[0:6] == 'Serial':
                return line.split(":")[1].strip()


# Check for Wi-Fi connection
def check_wifi():
    if check_output(['hostname', '-I']):
        return True
    else:
        return False


def send_to_luftdaten(values, id):
    pm_values = dict(i for i in values.items() if i[0].startswith("P"))
    temp_values = dict(i for i in values.items() if not i[0].startswith("P"))

    pm_values_json = [{"value_type": key, "value": val} for key, val in pm_values.items()]
    temp_values_json = [{"value_type": key, "value": val} for key, val in temp_values.items()]

    resp_pm = None
    resp_bmp = None

    try:
        resp_pm = requests.post(
            "https://api.sensor.community/v1/push-sensor-data/",
            json={
                "software_version": "enviro-plus 0.0.1",
                "sensordatavalues": pm_values_json
            },
            headers={
                "X-PIN": "1",
                "X-Sensor": id,
                "Content-Type": "application/json",
                "cache-control": "no-cache"
            },
            timeout=5
        )
    except requests.exceptions.ConnectionError as e:
        logging.warning('Sensor.Community PM Connection Error: {}'.format(e))
    except requests.exceptions.Timeout as e:
        logging.warning('Sensor.Community PM Timeout Error: {}'.format(e))
    except requests.exceptions.RequestException as e:
        logging.warning('Sensor.Community PM Request Error: {}'.format(e))

    try:
        resp_bmp = requests.post(
            "https://api.sensor.community/v1/push-sensor-data/",
            json={
                "software_version": "enviro-plus 0.0.1",
                "sensordatavalues": temp_values_json
            },
            headers={
                "X-PIN": "11",
                "X-Sensor": id,
                "Content-Type": "application/json",
                "cache-control": "no-cache"
            },
            timeout=5
        )
    except requests.exceptions.ConnectionError as e:
        logging.warning('Sensor.Community Climate Connection Error: {}'.format(e))
    except requests.exceptions.Timeout as e:
        logging.warning('Sensor.Community Climate Timeout Error: {}'.format(e))
    except requests.exceptions.RequestException as e:
        logging.warning('Sensor.Community Climate Request Error: {}'.format(e))

    if resp_pm is not None and resp_bmp is not None:
        if resp_pm.ok and resp_bmp.ok:
            return True
        else:
            logging.warning('Sensor.Community Error. PM: {}, Climate: {}'.format(resp_pm.reason, resp_bmp.reason))
            return False
    else:
        return False


# Raspberry Pi ID to send to Luftdaten
id = "raspi-" + get_serial_number()


# Log Raspberry Pi serial and Wi-Fi status
logging.info("Raspberry Pi serial: {}".format(get_serial_number()))
logging.info("Wi-Fi: {}\n".format("connected" if check_wifi() else "disconnected"))

time_since_update = 0
update_time = time.time()

# Main loop to read data, display, and send to Luftdaten
while True:
    try:
        values = read_values()
        time_since_update = time.time() - update_time
        if time_since_update > 145:
            logging.info(values)
            update_time = time.time()
            if send_to_luftdaten(values, id):
                logging.info("Sensor.Community Response: OK")
            else:
                logging.warning("Sensor.Community Response: Failed")
    except Exception as e:
        logging.warning('Main Loop Exception: {}'.format(e))
