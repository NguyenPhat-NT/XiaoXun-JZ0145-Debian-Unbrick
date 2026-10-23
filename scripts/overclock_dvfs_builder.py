#!/usr/bin/env python3
"""
Công cụ tạo bản Boot ép xung (Overclock) kèm Điều áp động phần cứng (Hardware DVFS)
cho USB 4G Qualcomm MSM8916 (Snapdragon 410/412 - XiaoXun JZ0145_V33 / OpenStick Debian).

Tính năng:
1. Mở khóa mạch nguồn PM8916 Buck S2 (vdd-apc tại địa chỉ SPMI 0-01: 0x1700, thanh ghi 0x1741).
2. Liên kết cpu-supply vào /cpus/cpu@0 để kích hoạt DVFS trong trình điều khiển cpufreq-dt.
3. Mở khóa tối đa 10 nấc xung nhịp của bộ khóa pha APCS A53 PLL (a53pll@b016000) từ 200 MHz đến 1.402 GHz.

Cài đặt thư viện cần thiết:
    pip install fdt
"""

import argparse
import hashlib
import os
import struct
import fdt

# Bảng cấu hình chuẩn 10 nấc Xung nhịp (Hz) và Điện áp (microvolt)
# Công thức thanh ghi PM8916 S2 (0x1741): V_uV = 375000 + selector * 12500
FULL_OPP_TABLE = [
    (200000000,  1050000),  # 200.0 MHz @ 1.0500 V (0x36) - Hạ áp khi nghỉ giúp mát máy
    (400000000,  1050000),  # 400.0 MHz @ 1.0500 V (0x36)
    (800000000,  1150000),  # 800.0 MHz @ 1.1500 V (0x3e) - Điện áp mặc định bootloader
    (998400000,  1150000),  # 998.4 MHz @ 1.1500 V (0x3e) - Xung tối đa mặc định ROM gốc
    (1094400000, 1225000),  # 1.094 GHz @ 1.2250 V (0x44) - +9.6%
    (1152000000, 1275000),  # 1.152 GHz @ 1.2750 V (0x48) - +15.4%
    (1209600000, 1312500),  # 1.210 GHz @ 1.3125 V (0x4b) - +21.2%
    (1248000000, 1325000),  # 1.248 GHz @ 1.3250 V (0x4c) - +25.0%
    (1363200000, 1362500),  # 1.363 GHz @ 1.3625 V (0x4f) - +36.5%
    (1401600000, 1375000),  # 1.402 GHz @ 1.3750 V (0x50) - +40.4% (Kịch trần a53pll)
]

PRESETS = {
    "1.09ghz": 1094400000,
    "1.15ghz": 1152000000,
    "1.21ghz": 1209600000,
    "1.36ghz": 1363200000,
    "1.40ghz": 1401600000,
}


