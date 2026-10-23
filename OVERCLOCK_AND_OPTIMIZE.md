# Hướng Dẫn Ép Xung CPU Lên 1.402 GHz (+40.4%) Kèm Điều Áp Động (Hardware DVFS) & Tối Ưu Bộ Nhớ Cho USB 4G MSM8916 (OpenStick Debian)

Tài liệu kỹ thuật chi tiết và hướng dẫn thực hành từng bước để mở khóa xung nhịp vi xử lý **Qualcomm Snapdragon 410 / 412 (MSM8916)** từ mức mặc định **$998.4\text{ MHz}$** lên kịch trần phần cứng **$1,401.6\text{ MHz}$ ($1.402\text{ GHz}$, $+40.4\%$)** kết hợp **Điều áp động phần cứng (Hardware DVFS `vdd-apc`)** và dọn dẹp tối ưu bộ nhớ eMMC.

---

## 📌 1. Tổng Quan & Nguyên Lý Kỹ Thuật

### 1.1. Giới hạn gốc trên ROM OpenStick Debian ($998.4\text{ MHz}$)
Trên SoC **Qualcomm MSM8916**, xung nhịp của 4 nhân ARM Cortex-A53 được cấp bởi bộ khóa pha **APCS A53 PLL (`a53pll@b016000`)**, nhân từ thạch anh chuẩn $19.2\text{ MHz}$ (`xo_board`) theo hệ số nhân `L`.

Khi giải nén `Image.gz` trong phân vùng `boot` (`/dev/mmcblk0p12`) và dịch ngược trình điều khiển `drivers/clk/qcom/a53-pll.c` (tại địa chỉ `0x9f0470`), bảng tần số phần cứng `pll_freq_tbl` trong kernel thực chất đã hỗ trợ sẵn **7 mức PLL cao**:
- `998,400,000 Hz` (`L = 0x34 = 52`) — *Mức trần mặc định của ROM gốc*
- `1,094,400,000 Hz` (`L = 0x39 = 57`)
- `1,152,000,000 Hz` (`L = 0x3e = 62`)
- `1,209,600,000 Hz` (`L = 0x3f = 63`)
- `1,248,000,000 Hz` (`L = 0x41 = 65`)
- `1,363,200,000 Hz` (`L = 0x47 = 71`)
- **`1,401,600,000 Hz` (`L = 0x49 = 73` — Mức kịch trần tuyệt đối trong driver `a53pll`)**

Tuy nhiên, trong **Device Tree Blob (`.dtb`)** gắn ở cuối kernel gốc, bảng `/cpu-opp-table` chỉ khai báo 4 mức (`200`, `400`, `800`, `998.4 MHz`), làm cho trình điều khiển `cpufreq-dt` bị khóa ở $998.4\text{ MHz}$.

### 1.2. Tại sao một số bo mạch bị sập nguồn (Brownout) nếu chỉ mở khóa tần số?
Trong `.dtb` gốc của OpenStick, đường cấp nguồn cho nhân CPU chưa được khai báo nên Linux sử dụng bộ điều áp giả (`regulator-dummy`). Khi đó, điện áp nhân CPU bị giữ cố định ở mức do bootloader cài đặt từ lúc bật nguồn:
- Thanh ghi phần cứng **PM8916 Buck `S2` (`0x1741` trên bus SPMI `0-01`) = `0x3e` ($1.150\text{V}$)**.
- Những chip trúng lô bán dẫn tốt ("Silicon Lottery" như bo mạch `165`) có thể chạy tới $1.363\text{ GHz}$ ở $1.150\text{V}$.
- Nhưng những chip có ngưỡng điện áp tiêu chuẩn (như bo mạch `227`) chỉ chịu được tối đa $1.094\text{ GHz} \sim 1.152\text{ GHz}$ ở $1.150\text{V}$. Khi nhảy lên $\ge 1.210\text{ GHz}$ mà không nâng áp, nhân CPU sẽ bị thiếu áp (brownout) và treo ngay lúc khởi động.

