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


def update_states(uploader, medtronic_pump_status):
    if is_data_valid(medtronic_pump_status):
        uploader.update_status("Connected.")

        uploader.update_bgl(state=medtronic_pump_status.sensorBGL)
        uploader.update_trend(state=medtronic_pump_status.trendArrow)
        uploader.update_active_insulin(state=medtronic_pump_status.activeInsulin)
        uploader.update_current_basal_rate(state=medtronic_pump_status.currentBasalRate)
        uploader.update_temp_basal_rate(state=medtronic_pump_status.tempBasalRate)
        uploader.update_temp_basal_rate_percentage(state=medtronic_pump_status.tempBasalPercentage)
        uploader.update_pump_battery_level(state=medtronic_pump_status.batteryLevelPercentage)
        uploader.update_insulin_units_remaining(state=medtronic_pump_status.insulinUnitsRemaining)
    else:
        uploader.update_status("Invalid data.")

        uploader.update_bgl(state="")
        uploader.update_trend(state="")
        uploader.update_active_insulin(state="")
        uploader.update_current_basal_rate(state="")
        uploader.update_temp_basal_rate(state="")
        uploader.update_temp_basal_rate_percentage(state="")
        uploader.update_pump_battery_level(state="")
        uploader.update_insulin_units_remaining(state="")


def is_data_valid(medtronic_pump_status) -> bool:
    invalid_sensor_values = [0, 770]
    return str(medtronic_pump_status.sensorBGLTimestamp.strftime(
        "%d.%m.%Y")) != "01.01.1970" and medtronic_pump_status.sensorBGL not in invalid_sensor_values


def get_and_upload_data() -> datetime.datetime:
    mt = Medtronic600SeriesDriver()
    mt.openDevice()
    connected = False
    status = None
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
                        return datetime.datetime.now()
                    mt.beginEHSM()
                    try:
                        # We need to read always the pump time to store the offset for later messaging
                        mt.getPumpTime()
                        try:
                            status = mt.getPumpStatus()
                            update_states(uploader, status)
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
            return status.sensorBGLTimestamp
        else:
            uploader.update_status("Not connected.")
            return datetime.datetime.now()


if __name__ == '__main__':
    TOKEN = os.getenv("HOMEASSISTANT_TOKEN")
    IP = os.getenv("HOMEASSISTANT_IP")
    PORT = os.getenv("HOMEASSISTANT_PORT")
    DELAY_IN_MINUTES = 5

    uploader = HomeAssistantUploader(token=TOKEN, ip=IP, port=PORT)

    waiting_time = datetime.datetime.now() + datetime.timedelta(minutes=5)
    while True:
        try:
            timestamp = get_and_upload_data()
            uploader.update_timestamp(state=timestamp.strftime("%H:%M:%S %d.%m.%Y"))

            waiting_time = timestamp.replace(tzinfo=None) + datetime.timedelta(minutes=5,
                                                                               seconds=30) - datetime.datetime.now()
        except BaseException as ex:
            print(ex)
        if waiting_time.seconds < 30:
            time.sleep(30)
        elif waiting_time.seconds > (6 * 60):
            time.sleep(6 * 60)
        else:
            time.sleep(waiting_time.seconds)
