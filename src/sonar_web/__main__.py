import logging
import os

import uvicorn


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # One worker is required for temporary sessions and global supplier pacing.
    uvicorn.run("sonar_web.api:create_app", factory=True, host=os.getenv("SONAR_BIND_HOST", "127.0.0.1"),
                port=int(os.getenv("SONAR_PORT", "8000")), workers=1, proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
