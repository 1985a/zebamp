#!/bin/sh
# Launcher for Zebamp (Winamp-style MPD client)
ZEBAMP_HOME="${ZEBAMP_HOME:-$HOME/proyectos/zebamp}"
export PYTHONPATH="$ZEBAMP_HOME${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m zebamp "$@"
