#!/bin/bash
# Script dọn dẹp triệt để bộ nhớ eMMC trên OpenStick Debian 11 (giải phóng ~1.5 GB)
# Giữ nguyên 100% các dịch vụ mạng, Wi-Fi, 4G ModemManager, NetworkManager, SSH, ADB, Python3, iptables.

set -e

echo "=== [1/4] Dọn dẹp nhật ký hệ thống (systemd-journald & /var/log) ==="
journalctl --vacuum-size=5M || true
sed -i 's/#SystemMaxUse=/SystemMaxUse=10M/' /etc/systemd/journald.conf || true
rm -f /var/log/*.1 /var/log/*.gz /var/log/*.old
truncate -s 0 /var/log/syslog /var/log/messages /var/log/daemon.log /var/log/kern.log /var/log/auth.log /var/log/user.log /var/log/debug 2>/dev/null || true

echo "=== [2/4] Xóa file tạm và các bản backup firmware/kernel thừa ==="
rm -rf /root/Geekbench* /root/*.tar.gz /root/__pycache__ /root/.cache /tmp/*.img /tmp/*.pl
rm -rf /usr/lib/firmware.bak /usr/lib/firmware.227 /usr/lib/firmware/backup_openstick_fw
rm -rf /boot/*5.14-sdm845* /usr/lib/modules/*5.14-sdm845* /usr/src/linux-headers*
dpkg --purge linux-image-5.14-sdm845 2>/dev/null || true

echo "=== [3/4] Gỡ bỏ các gói đồ họa/đa phương tiện nặng không dùng trên USB 4G ==="
export DEBIAN_FRONTEND=noninteractive
apt-get purge -y \
    mpv gmediarender cmake cmake-data tshark wireshark-common libwireshark14 \
    wifite reaver aircrack-ng hcxdumptool hcxtools \
    libgl1-mesa-dri libllvm11 libflite1 \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-base gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav gstreamer1.0-alsa \
    linux-headers-5.15.0-handsomekernel+ 2>/dev/null || true

apt-get autoremove -y --purge
apt-get clean
rm -rf /var/lib/apt/lists/*
sync

echo "=== [4/4] Hoàn tất! Dung lượng ổ cứng hiện tại: ==="
df -h /
du -xhd 1 / 2>/dev/null | sort -hr
