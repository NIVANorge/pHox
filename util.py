import logging
import json
logging.getLogger()

try:
    box_id = open("/home/pi/box_id.txt", "r").read().strip('\n')
except:
    logging.error('No box id found, using config_template.json')
    box_id = "template"

config_name = "configs/config_" + box_id + ".json"
with open(config_name) as json_file:
    config_file = json.load(json_file)
