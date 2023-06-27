import logging
import json
import os

def get_base_folderpath(args):
    if args.localdev:
        base_folderpath = os.getcwd() + '/data/'
    else:
        base_folderpath = "/home/pi/pHox/data"
    if not os.path.exists(base_folderpath):
        os.makedirs(base_folderpath)
    return base_folderpath

try:
    with open("/home/pi/box_id.txt", "r", encoding="utf-8") as file:
        BOX_ID = file.read().strip('\n')
except FileNotFoundError:
    logging.error('No box id found, using config_template.json')
    BOX_ID = "template"

CONFIG_NAME = "configs/config_" + BOX_ID + ".json"
with open(CONFIG_NAME, "r", encoding="utf-8") as json_file:
    CONFIG_FILE = json.load(json_file)

TEMP_PROBE_CONF_PATH = 'configs/temperature_sensors_config.json'

RGB_LOOKUP = {'red': 1, 'green': 2, 'white': 0}
