from datetime import date, timedelta

def biweekly(anchor: date, start: date, end: date) -> list[date]:
    current = anchor
    while current < start: current += timedelta(days=14)
    return [current + timedelta(days=14*i) for i in range(((end-current).days // 14)+1)] if current <= end else []

def weekly(weekday: int, start: date, end: date) -> list[date]:
    current = start + timedelta(days=(weekday-start.weekday()) % 7)
    return [current + timedelta(days=7*i) for i in range(((end-current).days // 7)+1)] if current <= end else []
