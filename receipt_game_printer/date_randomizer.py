from __future__ import annotations

import calendar
import random
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RandomDateTimeOptions:
    enabled: bool
    year: int
    month: int
    random_days: bool
    random_times: bool
    avoid_night_hours: bool
    start_time: str
    end_time: str
    allow_same_day: bool


def parse_hour_minute(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.strip().split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise ValueError("Saat aralığı HH:MM formatında olmalı") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Saat aralığı geçersiz")
    return hour, minute


def _minute_of_day(value: str) -> int:
    hour, minute = parse_hour_minute(value)
    return hour * 60 + minute


def validate_options(options: RandomDateTimeOptions) -> None:
    if not (1 <= options.month <= 12):
        raise ValueError("Ay seçimi 1-12 arasında olmalı")
    if not (1900 <= options.year <= 2100):
        raise ValueError("Yıl seçimi geçersiz")
    start = _minute_of_day(options.start_time)
    end = _minute_of_day(options.end_time)
    if start > end:
        raise ValueError("Başlangıç saat bitiş saatinden büyük olamaz")


def build_random_datetimes(count: int, options: RandomDateTimeOptions) -> list[datetime]:
    validate_options(options)
    if count <= 0:
        return []

    _, days_in_month = calendar.monthrange(options.year, options.month)
    if options.random_days:
        days = list(range(1, days_in_month + 1))
        if options.allow_same_day:
            selected_days = [random.choice(days) for _ in range(count)]
        else:
            random.shuffle(days)
            selected_days = []
            while len(selected_days) < count:
                remaining = days.copy()
                random.shuffle(remaining)
                selected_days.extend(remaining)
            selected_days = selected_days[:count]
    else:
        selected_days = [1 for _ in range(count)]

    if options.random_times:
        start_minute = _minute_of_day(options.start_time)
        end_minute = _minute_of_day(options.end_time)
        if options.avoid_night_hours:
            start_minute = max(start_minute, 8 * 60)
            end_minute = min(end_minute, 22 * 60 + 59)
        if start_minute > end_minute:
            raise ValueError("Saat aralığı geçersiz")
    else:
        start_minute = end_minute = _minute_of_day(options.start_time)

    result = []
    for day in selected_days:
        minute_of_day = random.randint(start_minute, end_minute)
        hour = minute_of_day // 60
        minute = minute_of_day % 60
        second = random.randint(0, 59) if options.random_times else 0
        result.append(datetime(options.year, options.month, day, hour, minute, second))
    return result
