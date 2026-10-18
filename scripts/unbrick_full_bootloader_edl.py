#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full Hard-Brick Recovery Script for Qualcomm MSM8916 (XiaoXun JZ0145_V33)
Restores all 9 essential bootloader stages to eMMC via Qualcomm EDL 9008 mode.
"""
import os
import sys
import time
import argparse

# Dynamic path resolution
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)

DEFAULT_SEARCH_PATHS = [
    os.path.join(REPO_DIR, "firmware", "base"),
    os.path.join(REPO_DIR, "firmware"),
    r"C:\hoc\base\base",
    r"C:\hoc",
    os.getcwd()
]

LOADER_SEARCH_PATHS = [
    os.path.join(REPO_DIR, "firmware", "loaders"),
    os.path.join(REPO_DIR, "firmware"),
    r"C:\hoc\edl\Loaders\cyanogen",
    r"C:\hoc\edl\Loaders",
    r"C:\hoc",
    os.getcwd()
]

def find_file(filename, search_paths):
    for p in search_paths:
        candidate = os.path.join(p, filename)
        if os.path.exists(candidate):
            return candidate
    return None

def find_edl_library():
    candidates = [
        os.path.join(REPO_DIR, "edl"),
        r"C:\hoc\edl",
        os.path.join(os.path.expanduser("~"), "edl")
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "edl.py")) or os.path.exists(os.path.join(c, "edlclient")):
            return c
    return None

def main():
    parser = argparse.ArgumentParser(description="Khôi phục toàn bộ Bootloader cho MSM8916 qua Qualcomm EDL 9008")
    parser.add_argument("--firmware-dir", help="Thư mục chứa các file bootloader (gpt_main0.bin, sbl1.mbn, aboot.bin, ...)")
    parser.add_argument("--loader", help="Đường dẫn file Firehose programmer (prog_emmc_firehose_8916.mbn hoặc fhprg.bin)")
    parser.add_argument("--edl-dir", help="Đường dẫn thư mục edl (bkerler/edl)")
    args_cli = parser.parse_args()

    # 1. Setup EDL path
    edl_path = args_cli.edl_dir or find_edl_library()
    if not edl_path:
        print("[-] KHONG TIM THAY THU VIEN EDL! Vui long chi dinh --edl-dir hoac clone git bkerler/edl")
        sys.exit(1)
    sys.path.insert(0, edl_path)
    from edl import main as edl_main, args as edl_args

    # 2. Find loader
    search_loaders = [args_cli.loader] if args_cli.loader else []
    search_loaders.extend(LOADER_SEARCH_PATHS)
    loader_file = None
    for l_name in ["007050e100000000_4e3eefa63a67eb7a_fhprg_peek.bin", "prog_emmc_firehose_8916.mbn", "prog_emmc_firehose_8916_lite.mbn"]:
        loader_file = find_file(l_name, search_loaders)
        if loader_file:
            break
    if not loader_file and args_cli.loader and os.path.exists(args_cli.loader):
        loader_file = args_cli.loader
    if not loader_file:
        print("[-] KHONG TIM THAY FIREHOSE LOADER! Vui long chi dinh --loader <path/to/loader.mbn>")
        sys.exit(1)

    # 3. Find bootloader binaries
    search_fw = [args_cli.firmware_dir] if args_cli.firmware_dir else []
    search_fw.extend(DEFAULT_SEARCH_PATHS)

    BOOTLOADER_STAGES = [
        # (Stage name, start_sector, filename)
        ("1. Primary GPT", 0, "gpt_main0.bin"),
        ("2. CDT", 131072, "sbc_1.0_8016.bin"),
        ("3. SBL1", 262144, "sbl1.mbn"),
        ("4. RPM", 263168, "rpm.mbn"),
        ("5. TZ", 264192, "tz.mbn"),
        ("6. HYP", 266240, "hyp.mbn"),
        ("7. ABOOT (Little Kernel)", 524288, "aboot.bin"),
        ("8. Clear Boot Sector", 526336, "zeros_1sector.bin"),
    ]

    resolved_stages = []
    for stage_name, sector, fname in BOOTLOADER_STAGES:
        fpath = find_file(fname, search_fw)
        if not fpath:
            # Special case for zeros_1sector: create if not exists
            if fname == "zeros_1sector.bin":
                fpath = os.path.join(SCRIPT_DIR, "zeros_1sector.bin")
                with open(fpath, "wb") as fz:
                    fz.write(b'\x00' * 512)
            else:
                print(f"[-] Thieu file {fname} cho moc {stage_name}! Vui long kiem tra lai thu muc firmware.")
                sys.exit(1)
        resolved_stages.append((stage_name, sector, fpath))

    print("=" * 65)
    print("   MSM8916 HARD-BRICK: KHOI PHUC TRON VEN 9 MOC BOOTLOADER (EDL 9008)")
    print("=" * 65)
    print(f"[*] Loader su dung: {loader_file}")
    print("[*] Vui long nhan giu nut BOT (canh khay SIM) va cam USB vao may tinh...")

    m = edl_main(edl_args, imported='')
    m.args["--loader"] = loader_file
    m.args["--memory"] = "eMMC"

    ret = m.run()
    if not m.fh or not m.fh.connected:
        print("[-] Khong the ket noi Firehose loader EDL! Kiem tra lai nut BOT va driver 9008.")
        sys.exit(1)

    fh = m.fh.firehose
    print("[+] Ket noi Firehose thanh cong! Bat dau nap 8 phan vung bootloader:")

    for stage_name, sector, fpath in resolved_stages:
        sz = os.path.getsize(fpath)
        print(f"\n  >> [{stage_name}] Dang ghi vao sector {sector} ({sz} bytes)...")
        t0 = time.time()
        success = fh.cmd_program(0, sector, fpath)
        dt = time.time() - t0
        if not success:
            print(f"[-] {stage_name} THAT BAI! Dung lai ngay de kiem tra!")
            sys.exit(1)
        print(f"  [+] {stage_name} thanh cong trong {dt:.2f}s!")

    print("\n  >> [9. Set Bootable Storage Drive 0]...")
    try:
        fh.cmd_setbootablestoragedrive(0)
        print("  [+] Da set Bootable Storage Drive 0 thanh cong!")
    except Exception as e:
        print(f"  [*] Setbootablestoragedrive: {e}")

    print("\n[+] HOAN TAT KHOI PHUC 9 MOC BOOTLOADER!")
    print("[*] Dang gui lenh reset. Thiet bi se tu dong khoi dong vao Google Fastboot mode (18D1:D00D)...")
    fh.cmd_reset("reset")
    print("[+] DONE! Bay gio ban co the chay tiep script nạp Debian qua Fastboot!")

if __name__ == "__main__":
    main()
