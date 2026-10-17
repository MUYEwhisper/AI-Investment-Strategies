from __future__ import annotations

import os
import sys

from flask import Flask
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(__file__))
from pages.local_chat import local_chat_page  # noqa: E402

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.register_blueprint(local_chat_page)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("LOCAL_MODEL_PORT", "8001")), threaded=True)
