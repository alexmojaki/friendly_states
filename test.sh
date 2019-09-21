#!/usr/bin/env bash

set -eu

. ./venv/bin/activate

set -x

pytest
python transitions_example.py
jupyter nbconvert --execute README.ipynb
rm README.html
