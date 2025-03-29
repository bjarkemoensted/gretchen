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


if __name__ == '__main__':
    pass
