import os
import logging
import time

from read_minimed_next24 import Medtronic600SeriesDriver
from homeassistant_uploader import HomeAssistantUploader

logging.basicConfig(format='%(asctime)s %(levelname)s [%(name)s] %(message)s', level=logging.WARNING)

logger = logging.getLogger(__name__)


def get_and_upload_data(mt):
    mt.openDevice()
    try:
        mt.getDeviceInfo()
        logger.info("Device serial: {0}".format(mt.deviceSerial))
        mt.enterControlMode()
        try:
            mt.enterPassthroughMode()
            try:
                mt.openConnection()
                try:
                    mt.readInfo()
                    mt.readLinkKey()
                    try:
                        mt.negotiateChannel()
                    except Exception:
                        logger.error("Cannot connect to the pump. Abandoning")
                        return
                    mt.beginEHSM()
                    try:
                        # We need to read always the pump time to store the offset for later messaging
                        mt.getPumpTime()
                        try:
                            status = mt.getPumpStatus()
                            uploader.update_states(status)
                        except Exception:
                            logger.error("Unexpected error in client downloadOperations", exc_info=True)
                            raise
                    finally:
                        mt.finishEHSM()
                finally:
                    mt.closeConnection()
            finally:
                mt.exitPassthroughMode()
        finally:
            mt.exitControlMode()
    finally:
        mt.closeDevice()


if __name__ == '__main__':
    TOKEN = os.getenv("HOMEASSISTANT_TOKEN")
    IP = os.getenv("HOMEASSISTANT_IP")
    PORT = os.getenv("HOMEASSISTANT_PORT")
    DELAY_IN_MINUTES = 5

    uploader = HomeAssistantUploader(token=TOKEN, ip=IP, port=PORT)

    mt = Medtronic600SeriesDriver()

    while True:
        get_and_upload_data(mt)
        time.sleep(DELAY_IN_MINUTES * 60)