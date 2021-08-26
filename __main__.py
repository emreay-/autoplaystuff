import os
import sys
import logging
import argparse
from pytz import UTC
from typing import Callable, Tuple
from datetime import datetime, time, timedelta

import vlc
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
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
    def __init__(self, stream_player: StreamPlayer, ):
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

    def repeating_time_schedule(self, start_at_utc: time, stop_at_utc: time):
        self._schedule_repeat(self._stream_player.start, start_at_utc)
        self._schedule_repeat(self._stream_player.stop, stop_at_utc)

    def one_off_interval_schedule(self, play_for: timedelta):
        self._stream_player.start()
        self._schedule_one_off(self._stream_player.stop, datetime.utcnow() + play_for)

    def _schedule_repeat(self, f: Callable, t: time):
        logger.debug(f"Job added to call {f} at {t} everyday")
        self._background_scheduler.add_job(
            func=f,
            trigger=CronTrigger(hour=t.hour, minute=t.minute, second=t.second, timezone=UTC)
        )

    def _schedule_one_off(self, f: Callable, t: datetime):
        logger.debug(f"Job added to call {f} at {t} once")
        self._background_scheduler.add_job(
            func=f,
            trigger=DateTrigger(run_date=t, timezone=UTC)
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
        sys.exit(f"Invalid time format <{t}>, expecting hh:mm")


def to_timedelta(t: str) -> timedelta:
    try:
        hours, minutes = t.split(":")
        return timedelta(hours=int(hours), minutes=int(minutes))
    except Exception:
        sys.exit(f"Invalid timedelta format <{t}>, expecting hh:mm")


def parse_arguments() -> Tuple:
    parser = argparse.ArgumentParser()
    repeating_time_group = parser.add_argument_group(
        "repeating_time_group", "Arguments to schedule playing the stream everyday between set hours"
    )
    repeating_time_group.add_argument(
        "--start-at", help="Start time in hh:mm format (24hrs), using UTC", type=to_time
    )
    repeating_time_group.add_argument(
        "--stop-at", help="Stop in hh:mm format (24hrs), using UTC", type=to_time
    )
    repeating_time_group.add_argument(
        "--jumpstart", help="Play the stream right away until hitting the first stop time", action="store_true"
    )

    one_off_interval_group = parser.add_argument_group(
        "one_off_interval_group", "Arguments to schedule playing the stream one time for the set interval"
    )
    one_off_interval_group.add_argument(
        "--play-for", help="Interval in hh:mm format", type=to_timedelta
    )

    args = parser.parse_args()
    if not (args.start_at or args.stop_at or args.play_for):
        sys.exit(f"At least one of the argument groups must be provided")
    if (args.start_at or args.stop_at) and args.play_for:
        sys.exit(f"The time and interval based argument groups are mutually exclusive")
    if not args.play_for and ((args.start_at is None) ^ (args.stop_at is None)):
        sys.exit(f"Both start and stop times should be provided for this argument group")

    return args.start_at, args.stop_at, args.jumpstart, args.play_for


def _main():
    start_at, stop_at, jumpstart, play_for = parse_arguments()
    stream_player = StreamPlayer(stream_url=RADIO_EKSEN_URL)
    stream_scheduler = StreamScheduler(stream_player=stream_player)

    if start_at:
        stream_scheduler.repeating_time_schedule(start_at_utc=start_at, stop_at_utc=stop_at)
        if jumpstart:
            stream_player.start()
    elif play_for:
        stream_scheduler.one_off_interval_schedule(play_for=play_for)

    stream_scheduler.run()


_main()
