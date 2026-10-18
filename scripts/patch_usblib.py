#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch for edlclient/Library/Connection/usblib.py to fix Qualcomm Firehose Short-Packet Bug
Author: NguyenPhat-NT
"""
import os
import sys

def patch_file(filepath):
    if not os.path.exists(filepath):
        print(f"[-] Khong tim thay file: {filepath}")
        return False

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    modified = False

    # 1. Patch short packet break condition
    old_snippet_1 = "if len(chunk) % self.EP_IN.wMaxPacketSize != 0"
    target_snippet_1 = "if len(chunk) < self.EP_IN.wMaxPacketSize or len(res) >= resplen:"
    if old_snippet_1 in content:
        content = content.replace(old_snippet_1, "if len(chunk) < self.EP_IN.wMaxPacketSize")
        modified = True
        print("[+] Da sua dieu kien short packet (< wMaxPacketSize).")

    # 2. Patch exception handling to preserve partial data
    old_snippet_2 = "error = (str(e.strerror) if hasattr(e, \"strerror\") and e.strerror else str(e)).lower()"
    preserve_code = "error = (str(e.strerror) if hasattr(e, \"strerror\") and e.strerror else str(e)).lower()\n                if len(res) > 0:\n                    break"
    if old_snippet_2 in content and "if len(res) > 0:" not in content:
        content = content.replace(old_snippet_2, preserve_code)
        modified = True
        print("[+] Da bo sung co che bao ve du lieu partial ACK khi gap timeout exception.")

    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[SUCCESS] Da patch thanh cong file: {filepath}")
        return True
    else:
        if "if len(chunk) < self.EP_IN.wMaxPacketSize" in content:
            print("[INFO] File usblib.py da duoc patch truoc do!")
            return True
        print("[-] Khong tim thay vi tri can patch hoac code da khac. Vui long kiem tra bang tay theo huong dan README.")
        return False

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if not target:
        # Search common paths
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "edl", "edlclient", "Library", "Connection", "usblib.py"),
            r"C:\hoc\edl\edlclient\Library\Connection\usblib.py",
            os.path.join(os.path.expanduser("~"), "edl", "edlclient", "Library", "Connection", "usblib.py"),
        ]
        for c in candidates:
            if os.path.exists(c):
                target = c
                break

    if not target or not os.path.exists(target):
        print("[-] Khong tu tim thay usblib.py. Vui long truyen duong dan file:")
        print("    python patch_usblib.py <path/to/usblib.py>")
        sys.exit(1)

    patch_file(target)

if __name__ == "__main__":
    main()
