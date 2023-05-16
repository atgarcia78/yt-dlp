#!/usr/bin/env sh
exec "${PYTHON:-python3}" -Wmodule -Xdev "$(dirname "$(realpath "$0")")/yt_dlp/__main__.py" "$@"
