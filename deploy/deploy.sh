#!/usr/bin/env bash
# Update the server to the latest prod branch. Run from your laptop:
#   SERVER=ubuntu@<ELASTIC_IP> KEY=~/keys/immersio.pem bash deploy/deploy.sh
set -e
: "${SERVER:?set SERVER=ubuntu@<ELASTIC_IP>}"
: "${KEY:?set KEY=path/to/immersio.pem}"

ssh -i "$KEY" "$SERVER" '
  cd ~/immersio-backend &&
  git pull &&
  ~/venv/bin/pip install -q -r requirements.txt &&
  sudo systemctl restart immersio &&
  sleep 5 && systemctl is-active immersio
'
