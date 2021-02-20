#!/bin/sh
cd "$(dirname "$0")"
. ./venv/bin/activate
ERROR_FILE="$XDG_DATA_HOME/mystatus/error.log"
python3 "$(dirname "$0")/mystatus.py" 2>"$ERROR_FILE"
