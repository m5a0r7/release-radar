"""Write the API's OpenAPI schema, which the web client generates its types from."""

import json
import sys
from pathlib import Path

from radar.main import create_app

if __name__ == "__main__":
    target = Path(sys.argv[1])
    target.write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
