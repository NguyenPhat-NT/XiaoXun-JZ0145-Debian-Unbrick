# Hướng Dẫn Cứu Brick & Cài Debian Linux Cho USB 4G Dongle XiaoXun JZ0145_V33 (Qualcomm Snapdragon 410 / MSM8916)

Tài liệu chi tiết và toàn bộ script tự động giúp cứu sống bo mạch từ cả 2 trạng thái: **Hard-brick mất sạch Bootloader** (chỉ nhận Qualcomm 9008) lẫn **Soft-brick treo boot/Kernel panic**, sau đó cài đặt thành công **Debian GNU/Linux 11 (Bullseye) ARM64** lên USB Wi-Fi 4G Dongle **XiaoXun JZ0145_V33**.

---

## 📌 1. Thông Số Phần Cứng (Hardware Specs)

* **Model bo mạch:** XiaoXun JZ0145_V33 (`msm8916-xiaoxun-jz0145-v33`)
* **Vi xử lý (SoC):** Qualcomm Snapdragon 410 (MSM8916) - 4 nhân ARM Cortex-A53 64-bit (200 MHz - 998.4 MHz)
* **Bộ nhớ (eMCP):** SK Hynix `H9TP32A4GDBC` (chuẩn chân BGA221)
  * **RAM:** 512 MB LPDDR3 (382 MB khả dụng cho Linux OS)
  * **Bộ nhớ trong:** 4 GB eMMC 5.0 (3.3 GB cho phân vùng hệ thống rootfs)
* **Wi-Fi / Bluetooth:** Qualcomm Atheros WCN3620 / WCN3660
* **Modem di động:** Qualcomm Gobi 4G LTE (QMI interface `wwan0qmi0`)
* **Hệ điều hành đích:** Debian GNU/Linux 11 (Bullseye) aarch64, Kernel 5.15

---

## 📷 2. Sơ Đồ Bo Mạch & Nút Boot (Pinout & Hardware)

### Mặt trước bo mạch (SoC & Chân UART):
![Mặt trước bo mạch](images/board_front_bootpin.jpg)

* **Chân UART Debug:** Gồm 3 điểm tròn `TX`, `RX`, `GND` (mức logic 1.8V, baudrate 115200). Không bắt buộc dùng vì toàn bộ quá trình cứu boot đều chạy trực tiếp qua cổng USB.

### Mặt sau bo mạch (Nút bấm BOT, Khay SIM & Anten):
![Mặt sau bo mạch](images/board_back_sim_pad.jpg)

* **Nút bấm vật lý `BOT`:** Nằm ngay cạnh khay SIM, trên bo mạch có in chữ **`BOT`**. 
  > [!TIP]
  > **HOÀN TOÀN KHÔNG CẦN HÀN DÂY!** Bạn chỉ cần **nhấn giữ nút `BOT` này và cắm USB vào máy tính**, chip Snapdragon 410 sẽ lập tức vào chế độ nạp khẩn cấp **Qualcomm HS-USB QDLoader 9008**!
* **Khay SIM:** Chuẩn Micro SIM.
* **Cụm test pad SIM 2 (eSIM):** `U_DATA`, `U_CLK`, `U_RES`, `U_VREG`.
* **Đèn LED hiển thị:** 
  * LED Đỏ: **GPIO 6** (sysfs `396`)
  * LED Xanh lá: **GPIO 7** (sysfs `397`)
  * LED Xanh dương: **GPIO 8** (sysfs `398`)

---

## 📁 3. Các Tệp Cần Chuẩn Bị & Cấu Trúc Thư Mục (Firmware Setup)

Tất cả các script trong repo này đều sử dụng **đường dẫn tương đối tự động tìm kiếm** (hoặc nhận đường dẫn qua tham số `--firmware-dir`), bạn không cần sửa code. Hãy tải và đặt các file vào cấu trúc thư mục sau:

