import logging
import json
import os
logging.getLogger()
base_folderpath = "/home/pi/pHox/data"

if not os.path.exists(base_folderpath):
    os.makedirs(base_folderpath)

try:
    box_id = open("/home/pi/box_id.txt", "r").read().strip('\n')
except:
    logging.error('No box id found, using config_template.json')
    box_id = "template"

config_name = "configs/config_" + box_id + ".json"
with open(config_name) as json_file:
    config_file = json.load(json_file)