def build_dvfs_boot(input_boot: str, output_boot: str, max_freq: int = 1401600000, enable_dvfs: bool = True):
    with open(input_boot, "rb") as f:
        data = f.read(13588480)

    hdr = bytearray(data[:2048])
    magic, k_sz, k_addr, r_sz, r_addr, s_sz, s_addr, tags, pagesize = struct.unpack('<8s8I', hdr[:40])
    if magic != b'ANDROID!':
        raise ValueError(f"File {input_boot} không phải Android Boot Image hợp lệ!")

    k_data = data[pagesize : pagesize + k_sz]
    dtb_idx = k_data.find(b'\xd0\x0d\xfe\xed')
    if dtb_idx == -1:
        raise ValueError("Không tìm thấy Device Tree Blob (DTB) trong kernel!")

    image_gz = k_data[:dtb_idx]
    orig_dtb = k_data[dtb_idx:]
    dt = fdt.parse_dtb(orig_dtb)

    if enable_dvfs:
        # 1. Khai báo mạch nguồn PM8916 Buck S2 (vdd-apc) dưới /soc/spmi@200f000/pmic@1
        pmic1 = dt.get_node('/soc/spmi@200f000/pmic@1')
        if not any(n.name == 'regulators' for n in pmic1.nodes):
            reg_node = fdt.Node('regulators')
            reg_node.append(fdt.PropStrings('compatible', 'qcom,pm8916-regulators'))

            s2_node = fdt.Node('s2')
            s2_node.append(fdt.PropStrings('regulator-name', 'vdd-apc'))
            s2_node.append(fdt.PropWords('regulator-min-microvolt', 1050000))
            s2_node.append(fdt.PropWords('regulator-max-microvolt', 1375000))
            s2_node.append(fdt.Property('regulator-always-on'))
            s2_node.append(fdt.PropWords('phandle', 0x9A))
            reg_node.append(s2_node)
            pmic1.append(reg_node)

        # 2. Liên kết cpu-supply = <0x9A> vào /cpus/cpu@0
        cpu0 = dt.get_node('/cpus/cpu@0')
        if not any(p.name == 'cpu-supply' for p in cpu0.props):
            cpu0.append(fdt.PropWords('cpu-supply', 0x9A))

    # 3. Cập nhật bảng /cpu-opp-table
    opp = dt.get_node('/cpu-opp-table')
    existing = {n.name: n for n in opp.nodes}

    selected_opps = [(f, v) for (f, v) in FULL_OPP_TABLE if f <= max_freq]
    for freq, uV in selected_opps:
        name = f"opp-{freq}"
        if name in existing:
            node = existing[name]
            if enable_dvfs and not any(p.name == 'opp-microvolt' for p in node.props):
                node.append(fdt.PropWords('opp-microvolt', uV))
        else:
            node = fdt.Node(name)
            node.append(fdt.PropWords('opp-hz', 0, freq))
            if enable_dvfs:
                node.append(fdt.PropWords('opp-microvolt', uV))
            opp.append(node)

    new_dtb = dt.to_dtb()
    new_kernel = image_gz + new_dtb
    new_k_sz = len(new_kernel)
    hdr[8:12] = struct.pack('<I', new_k_sz)

    def pad(d, sz):
        rem = len(d) % sz
        return d + b'\x00' * (sz - rem) if rem != 0 else d

    orig_k_pages = (k_sz + pagesize - 1) // pagesize
    r_offset = (1 + orig_k_pages) * pagesize
    ramdisk = data[r_offset : r_offset + r_sz]

    out_bytes = hdr + pad(new_kernel, pagesize) + pad(ramdisk, pagesize)
    with open(output_boot, "wb") as f:
        f.write(out_bytes)

    sha256 = hashlib.sha256(out_bytes).hexdigest()
    print(f"[+] Đã tạo thành công: {output_boot}")
    print(f"    - Dung lượng : {len(out_bytes)} bytes")
    print(f"    - Xung tối đa: {max_freq / 1e9:.3f} GHz (DVFS={'BẬT' if enable_dvfs else 'TẮT'})")
    print(f"    - SHA256     : {sha256}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Overclock + DVFS boot.img cho MSM8916 OpenStick Debian")
    parser.add_argument("-i", "--input", default="firmware/debian/boot.img", help="Đường dẫn boot.img gốc")
    parser.add_argument("-o", "--output", default="boot_oc_1.40ghz_dvfs.img", help="Đường dẫn boot.img đầu ra")
    parser.add_argument(
        "-p", "--preset",
        choices=list(PRESETS.keys()),
        default="1.40ghz",
        help="Mức xung nhịp tối đa (mặc định: 1.40ghz)"
    )
    parser.add_argument("--no-dvfs", action="store_true", help="Không thêm điều áp vdd-apc (chỉ mở khóa tần số)")
    args = parser.parse_args()

    build_dvfs_boot(args.input, args.output, PRESETS[args.preset], enable_dvfs=not args.no_dvfs)