### 1.3. Giải pháp triệt để: Kích hoạt Điều áp động phần cứng (Hardware DVFS)
Trong nhân `5.15.0-handsomekernel+`, trình điều khiển **`qcom-spmi-regulator`** (`drivers/regulator/qcom_spmi-regulator.c`) đã được biên dịch sẵn, hỗ trợ điều khiển trực tiếp mạch Buck **`S2` (`VDD_APC` tại địa chỉ SPMI `0x1700`, kiểu `ULT_LO_SMPS` `0x22/0x0d`)** qua thanh ghi `0x1741`:
$$V_{\text{CPU}} = 375\text{ mV} + (\text{Giá trị thanh ghi }\mathtt{0x1741}) \times 12.5\text{ mV}$$

Bằng cách can thiệp trực tiếp vào Kernel (`Image.gz`) và Device Tree (`.dtb`) trong `boot.img` thông qua script [`scripts/overclock_dvfs_builder.py`](scripts/overclock_dvfs_builder.py), chúng ta thực hiện **4 thay đổi cốt lõi**:
1. **Cô lập duy nhất mạch nguồn `s2` (`0x1700` = `vdd-apc`) trong bảng `spmi_pm8916_regulators` của `Image.gz`:**
   - Trong `qcom_spmi-regulator.c`, bảng `spmi_pm8916_regulators` mặc định chứa cả 22 mạch nguồn (`s1..s4`, `l1..l18`). Nếu đăng ký toàn bộ trên bus SPMI, sau 30 giây khởi động hàm `regulator_late_cleanup` của nhân Linux sẽ tắt các LDO không có consumer trên nhánh SPMI (như `l9`/`l5`/`l7` vốn đang cấp nguồn cho chip Wi-Fi WCN3620 bên nhánh RPM).
   - Script tự động sửa điểm relocation `0xdd6880` trỏ thẳng vào phần tử `s2` (`0xffff800010a031a0`) và đặt sentinel kết thúc mảng ngay sau `s2` (`0xdd8bf0` / `0xa031c8`), giúp driver SPMI chỉ đăng ký duy nhất **`vdd-apc` (`s2`)** mà không đụng chạm tới bất kỳ nguồn Wi-Fi/Modem nào của RPM.
2. **Khai báo mạch nguồn `s2` (`vdd-apc`) dưới `/soc/spmi@200f000/pmic@1`:**
   ```dts
   regulators {
       compatible = "qcom,pm8916-regulators";
       s2 {
           regulator-name = "vdd-apc";
           regulator-min-microvolt = <1050000>; /* 1.050V */
           regulator-max-microvolt = <1375000>; /* 1.375V */
           regulator-always-on;
           phandle = <0x9A>;
       };
   };
   ```
3. **Gắn `cpu-supply = <0x9A>;` vào `/cpus/cpu@0`:** Để `cpufreq-dt` tự động nâng điện áp trước khi tăng xung và hạ điện áp sau khi giảm xung.
4. **Thiết lập bảng 10 nấc Xung nhịp & Điện áp (`opp-hz` & `opp-microvolt`) trong `/cpu-opp-table`:**

| Nấc | Tần số (`opp-hz`) | Điện áp (`opp-microvolt`) | Thanh ghi `0x1741` | Ghi chú |
| :-: | :---: | :---: | :---: | :--- |
| 1 | `200.0 MHz` | **$1.0500\text{ V}$** | `0x36` | Hạ áp khi nghỉ (mát hơn gốc) |
| 2 | `400.0 MHz` | **$1.0500\text{ V}$** | `0x36` | Hạ áp khi tải nhẹ |
| 3 | `800.0 MHz` | **$1.1500\text{ V}$** | `0x3e` | Mức áp mặc định của bootloader |
| 4 | `998.4 MHz` | **$1.1500\text{ V}$** | `0x3e` | Xung tối đa mặc định của ROM gốc |
| 5 | `1,094.4 MHz` | **$1.2250\text{ V}$** | `0x44` | Ép xung nấc 1 ($+9.6\%$) |
| 6 | `1,152.0 MHz` | **$1.2750\text{ V}$** | `0x48` | Ép xung nấc 2 ($+15.4\%$) |
| 7 | `1,209.6 MHz` | **$1.3125\text{ V}$** | `0x4b` | Ép xung nấc 3 ($+21.2\%$) |
| 8 | `1,248.0 MHz` | **$1.3250\text{ V}$** | `0x4c` | Ép xung nấc 4 ($+25.0\%$) |
| 9 | `1,363.2 MHz` | **$1.3625\text{ V}$** | `0x4f` | Ép xung nấc 5 ($+36.5\%$) |
| 10 | **`1,401.6 MHz`** | **$1.3750\text{ V}$** | `0x50` | **Đỉnh phần cứng `a53pll` ($+40.4\%$)** |

