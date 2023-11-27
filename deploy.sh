#!/bin/bash
poetry update
poetry run pyinstaller -F src/main.py -n RvHelper
