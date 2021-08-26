import os
import logging
import argparse
from pytz import UTC
from typing import Callable, Tuple
from datetime import datetime, time

import vlc
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.background import BackgroundScheduler


RADIO_EKSEN_URL = 'https://ssldyg.radyotvonline.com/pozitif/smil:eksen.smil/playlist.m3u8'
LOG_DIRECTORY = os.getenv("AUTOPLAYSTUFF_LOG_DIRECTORY", os.path.split(__file__)[0])


def get_log_path():
    now = str(datetime.utcnow()).replace(" ", "").replace(":", "_").replace("-", "_")
    return os.path.join(LOG_DIRECTORY, f"autoplaystuff_{now}.log")


def get_logger():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s")

    file_handler = logging.FileHandler(get_log_path())
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


logger = get_logger()


class StreamPlayer:
    def __init__(self, stream_url: str):
        self._stream_url = stream_url
        self._instance = vlc.Instance()
        self._player = self._instance.media_player_new()
        self._media = self._instance.media_new(self._stream_url)
        self._player.set_media(self._media)

    def start(self):
        try:
            if self._player.get_state() != vlc.State.Playing:
                logger.info("Stream player started")
                self._player.play()
        except Exception as e:
            logger.exception(f"Exception while attempting to start the player:\n{e}")

    def stop(self):
        try:
            if self._player.get_state() == vlc.State.Playing:
                logger.info("Stream player stopped")
                self._player.stop()
        except Exception as e:
            logger.exception(f"Exception while attempting to stop the player:\n{e}")

    def loop(self):
        while self._player.get_state() != vlc.State.Ended:
            continue


class StreamScheduler:
    def __init__(self, stream_player: StreamPlayer, start_at_utc: time, stop_at_utc: time):
        self._stream_player = stream_player
        self._background_scheduler = BackgroundScheduler(
            timezone=UTC,
            executors={
                "default": {
                    "type": "threadpool",
                    "max_workers": 20
                }
            },
        )
        self._schedule_at(self._stream_player.start, start_at_utc)
        self._schedule_at(self._stream_player.stop, stop_at_utc)

    def _schedule_at(self, f: Callable, t: time):
        logger.debug(f"Job added to call {f} at {t} everyday")
        self._background_scheduler.add_job(
            func=f,
            trigger=CronTrigger(hour=t.hour, minute=t.minute, second=t.second, timezone=UTC)
        )

    def run(self):
        self._background_scheduler.start()
        for job in self._background_scheduler.get_jobs():
            logger.debug(f"Next run time for job {job}: {job.next_run_time}")
        self._stream_player.loop()


def to_time(t: str) -> time:
    try:
        hours, minutes = t.split(":")
        return time(hour=int(hours), minute=int(minutes))
    except Exception:
        raise ValueError(f"Invalid hour format <{t}>, expecting hh:mm")


def parse_arguments() -> Tuple:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-at", help="Start time in hh:mm format, using UTC", type=to_time, required=True)
    parser.add_argument("--stop-at", help="Stop in hh:mm format, using UTC", type=to_time, required=True)
    parser.add_argument("--jumpstart", help="Play the stream right away until hitting the first stop time",
                        action="store_true")
    args = parser.parse_args()

    return args.start_at, args.stop_at, args.jumpstart


def _main():
    start_at, stop_at, jumpstart = parse_arguments()

    stream_scheduler = StreamScheduler(
        stream_player=StreamPlayer(stream_url=RADIO_EKSEN_URL),
        start_at_utc=start_at,
        stop_at_utc=stop_at,
    )
    stream_scheduler.run()


_main()
