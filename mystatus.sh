if ! [ -d "$XDG_DATA_HOME/mystatus/venv" ]; then
	mkdir -p "$XDG_DATA_HOME/mystatus/venv"
	python3 -m venv "$XDG_DATA_HOME/mystatus/venv"
	source "$XDG_DATA_HOME/mystatus/venv/bin/activate"
	pip3 install -r "$(dirname "$0")/requirements.txt"
else
	source "$XDG_DATA_HOME/mystatus/venv/bin/activate"
fi
python3 "$(dirname "$0")/mystatus.py"
