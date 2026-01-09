#!/bin/bash

# Upgrade all installed packages to the latest version
pip install --upgrade $(pip freeze | awk -F'[=]' '{print $1}')

# Freeze the updated packages to requirements.txt
pip freeze > requirements.txt