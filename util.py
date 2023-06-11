import logging
import json
import os
# logging.getLogger()

def get_base_folderpath(args):
    if args.localdev:
        base_folderpath = os.getcwd() + '/data/'
    else:
        base_folderpath = "/home/pi/pHox/data"
    if not os.path.exists(base_folderpath):
        os.makedirs(base_folderpath)
    return base_folderpath

try:
    box_id = open("/home/pi/box_id.txt", "r").read().strip('\n')
except:
    logging.error('No box id found, using config_template.json')
    box_id = "template"

config_name = "configs/config_" + box_id + ".json"
with open(config_name) as json_file:
    config_file = json.load(json_file)


temp_probe_conf_path = 'configs/temperature_sensors_config.json'

rgb_lookup = {'red': 1, 'green': 2, 'white': 0}