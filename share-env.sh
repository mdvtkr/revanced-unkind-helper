#!/bin/sh

poetry config virtualenvs.in-project true --local
poetry config virtualenvs.create true --local
poetry config virtualenvs.path ~/.venv --local

VENV_NAME=atwstw
SHARED_VENV=$HOME/.venv/$VENV_NAME

PYTHON=python3
PYTHON_VERSION=`$PYTHON --version | awk '{print $2}' | cut -d. -f1,2`
if [ $PYTHON_VERSION != "3.11" ]; then
  PYTHON=python3.11
  PYTHON_VERSION=`$PYTHON --version | awk '{print $2}' | cut -d. -f1,2`
  if [ $PYTHON_VERSION != "3.11" ]; then
    echo 'Python 3.11 is required. Abort...'
    exit 1
  fi
fi

if [ -d "./.venv" ]; then
  if [ -h './.venv' ]; then
     echo 'symbolic link to shared venv exists'
  else
    echo 'delete current venv'
    rm -rf ./.venv
  fi
fi

if [ -d "$SHARED_VENV" ]; then
  echo 'shared venv exists.'
  ln -s $SHARED_VENV .venv 
else
  echo 'create new venv.'
  #poetry update
  python3 -m venv --prompt $VENV_NAME $SHARED_VENV
  ln -s $SHARED_VENV .venv 
  ln -s ~/.venv/atwstw .venv 
  poetry update
fi
