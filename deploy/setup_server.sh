#!/bin/bash
# ==============================================================================
# Script de Despliegue Automático — File Server ICFD (Ubuntu / Debian)
# Configura: Systemd + Nginx (Puerto 80) + Avahi mDNS (.local) + LLMNR + Dnsmasq
# ==============================================================================
set -e

APP_DIR="${APP_DIR:-/opt/python-file-server}"
SERVER_IP=$(hostname -I | awk '{print $1}')

echo "==> [1/5] Instalando paquetes del sistema (Nginx, Avahi, Dnsmasq)..."
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx avahi-daemon avahi-utils dnsmasq

echo "==> [2/5] Configurando servicio Systemd (python-file-server.service)..."
sudo tee /etc/systemd/system/python-file-server.service > /dev/null <<EOF
[Unit]
Description=ICFD Python Modern File Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/python3 ${APP_DIR}/server.py --host 0.0.0.0 --port 8000 --storage ${APP_DIR}/storage
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now python-file-server.service

echo "==> [3/5] Configurando Proxy Inverso Nginx en puerto 80..."
sudo tee /etc/nginx/sites-available/fileserver.icfd.cl > /dev/null <<'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name fileserver.local fileserver-icfd.local fileserver.icfd.cl fileserver-icfd _;

    client_max_body_size 0;
    proxy_request_buffering off;
    proxy_buffering off;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Range $http_range;
        proxy_set_header If-Range $http_if_range;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
EOF

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/fileserver.icfd.cl /etc/nginx/sites-enabled/fileserver.icfd.cl
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx

echo "==> [4/5] Configurando Avahi (mDNS: fileserver.local / fileserver-icfd.local) y LLMNR..."
sudo hostnamectl set-hostname fileserver
sudo sed -i "s/^#*host-name=.*/host-name=fileserver/" /etc/avahi/avahi-daemon.conf
sudo sed -i "s/^#*enable-dbus=.*/enable-dbus=yes/" /etc/avahi/avahi-daemon.conf
sudo sed -i "s/^#*use-ipv4=.*/use-ipv4=yes/" /etc/avahi/avahi-daemon.conf
sudo sed -i "s/^#*publish-addresses=.*/publish-addresses=yes/" /etc/avahi/avahi-daemon.conf
sudo sed -i "s/^#*publish-workstation=.*/publish-workstation=yes/" /etc/avahi/avahi-daemon.conf

sudo tee /usr/local/bin/publish-fileserver-mdns.sh > /dev/null <<'EOF'
#!/bin/bash
IP=$(hostname -I | cut -d" " -f1)
exec /usr/bin/avahi-publish -a -R fileserver-icfd.local "$IP"
EOF
sudo chmod +x /usr/local/bin/publish-fileserver-mdns.sh

sudo tee /etc/systemd/system/avahi-alias-fileserver.service > /dev/null <<'EOF'
[Unit]
Description=Publish fileserver-icfd.local mDNS alias
After=network-online.target avahi-daemon.service
Wants=network-online.target
Requires=avahi-daemon.service

[Service]
Type=simple
ExecStart=/usr/local/bin/publish-fileserver-mdns.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo mkdir -p /etc/systemd/resolved.conf.d
sudo tee /etc/systemd/resolved.conf.d/llmnr.conf > /dev/null <<'EOF'
[Resolve]
LLMNR=yes
MulticastDNS=no
EOF

sudo systemctl daemon-reload
sudo systemctl restart systemd-resolved
sudo systemctl enable --now avahi-daemon
sudo systemctl restart avahi-daemon
sudo systemctl enable --now avahi-alias-fileserver.service
sudo systemctl restart avahi-alias-fileserver.service

echo "==> [5/5] Configurando DNS local (dnsmasq) para fileserver.icfd.cl..."
if [ -n "$SERVER_IP" ]; then
    sudo tee /etc/dnsmasq.d/icfd.conf > /dev/null <<EOF
listen-address=${SERVER_IP}
bind-interfaces
no-resolv
all-servers
server=1.1.1.1
server=8.8.8.8
address=/fileserver.icfd.cl/${SERVER_IP}
address=/fileserver.local/${SERVER_IP}
address=/fileserver-icfd.local/${SERVER_IP}
cache-size=2000
EOF
    sudo systemctl enable dnsmasq
    sudo systemctl restart dnsmasq
fi

echo "=============================================================================="
echo " ¡Despliegue completado!"
echo " - Acceso Plug & Play (mDNS): http://fileserver.local"
echo " - Acceso alternativo mDNS  : http://fileserver-icfd.local"
echo " - Acceso por DNS interno   : http://fileserver.icfd.cl"
echo " - Acceso por IP directa    : http://${SERVER_IP}"
echo "=============================================================================="
