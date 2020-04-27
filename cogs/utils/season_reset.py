import calendar
from datetime import datetime
import pytz

def next_season_start():
    def get_season_start_for(month, year):
        (weekday_of_first_day, days_in_month) = calendar.monthrange(year, month)
        season_start_day = days_in_month - datetime(year=year, month=month,
                                                    day=days_in_month, tzinfo=pytz.utc).weekday()
        return datetime(year=year, month=month, day=season_start_day, hour=5, minute=0, second=0, microsecond=0,
                        tzinfo=pytz.utc)

    # Start date is the last Monday of the month. That's when SC resets the season values
    now = datetime.now(pytz.utc)
    start_date = get_season_start_for(now.month, now.year)
    if now > start_date:
        # time is in past
        next_month = 1 if now.month == 12 else now.month + 1
        year = now.year + 1 if now.month == 12 else now.year
        start_date = get_season_start_for(next_month, year)

    return start_date
