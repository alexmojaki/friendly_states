#!/usr/bin/env bash

set -eux

pytest
python transitions_example.py
jupyter nbconvert --execute README.ipynb
rm README.html
