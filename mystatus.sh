#!/bin/sh
if ! [ -d "$XDG_DATA_HOME/mystatus/venv" ]; then
	mkdir -p "$XDG_DATA_HOME/mystatus/venv"
	python3 -m venv "$XDG_DATA_HOME/mystatus/venv"
	. "$XDG_DATA_HOME/mystatus/venv/bin/activate"
	pip3 install -r "$(dirname "$0")/requirements.txt"
else
	. "$XDG_DATA_HOME/mystatus/venv/bin/activate"
fi
ERROR_FILE="$XDG_DATA_HOME/mystatus/error.log"
python3 "$(dirname "$0")/mystatus.py" 2>"$ERROR_FILE"
