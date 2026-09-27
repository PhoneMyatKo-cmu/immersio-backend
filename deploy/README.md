# Deploying to EC2 (demo)

Single instance: Postgres in Docker, the API as a systemd service (one uvicorn
worker), Caddy in front for HTTPS. Instance: `g4dn.xlarge` (or `t3.xlarge` while
waiting for GPU quota — change the instance type later, nothing to reinstall).
AMI: *Deep Learning Base AMI with Single CUDA (Ubuntu 24.04)*, 64-bit (x86).

## First-time setup (on the server)

Docker is preinstalled on this AMI — don't install `docker.io` (it conflicts
with the bundled `containerd.io`).

```bash
sudo apt update && sudo apt install -y ffmpeg python3.12-venv caddy
docker --version && docker compose version
sudo usermod -aG docker ubuntu          # log out and back in afterwards

git clone https://github.com/PhoneMyatKo-cmu/immersio-backend.git
cd immersio-backend && git checkout prod

python3.12 -m venv ~/venv
~/venv/bin/pip install -r requirements.txt
~/venv/bin/python -m unidic download
```

Copy the files that are not in git (from your laptop):

```bash
scp -i immersio.pem .env gct_key.json immersio.dump ubuntu@<IP>:~/immersio-backend/
scp -i immersio.pem -r utils/data ubuntu@<IP>:~/immersio-backend/utils/
scp -i immersio.pem -r temp_audios ubuntu@<IP>:~/immersio-backend/
```

In the server `.env` set `CORS_ORIGINS=https://<frontend>.vercel.app` and
`WHISPER_PRELOAD=1` (see [.env.example](../.env.example)).

### Database

```bash
docker compose up -d
docker cp immersio.dump immersio_db:/tmp/
docker exec immersio_db pg_restore -U postgres -d immersio --no-owner /tmp/immersio.dump
```

### GPU check (g4dn only)

faster-whisper needs the CUDA libraries that ship with torch:

```bash
~/venv/bin/python -c 'import os, nvidia.cublas.lib, nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ":" + os.path.dirname(nvidia.cudnn.lib.__file__))'
~/venv/bin/python -c "import torch, ctranslate2; print(torch.cuda.is_available(), ctranslate2.get_cuda_device_count())"   # expect: True 1
```

Put the first command's output into `LD_LIBRARY_PATH` in `immersio.service`.

### YouTube access (captions + audio from a server IP)

YouTube blocks datacenter IPs, so on the server yt-dlp needs:

- **Cookies** from a throwaway account (export from a private window, see the
  yt-dlp wiki) at `~/cookies.txt`, `chmod 600`, and
  `YOUTUBE_COOKIES=/home/ubuntu/cookies.txt` in `.env`.
- **Deno** (JS challenge solver), system-wide so the service can find it:
  `curl -fsSL https://deno.land/install.sh | sudo DENO_INSTALL=/usr/local sh -s -- -y`
- **A PO token provider** — without a PO token, caption downloads get HTTP 429:

```bash
docker run --name bgutil-provider -d --restart unless-stopped -p 127.0.0.1:4416:4416 brainicism/bgutil-ytdlp-pot-provider
~/venv/bin/pip install -U bgutil-ytdlp-pot-provider
```

  and `YOUTUBE_FETCH_POT=1` in `.env`.

### Service + HTTPS

```bash
sudo cp deploy/immersio.service /etc/systemd/system/     # then edit LD_LIBRARY_PATH
sudo systemctl daemon-reload && sudo systemctl enable --now immersio
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile            # then edit the hostname
sudo systemctl restart caddy
```

Check: `https://<host>/docs` loads. Logs: `journalctl -u immersio -f`.

## Updating

```bash
SERVER=ubuntu@<IP> KEY=path/to/immersio.pem bash deploy/deploy.sh
```

With `WHISPER_PRELOAD=1` the API takes ~20–60 s after a (re)start before it
answers, while it loads the model.
