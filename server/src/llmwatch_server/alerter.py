from time import sleep, time

from sqlalchemy.orm import Session

from .alerts import check_rules
from .config import get_settings
from .db import get_engine
from .migrate import check_schema


def run() -> None:
    settings = get_settings()
    engine = get_engine()
    check_schema()
    print(f"Alerter started, checking rules every {settings.alert_interval_seconds}s")

    while True:
        with Session(engine) as session:
            sent = check_rules(session, time())
            session.commit()
        if sent:
            print(f"Alerter sent {sent} notifications")
        sleep(settings.alert_interval_seconds)


if __name__ == "__main__":
    run()
