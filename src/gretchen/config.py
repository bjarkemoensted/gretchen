import datetime
import logging
import logging.handlers
from pathlib import Path
import platformdirs
import time

db_path = Path.home() / "Dropbox" / "monitoring.db"
app_name = "monitoring_thingy"

local_data_dir = Path(platformdirs.user_data_dir(app_name))


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def epoch():
    return int(time.time())


def setup_standard_logfile(logger_inst: logging.Logger):
    handler = logging.handlers.TimedRotatingFileHandler(
        filename='app.log',
        when='D',
        interval=1,
        delay=False,
        backupCount=7
    )
    handler.names = lambda n: "app_wat"
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)
    logger_inst.addHandler(handler)


if __name__ == '__main__':
    pass
