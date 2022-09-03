import os
import logging
import time
import datetime
import binascii

logging.basicConfig(format='%(asctime)s %(levelname)s [%(name)s] %(message)s', level=logging.INFO)

logger = logging.getLogger(__name__)

from read_minimed_next24 import Medtronic600SeriesDriver, HISTORY_DATA_TYPE
from pump_history_parser import AlarmNotificationEvent, AlarmClearedEvent
from homeassistant_uploader import HomeAssistantUploader


def get_pump_events(mt):
    events_to_send = [AlarmNotificationEvent]

    start_date = datetime.datetime.now() - datetime.timedelta(minutes=10)
    history_pages = mt.getPumpHistory(None, start_date, datetime.datetime.max,
                                      HISTORY_DATA_TYPE.PUMP_DATA)
    events = mt.processPumpHistory(history_pages, HISTORY_DATA_TYPE.PUMP_DATA)

    events_found = {}
    for event in events:
        if type(event) in events_to_send:
            events_found[get_pump_event_id(event)] = event
        if type(event) == AlarmClearedEvent:
            if get_pump_event_id(event) in events_found:
                del events_found[get_pump_event_id(event)]

    return events_found


def get_pump_event_id(event):
    return binascii.hexlify(event.eventData[0x0B:][0:2])


def get_and_upload_data():
    mt = Medtronic600SeriesDriver()
    mt.openDevice()
    connected = False
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
                            events = get_pump_events(mt)

                            if not events:
                                uploader.update_event("")  # Reset message
                            else:
                                for event in events:
                                    logger.info(events[event])
                                    uploader.update_event(str(events[event]))
                                    time.sleep(1)  # time to process event on Homeassistant

                            connected = True
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

        if connected:
            uploader.update_status("Connected.")
        else:
            uploader.update_status("Not connected.")
            uploader.update_timestamp(datetime.datetime.now().strftime("%H:%M:%S %d.%m.%Y"))


if __name__ == '__main__':
    TOKEN = os.getenv("HOMEASSISTANT_TOKEN")
    IP = os.getenv("HOMEASSISTANT_IP")
    PORT = os.getenv("HOMEASSISTANT_PORT")
    DELAY_IN_MINUTES = 5

    uploader = HomeAssistantUploader(token=TOKEN, ip=IP, port=PORT)

    while True:
        try:
            get_and_upload_data()
        except BaseException as ex:
            print(ex)
        time.sleep(DELAY_IN_MINUTES * 60)