---

## 📦 2. Danh Sách Các Bản Boot Đã Đóng Gói Sẵn (`boot_images/`)

Trong thư mục [`boot_images/`](boot_images/) của repo đã lưu sẵn 5 file `.img` chuẩn (kích thước `13,588,480` bytes) để bạn có thể nạp ngay lập tức trên bất kỳ máy tính nào mà không cần build lại:

| Tên file trong `boot_images/` | Mức xung tối đa | Điều áp động (DVFS) | Mã kiểm tra SHA256 |
| :--- | :---: | :---: | :--- |
| [`boot_oc_1.40ghz_dvfs.img`](boot_images/boot_oc_1.40ghz_dvfs.img) | **$1.402\text{ GHz}$ (+40.4%)** | Có (`1.05V – 1.375V`) | `9D75B983E2797BD7409C11E658618B7845244E1F6F17A58AB17CE80953EF77E9` |
| [`boot_oc_1.36ghz_dvfs.img`](boot_images/boot_oc_1.36ghz_dvfs.img) | **$1.363\text{ GHz}$ (+36.5%)** | Có (`1.05V – 1.362V`) | `79A19634AAC30C5138FA2A6E8A5B3A45E2A06EBB410E50B93EB0478A22A62AC6` |
| [`boot_oc_1.21ghz_dvfs.img`](boot_images/boot_oc_1.21ghz_dvfs.img) | **$1.210\text{ GHz}$ (+21.2%)** | Có (`1.05V – 1.325V`) | `30E97236E3A88D259327266B8DE522EA7EAE0AEB929C1E7AB692F13DEAC969D6` |
| [`boot_oc_1.09ghz.img`](boot_images/boot_oc_1.09ghz.img) | **$1.094\text{ GHz}$ (+9.6%)** | Không (Áp gốc `1.15V`) | `1B150747307F6A09A02ACB28621FF241ACDBB8790DE1DE45B780A66007B204BC` |
| [`boot_stock_998mhz.img`](boot_images/boot_stock_998mhz.img) | **$998.4\text{ MHz}$ (Gốc)** | Không (Áp gốc `1.15V`) | `6C961CF9694594FA3F57A27970B3D552F6903C89471938350C118BE05FA2621D` |

---

## 🚀 3. Hướng Dẫn Thực Hiện Ép Xung (Step-by-Step)

### Bước 0: Bật chế độ USB Gadget (ADB) nếu cổng USB đang ở chế độ Host
Nếu que 4G của bạn đang tắt cổng USB (chế độ `host` để chống chạm nguồn 5V), hãy vào SSH qua Wi-Fi và chuyển về chế độ `gadget` để cắm vào máy tính nhận ADB:
```bash
ssh root@<IP_CUA_QUE_4G>
systemctl disable --now usb-host.service 2>/dev/null || true
echo gadget > /sys/kernel/debug/ci_hdrc.0/role
```

### Cách 1: Nạp trực tiếp qua ADB (Khi máy đang hoạt động bình thường — Chỉ mất 10 giây)
1. **Sao lưu phân vùng `boot` hiện tại về máy tính (Chốt an toàn):**
   ```powershell
   adb shell "dd if=/dev/mmcblk0p12 bs=4096 count=3318 2>/dev/null" > boot_backup.img
   ```