```text
XiaoXun-JZ0145-Debian-Unbrick/
├── firmware/
│   ├── base/               <-- Các file bootloader từ OpenStick base.zip
│   │   ├── gpt_main0.bin       (Bảng phân vùng Primary GPT)
│   │   ├── sbc_1.0_8016.bin    (CDT - Cấu hình RAM LPDDR3)
│   │   ├── sbl1.mbn            (Secondary Boot Loader)
│   │   ├── rpm.mbn             (Resource Power Manager)
│   │   ├── tz.mbn              (TrustZone)
│   │   ├── hyp.mbn             (Hypervisor)
│   │   ├── aboot.bin           (Little Kernel / Android Bootloader Fastboot)
│   │   └── zeros_1sector.bin   (512 bytes 0x00 để xóa header boot)
│   ├── debian/             <-- Các file hệ điều hành từ OpenStick debian.zip
│   │   ├── boot.img            (Linux Kernel 5.15 & Device Tree)
│   │   └── rootfs.img          (Debian 11 Bullseye Android Sparse Image ~920MB)
│   └── loaders/            <-- Qualcomm Firehose programmer
│       └── prog_emmc_firehose_8916.mbn (hoặc loader Cyanogen MSM8916)
├── boot_images/            <-- Các bản Boot gốc & Ép xung (Overclock + DVFS) đóng gói sẵn
│   ├── boot_stock_998mhz.img       (Boot gốc 998.4 MHz)
│   ├── boot_oc_1.09ghz.img         (Ép xung nhẹ 1.094 GHz - Áp gốc 1.15V)
│   ├── boot_oc_1.21ghz_dvfs.img    (Ép xung 1.210 GHz + Điều áp động DVFS 1.05V-1.325V)
│   ├── boot_oc_1.36ghz_dvfs.img    (Ép xung 1.363 GHz + Điều áp động DVFS 1.05V-1.362V)
│   └── boot_oc_1.40ghz_dvfs.img    (Ép xung kịch trần 1.402 GHz + DVFS 1.05V-1.375V)
├── scripts/
│   ├── unbrick_full_bootloader_edl.py  (Khôi phục toàn diện 9 mốc bootloader)
│   ├── auto_recover_and_flash.py       (Tự động cứu soft-brick & nạp Debian)
│   ├── flash_debian_checkpoints.py     (Nạp Debian Fastboot từng mốc kiểm tra)
│   ├── patch_usblib.py                 (Tự động vá lỗi Short Packet trong thư viện edl)
│   ├── setup_error_led.py              (Cấu hình đèn LED báo lỗi mạng)
│   ├── overclock_dvfs_builder.py       (Tự động build boot.img ép xung 1.402 GHz + DVFS)
│   └── clean_debian_storage.sh         (Dọn dẹp ổ cứng Debian giải phóng ~1.5 GB)
├── images/
├── OVERCLOCK_AND_OPTIMIZE.md           (Tài liệu chi tiết quy trình Ép xung 1.402 GHz & DVFS)
├── .gitignore
└── README.md
```

### 🔗 Nguồn tải Firmware & Công cụ:
1. **Thư viện EDL (Qualcomm Firehose Tool):**
   Clone từ repository của B. Kerler:
   ```cmd
   git clone https://github.com/bkerler/edl.git
   ```
