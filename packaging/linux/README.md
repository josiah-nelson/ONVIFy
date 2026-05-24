# Linux Packaging

## systemd Service

```bash
# Install
sudo cp packaging/linux/onvify.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable onvify
sudo systemctl start onvify

# Check status
sudo systemctl status onvify
sudo journalctl -u onvify -f
```

## Docker

```bash
docker compose up -d
```