2. **Đẩy bản Boot $1.402\text{ GHz}$ DVFS lên thiết bị và ghi vào phân vùng `/dev/mmcblk0p12`:**
   ```powershell
   adb push boot_images/boot_oc_1.40ghz_dvfs.img /tmp/boot_ov.img
   adb shell "dd if=/tmp/boot_ov.img of=/dev/mmcblk0p12 bs=4096 conv=fsync; head -c 13590528 /dev/mmcblk0p12 | sha256sum"
   ```
   *(Kiểm tra mã SHA256 in ra khớp với `9d75b983e2797bd7409c11e658618b7845244e1f6f17a58ab17ce80953ef77e9`)*.
3. **Khởi động lại thiết bị:**
   ```powershell
   adb reboot
   ```

### Cách 2: Nạp qua chế độ EDL 9008 (Dùng khi máy không lên ADB hoặc muốn khôi phục nhanh)
1. Nhấn giữ nút **`BOT`** trên mạch và cắm USB vào máy tính để vào chế độ **Qualcomm HS-USB QDLoader 9008 (`05C6:9008`)**.
2. Chạy lệnh nạp phân vùng `boot` bằng công cụ `edl`:
   ```powershell
   py -3 edl/edl.py w boot boot_images/boot_oc_1.40ghz_dvfs.img
   py -3 edl/edl.py reset
   ```
   *(Nếu sau lệnh `reset` máy chưa tự nhận USB, hãy rút que 4G ra và cắm lại).*

### Cách 3: Tự tạo bản Boot tùy chỉnh từ `boot.img` gốc bằng Script Python
Nếu sau này bạn muốn tự build lại từ file `boot.img` gốc hoặc đổi thông số điện áp:
```powershell
pip install fdt
py -3 scripts/overclock_dvfs_builder.py -i boot_images/boot_stock_998mhz.img -o my_boot_1.40ghz.img -p 1.40ghz
```

---

## 🔍 4. Lệnh Kiểm Chứng Sau Khi Ép Xung

Sau khi máy khởi động lại, chạy lệnh sau qua ADB hoặc SSH để kiểm tra:
```bash
mount -t debugfs none /sys/kernel/debug 2>/dev/null || true

# 1. Xem danh sách 10 nấc tần số và tần số tối đa hiện tại
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq

# 2. Thử ép tải tối đa (performance) và kiểm tra xung PLL + Điện áp PMIC S2
echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
grep a53 /sys/kernel/debug/clk/clk_summary
grep '^1741:' /sys/kernel/debug/regmap/0-01/registers
grep -A 1 'vdd-apc' /sys/kernel/debug/regulator/regulator_summary

# 3. Stress test SHA256 40MB và đo nhiệt độ
dd if=/dev/zero bs=1M count=40 2>/dev/null | sha256sum
cat /sys/class/thermal/thermal_zone*/temp

# 4. Trả về chế độ điều tốc thông minh (schedutil)
echo schedutil > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
```

**Kết quả chuẩn khi chạy ở $1.402\text{ GHz}$:**
```text
200000 400000 800000 998400 1094400 1152000 1209600 1248000 1363200 1401600
1401600
       a53pll@b016000     1  2  0  1401600000  0  0  50000  ?
          a53mux@b011000  1  1  0  1401600000  0  0  50000  Y
1741: 50
    vdd-apc               2  1  0  normal  1375mV  0mA  1050mV  1375mV
       cpu0-cpu           1                        0mA  1375mV  1375mV
```

---

## 🧹 5. Dọn Dẹp & Tối Ưu Bộ Nhớ eMMC (Giải Phóng ~1.5 GB)

Bản ROM Debian 11 gốc của OpenStick cài sẵn nhiều thư viện đồ họa/âm thanh/pentest không cần thiết và không giới hạn dung lượng log `journald`, làm ổ cứng 3.3 GB nhanh chóng bị đầy.

Để dọn sạch tự động (giảm dung lượng đã dùng từ `2.3 GB (75%)` xuống chỉ còn **`~780 MB (25%)`**, trống **`2.3 GB`**), chạy script đi kèm:
```powershell
adb push scripts/clean_debian_storage.sh /tmp/clean_debian_storage.sh
adb shell "bash /tmp/clean_debian_storage.sh"
```
Hoặc chạy trực tiếp trên SSH của thiết bị:
```bash
bash /tmp/clean_debian_storage.sh
```
