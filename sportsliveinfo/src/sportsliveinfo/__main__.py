import logging
import os
import threading
from pathlib import Path
from .engine import Engine
from .server import serve
from .storage import Store


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    os.umask(0o077)
    base = Path(os.environ.get("SLI_DATA_DIR", "/data"))
    base.mkdir(parents=True, exist_ok=True)
    store = Store(base / "sportsliveinfo.sqlite3")
    engine = Engine(store)
    threading.Thread(target=engine.run_scheduler, name="sportsliveinfo-scheduler", daemon=True).start()
    serve(store, engine)


if __name__ == "__main__":
    main()