2. **Gói Base & Debian của OpenStick:**
   - [OpenStick Releases](https://github.com/OpenStick/OpenStick/releases) hoặc [HandsomeOpenstick](https://github.com/HandsomeHacker/HandsomeOpenstick/releases).
   - Tải `base.zip` giải nén vào `firmware/base/`.
   - Tải `debian.zip` giải nén vào `firmware/debian/`.
3. **Firehose Loader:**
   - Tải file `prog_emmc_firehose_8916.mbn` (hoặc lấy từ thư mục `edl/Loaders/cyanogen/`).
4. **Thư viện phụ thuộc Python:**
   ```cmd
   pip install pyusb paramiko
   ```
   *(Đảm bảo file `libusb-1.0.dll` có trong `firmware/` hoặc thư mục Windows của edl)*.

---

## ⚠️ 4. Ba "Cạm Bẫy" Kỹ Thuật Lớn & Cách Khắc Phục (Root Cause Analysis)

### Bẫy 1: Lỗi Gói Ngắn (Short Packet Bug) trong thư viện Firehose Python (`usblib.py`)
* **Hiện tượng:** Khi nạp GPT hoặc SBL1 trong chế độ EDL 9008 trên Windows, loader Firehose nạp được vài chục KB thì báo lỗi Win32 `ERROR_GEN_FAILURE (code 31)` hoặc mất phản hồi ACK.
* **Nguyên nhân:** Loader Firehose của Qualcomm luôn gửi một gói tin phản hồi ngắn `<response value="ACK" rawmode="true" />` (~120 bytes) trước khi truyền dữ liệu thô. Trong hàm `usblib.py`, code chỉ chấp nhận gói tin có kích thước tròn 512 bytes (`wMaxPacketSize`). Khi nhận gói ngắn 120 bytes, hàm cố đọc tiếp lần 2 làm tràn bộ đệm USB của Windows và vứt bỏ mất gói ACK.
* **Khắc phục:** Chạy script vá tự động đi kèm trong repo:
  ```cmd
  python scripts/patch_usblib.py
  ```
  Script sẽ sửa điều kiện nhận gói ngắn (`len(chunk) < wMaxPacketSize`) và bảo toàn dữ liệu partial ACK khi gặp timeout exception.

### Bẫy 2: `fastboot.exe` không nhận diện thiết bị trên Windows
* **Hiện tượng:** Cắm dongle vào Windows nhận `VID_18D1&PID_D00D` (Android Bootloader), nhưng chạy `fastboot.exe devices` thì không hiện thiết bị nào.
* **Nguyên nhân:** Trình điều khiển WinUSB cài qua Zadig tự sinh ngẫu nhiên `DeviceInterfaceGUID`, trong khi `fastboot.exe` của Google chỉ tìm đúng GUID `{F72548D4-95D9-40BA-AB10-E20782679291}`.
* **Khắc phục:** Sử dụng script `flash_debian_checkpoints.py` nạp trực tiếp qua `pyusb` và thư viện `libusb-1.0.dll`. Giao thức Fastboot là chuẩn USB Bulk Transfer thông thường (Endpoint OUT `0x01`, IN `0x81`), kết nối trực tiếp theo VID/PID mà không phụ thuộc vào GUID Windows.

### Bẫy 3: Treo khi nạp `rootfs.img` qua Fastboot USB
* **Hiện tượng:** Nạp `boot.img` (13MB) thành công rất nhanh, nhưng khi nạp `rootfs.img` chia nhỏ (180MB) thì bị timeout ngay sau 0.6MB.
* **Nguyên nhân:** File Android Sparse Image chứa các header nhỏ (28 bytes header, 12 bytes chunk). Nếu truyền từng mẩu nhỏ này trực tiếp qua USB, mỗi mẩu nhỏ là một gói tin ngắn (< 512 bytes), khiến chip USB hiểu nhầm là đã kết thúc truyền và tạm dừng (stall).
* **Khắc phục:** Sử dụng bộ đệm (Stream Buffer) gom dữ liệu thành các khối chẵn đúng **1 MB** (`2048 * 512 bytes`). Toàn bộ quá trình truyền 100% dùng gói đầy đủ 512 bytes, chỉ gói cuối cùng mới kết thúc truyền.

---

## 🚀 5. Quy Trình Cứu Boot & Cài Đặt (Step-by-Step)

Tùy vào tình trạng thiết bị của bạn, chọn 1 trong 2 trường hợp sau:

---

### TRƯỜNG HỢP A: Hard-Brick (Mất bootloader hoàn toàn / eMMC trắng / Chỉ nhận 9008)

Nếu bo mạch của bạn bị mất sạch partition table, bị xóa eMMC, hoặc nạp nhầm rom dẫn đến mất hoàn toàn Little Kernel Fastboot:

1. **Vào EDL 9008:** Nhấn giữ nút **`BOT`** (cạnh khay SIM) và cắm USB vào máy tính. Máy nhận cổng `Qualcomm HS-USB QDLoader 9008`.
2. **Khôi phục 9 mốc Bootloader:**
   ```cmd
   python scripts/unbrick_full_bootloader_edl.py
   ```
   Script sẽ tự động nạp tuần tự 8 phân vùng cốt lõi với kiểm tra hardware ACK:
   - Mốc 1: `Primary GPT` (`gpt_main0.bin`) $\rightarrow$ Sector 0 (34 sectors)
   - Mốc 2: `CDT` (`sbc_1.0_8016.bin`) $\rightarrow$ Sector 131072 (1 sector)
   - Mốc 3: `SBL1` (`sbl1.mbn`) $\rightarrow$ Sector 262144 (1024 sectors)
   - Mốc 4: `RPM` (`rpm.mbn`) $\rightarrow$ Sector 263168 (1024 sectors)
   - Mốc 5: `TZ` (`tz.mbn`) $\rightarrow$ Sector 264192 (1183 sectors)
   - Mốc 6: `HYP` (`hyp.mbn`) $\rightarrow$ Sector 266240 (24 sectors)
   - Mốc 7: `ABOOT` (`aboot.bin`) $\rightarrow$ Sector 524288 (562 sectors)
   - Mốc 8: `Clear Boot Sector` (`zeros_1sector.bin`) $\rightarrow$ Sector 526336 (1 sector)
   - Mốc 9: Gửi lệnh `Set Bootable Storage Drive 0` và `reset`.
3. Khi chip khởi động lại, thấy phân vùng `boot` trống, Little Kernel sẽ tự động chuyển sang chế độ **Google Fastboot mode (`18D1:D00D`)**.
4. Chuyển sang bước nạp Debian (xem Bước 2 bên dưới).

---

### TRƯỜNG HỢP B: Soft-Brick (Treo Kernel Panic / Bootloop / Cài mới Debian)

Nếu bo mạch đã có sẵn Little Kernel nhưng bị treo khi nạp dở, hoặc bạn muốn cài mới hoàn toàn:

1. Nhấn giữ nút **`BOT`** và cắm USB vào máy tính.
2. Chạy script tự động toàn diện:
   ```cmd
   python scripts/auto_recover_and_flash.py
   ```
3. Script sẽ tự động:
   - Xóa sector đầu phân vùng `boot` để ép Little Kernel vào Fastboot mode.
   - Nhận diện thiết bị Fastboot `LK1ST_MSM8916`.
   - Cắt `rootfs.img` thành 5 phần (< 180MB) và nạp toàn bộ vào eMMC bằng bộ đệm 1MB.
   - Nạp Linux Kernel `boot.img`.
   - Gửi lệnh `reboot` để khởi động thẳng vào Debian Linux!

---

## ⚙️ 6. Các Tinh Chỉnh & Cấu Hình Sau Cài Đặt (Post-Install)

Sau khi dongle khởi động thành công, bạn có thể kết nối ngay qua ADB:
```cmd
adb shell
```

### 1. Sửa lỗi kết nối Wi-Fi WPA2/WPA3 (SAE Error)
Nếu router Wi-Fi của bạn dùng chế độ bảo mật kép WPA2/WPA3 (SAE Transition), lệnh `nmcli dev wifi connect` thông thường sẽ báo lỗi `(7) Secrets were required, but not provided`. Cách sửa:
```bash
nmcli con add type wifi con-name "Ten_Wifi" ifname wlan0 ssid "Ten_Wifi" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "Mat_Khau_Wifi"
nmcli con up "Ten_Wifi"
```
Dongle sẽ kết nối Wi-Fi thành công và nhận địa chỉ IP nội bộ (ví dụ: `192.168.1.165`).

### 2. Kích hoạt SSH & Đổi mật khẩu
Mở quyền đăng nhập root qua SSH:
```bash
sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
systemctl restart ssh
```
Mật khẩu mặc định:
* Tài khoản: `root` | Mật khẩu: `1`
* Tài khoản: `user` | Mật khẩu: `1`

Bây giờ bạn có thể rút dongle cắm vào củ sạc ở bất cứ đâu trong nhà và SSH điều khiển qua Wi-Fi:
```bash
ssh root@192.168.1.165
```

### 3. Tăng bộ nhớ ảo Swap lên 1.2 GB (Chống tràn RAM OOM)
Dongle có 512 MB RAM vật lý. Để cài các ứng dụng nặng (Docker, Python, Node.js...) mà không bị văng:
```bash
fallocate -l 1G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=1024
chmod 600 /swapfile
mkswap /swapfile
swapon -p 10 /swapfile
echo '/swapfile none swap sw,pri=10 0 0' >> /etc/fstab
```
Hệ thống sẽ có tổng cộng **~1.6 GB bộ nhớ ảo** (191MB ZRAM nén siêu tốc ưu tiên 100 + 1024MB eMMC swapfile ưu tiên 10).

### 4. Đèn LED chế độ cảnh báo lỗi mạng (Stealth Mode)
Để đèn không sáng chói mắt vào ban đêm, cấu hình chế độ chỉ bật đèn ĐỎ khi mất kết nối Internet/4G:
* **Nguyên lý kiểm tra:** Script giám sát liên tục ping DNS Internet (`8.8.8.8` hoặc `1.1.1.1`). Không dùng ping router vì nếu router còn bật nhưng đứt mạng Internet/4G thì vẫn phải cảnh báo lỗi.
* **Tự khởi động cùng hệ thống:** Dịch vụ được gán `systemctl enable jz0145-leds.service` để luôn tự chạy sau khi khởi động lại.
* Chạy cấu hình qua script:
  ```cmd
  python scripts/setup_error_led.py
  ```

---

## 🔥 7. Ép Xung CPU Lên 1.402 GHz (+40.4%) Kèm Điều Áp Động (Hardware DVFS) & Dọn Ổ Cứng

Mặc định bản ROM OpenStick giới hạn xung nhịp CPU ở **$998.4\text{ MHz}$** và dùng mức điện áp cố định **$1.150\text{V}$** (`regulator-dummy`). Chúng ta có thể mở khóa toàn bộ 10 nấc tần số của bộ khóa pha `a53pll` lên tới **$1,401.6\text{ MHz}$ ($1.402\text{ GHz}$)** kết hợp kích hoạt mạch điều áp động phần cứng **PM8916 Buck `S2` (`vdd-apc`, $1.050\text{V} \leftrightarrow 1.375\text{V}$)** trực tiếp trong Device Tree (`.dtb`).

👉 **Xem tài liệu phân tích kỹ thuật và hướng dẫn chi tiết tại:** [**OVERCLOCK_AND_OPTIMIZE.md**](OVERCLOCK_AND_OPTIMIZE.md)

### Nạp nhanh bản Boot Ép Xung $1.402\text{ GHz}$ + DVFS (Lưu vĩnh viễn trong eMMC):
- **Qua ADB (khi máy đang chạy bình thường):**
  ```powershell
  adb push boot_images/boot_oc_1.40ghz_dvfs.img /tmp/boot_ov.img
  adb shell "dd if=/tmp/boot_ov.img of=/dev/mmcblk0p12 bs=4096 conv=fsync"
  adb reboot
  ```
- **Hoặc qua chế độ EDL 9008:**
  ```powershell
  py -3 edl/edl.py w boot boot_images/boot_oc_1.40ghz_dvfs.img
  py -3 edl/edl.py reset
  ```
- **Tự build file `boot.img` ép xung bằng script Python:**
  ```powershell
  pip install fdt
  py -3 scripts/overclock_dvfs_builder.py -i boot_images/boot_stock_998mhz.img -o boot_oc_1.40ghz_dvfs.img -p 1.40ghz
  ```

### Dọn dẹp ổ cứng Debian (Giải phóng ~1.5 GB bộ nhớ trống):
```powershell
adb push scripts/clean_debian_storage.sh /tmp/clean_debian_storage.sh
adb shell "bash /tmp/clean_debian_storage.sh"
```

---

## 📄 License & Credits
* Dựa trên dự án mã nguồn mở **OpenStick** và **HandsomeOpenstick**.
* Tài liệu và script tổng hợp, tối ưu bởi **NguyenPhat-NT**.
