#!/usr/bin/env bash

set -eux

rm -rf README_files
jupyter nbconvert --to markdown README.ipynb
python make_md.py
