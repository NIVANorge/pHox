import logging
import json
import os
from pathlib import Path

def get_base_folderpath(args):
    base_folderpath = f"{Path().home()}/pHox_data"
    # if args.localdev:
    #     base_folderpath = os.getcwd() + '/data/'
    # else:
    #     base_folderpath = f"{Path().home()}/pHox/data"
    if not os.path.exists(base_folderpath):
        os.makedirs(base_folderpath)
    return base_folderpath

try:
    with open(f"{Path().home()}/box_id.txt", "r", encoding="utf-8") as file:
        BOX_ID = file.read().strip('\n')
        BOX_ID = "template" if BOX_ID == 'pHox0' else BOX_ID
except FileNotFoundError:
    logging.error('No box id found, using config_template.json')
    BOX_ID = "template"

dirname = os.path.dirname(__file__)
CONFIG_NAME = os.path.join(dirname, "configs/config_" + BOX_ID + ".json")
with open(CONFIG_NAME, "r", encoding="utf-8") as json_file:
    CONFIG_FILE = json.load(json_file)

TEMP_PROBE_CONF_PATH = os.path.join(dirname, 'configs/temperature_sensors_config.json')

RGB_LOOKUP = {'red': 1, 'green': 2, 'white': 0}
