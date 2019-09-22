#!/usr/bin/env bash

set -eux

jupyter nbconvert --to markdown README.ipynb
python make_md.py
