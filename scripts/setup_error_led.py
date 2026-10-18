import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.1.165', port=22, username='root', password='1', timeout=5)

cmd = """
cat << 'EOF' > /usr/local/bin/led_monitor.sh
#!/bin/bash
# XiaoXun JZ0145 LED Error Indicator
# Red = 396 (TLMM 6), Green = 397 (TLMM 7), Blue = 398 (TLMM 8)

for g in 396 397 398; do
    if [ ! -d "/sys/class/gpio/gpio$g" ]; then
        echo $g > /sys/class/gpio/export 2>/dev/null
    fi
    echo out > /sys/class/gpio/gpio$g/direction 2>/dev/null
done

# Turn off Green and Blue permanently (Stealth mode)
echo 0 > /sys/class/gpio/gpio397/value
echo 0 > /sys/class/gpio/gpio398/value

while true; do
    # Kiem tra ket noi Internet thuc te (ping Google DNS 8.8.8.8 hoac Cloudflare 1.1.1.1)
    # Neu mat 4G / mat Internet (du router van bat) -> BAT DEN DO
    if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1 || ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1; then
        # Internet binh thuong: TAT HET DEN
        echo 0 > /sys/class/gpio/gpio396/value
    else
        # Mat ket noi Internet: BAT DEN DO CANH BAO
        echo 1 > /sys/class/gpio/gpio396/value
    fi
    sleep 10
done
EOF

chmod +x /usr/local/bin/led_monitor.sh

cat << 'EOF' > /etc/systemd/system/jz0145-leds.service
[Unit]
Description=XiaoXun JZ0145 LED Error Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/led_monitor.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable jz0145-leds.service
systemctl restart jz0145-leds.service
echo -n "Enabled: "; systemctl is-enabled jz0145-leds.service
echo -n "Active: "; systemctl is-active jz0145-leds.service
"""

stdin, stdout, stderr = ssh.exec_command(cmd)
print(stdout.read().decode('ascii', errors='ignore'))
ssh.close()
