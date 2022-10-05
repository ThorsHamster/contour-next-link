import os
import logging
import logging.handlers as handlers
import time
import datetime

logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)

logger = logging.getLogger('app')

logHandler = handlers.RotatingFileHandler('log.txt', maxBytes=1000000, backupCount=2)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

from homeassistant_connector import HomeAssistantConnector
from pump_connector import PumpConnector


if __name__ == '__main__':
    TOKEN = os.getenv("HOMEASSISTANT_TOKEN")
    IP = os.getenv("HOMEASSISTANT_IP")
    PORT = os.getenv("HOMEASSISTANT_PORT")

    home_assistant_connector = HomeAssistantConnector(token=TOKEN, ip=IP, port=PORT)
    pump_connector = PumpConnector(connector=home_assistant_connector)

    while True:
        try:
            if home_assistant_connector.switched_on():
                home_assistant_connector.update_status("Requesting data.")
                pump_connector.get_and_upload_data()
            else:
                home_assistant_connector.update_status("Deactivated.")
                pump_connector.reset_all_states()
                home_assistant_connector.update_timestamp(state=datetime.datetime.now().strftime("%H:%M:%S %d.%m.%Y"))

            pump_connector.wait()
        except BaseException as ex:
            logger.error(ex)
            time.sleep(30)
