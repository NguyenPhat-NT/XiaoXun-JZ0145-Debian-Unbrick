import os
import sys
import time
import struct
import usb.core
import usb.util
import usb.backend.libusb1 as libusb1

LIBUSB_PATH = r"C:\hoc\edl\edlclient\Windows\libusb-1.0.dll"
BOOT_IMG = r"C:\hoc\debian\debian\boot.img"
ROOTFS_IMG = r"C:\hoc\debian\debian\rootfs.img"
MAX_PART_BYTES = 180 * 1024 * 1024  # 180 MB per chunk

class FastbootDevice:
    def __init__(self, timeout_sec=300):
        backend = libusb1.get_backend(find_library=lambda x: LIBUSB_PATH)
        if not backend:
            raise RuntimeError(f"Khong the load libusb DLL tu: {LIBUSB_PATH}")
        
        t0 = time.time()
        self.dev = None
        while time.time() - t0 < timeout_sec:
            dev = usb.core.find(idVendor=0x18D1, idProduct=0xD00D, backend=backend)
            if dev:
                try:
                    dev.set_configuration()
                    cfg = dev.get_active_configuration()
                    intf = cfg[(0, 0)]
                    ep_out = usb.util.find_descriptor(
                        intf,
                        custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
                    )
                    ep_in = usb.util.find_descriptor(
                        intf,
                        custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
                    )
                    if ep_out and ep_in:
                        # Test sending a command
                        ep_out.write(b'getvar:version', timeout=1000)
                        resp = bytes(ep_in.read(512, timeout=1000)).decode('latin1', errors='replace')
                        if resp.startswith('OKAY'):
                            self.dev = dev
                            self.ep_out = ep_out
                            self.ep_in = ep_in
                            break
                except Exception:
                    pass
            time.sleep(0.5)
            sys.stdout.write(".")
            sys.stdout.flush()
        print()

        if not self.dev:
            raise RuntimeError("Het thoi gian cho thiet bi Fastboot (VID=0x18D1, PID=0xD00D)!")

    def send_cmd(self, cmd_str, timeout=10000):
        self.ep_out.write(cmd_str.encode('ascii'), timeout=timeout)
        resp = bytes(self.ep_in.read(512, timeout=timeout)).decode('latin1', errors='replace')
        return resp

    def download_data(self, data_size, stream_generator, timeout=120000):
        cmd = f"download:{data_size:08x}"
        resp = self.send_cmd(cmd)
        if not resp.startswith("DATA"):
            raise RuntimeError(f"Lenh download bi tu choi: {resp}")
        
        expected_size = int(resp[4:12], 16)
        if expected_size != data_size:
            raise RuntimeError(f"Kich thuoc yeu cau khong khop: cho {data_size}, thiet bi bao {expected_size}")

        sent_total = 0
        t0 = time.time()
        for chunk in stream_generator:
            self.ep_out.write(chunk, timeout=timeout)
            sent_total += len(chunk)
            pct = (sent_total / data_size) * 100
            dt = max(0.001, time.time() - t0)
            speed = (sent_total / dt) / (1024 * 1024)
            sys.stdout.write(f"\r    -> Dang truyen: {sent_total / (1024*1024):.1f}/{data_size / (1024*1024):.1f} MB ({pct:.1f}%) - Toc do: {speed:.2f} MB/s ")
            sys.stdout.flush()
        print()

        resp_finish = bytes(self.ep_in.read(512, timeout=timeout)).decode('latin1', errors='replace')
        if not resp_finish.startswith("OKAY"):
            raise RuntimeError(f"Loi truyen download buffer: {resp_finish}")
        return True

    def flash_partition(self, partition_name, timeout=180000):
        cmd = f"flash:{partition_name}"
        print(f"    -> Dang ghi du lieu vao partition '{partition_name}' tren eMMC chip (cho ACK)...")
        t0 = time.time()
        self.ep_out.write(cmd.encode('ascii'), timeout=10000)
        resp = bytes(self.ep_in.read(512, timeout=timeout)).decode('latin1', errors='replace')
        dt = time.time() - t0
        if not resp.startswith("OKAY"):
            raise RuntimeError(f"Ghi partition '{partition_name}' THAT BAI: {resp}")
        print(f"    [ACK THANH CONG]: Da ghi xong partition '{partition_name}' trong {dt:.2f}s! Response: {resp.strip()}")
        return True

    def reboot(self):
        print("    -> Gui lenh reboot khoi dong lai dongle vao Debian Linux...")
        try:
            self.send_cmd("reboot", timeout=5000)
        except Exception:
            pass  # Device disconnects immediately upon reset

def plan_sparse_chunks(filename, max_part_bytes=MAX_PART_BYTES):
    with open(filename, 'rb') as f:
        hdr = f.read(28)
        magic, maj, minv, fhdr_sz, chdr_sz, blk_sz, tot_blks, tot_chunks, crc = struct.unpack('<I4H4I', hdr)
        if magic != 0xED26FF3A:
            raise ValueError(f"Khong phai Android Sparse Image (magic={hex(magic)})")

        parts = []
        current_part_chunks = []
        current_part_bytes = 28
        current_part_start_blk = 0
        current_out_blk = 0

        for i in range(tot_chunks):
            pos = f.tell()
            chdr = f.read(12)
            c_type, res, c_sz, t_sz = struct.unpack('<2H2I', chdr)
            data_sz = t_sz - 12
            f.seek(data_sz, 1)

            needed_bytes = t_sz
            if current_part_start_blk > 0 and len(current_part_chunks) == 0:
                needed_bytes += 12

            if current_part_bytes + needed_bytes > max_part_bytes and len(current_part_chunks) > 0:
                parts.append({
                    'start_blk': current_part_start_blk,
                    'end_blk': current_out_blk,
                    'num_chunks': len(current_part_chunks),
                    'total_size': current_part_bytes,
                    'chunks': current_part_chunks
                })
                current_part_start_blk = current_out_blk
                current_part_chunks = []
                current_part_bytes = 28 + 12

            current_part_chunks.append((pos, c_type, c_sz, t_sz))
            current_part_bytes += t_sz
            current_out_blk += c_sz

        if len(current_part_chunks) > 0:
            parts.append({
                'start_blk': current_part_start_blk,
                'end_blk': current_out_blk,
                'num_chunks': len(current_part_chunks),
                'total_size': current_part_bytes,
                'chunks': current_part_chunks
            })

        return blk_sz, tot_blks, parts

def generate_part_stream(filename, part_info, blk_sz, chunk_buffer_sz=1048576):
    start_blk = part_info['start_blk']
    end_blk = part_info['end_blk']
    chunks = part_info['chunks']
    
    # 1. Sparse header (28 bytes)
    num_total_chunks = (1 if start_blk > 0 else 0) + len(chunks)
    sparse_hdr = struct.pack(
        '<I4H4I',
        0xED26FF3A, # magic
        1,          # major_version
        0,          # minor_version
        28,         # file_hdr_sz
        12,         # chunk_hdr_sz
        blk_sz,     # blk_sz
        end_blk,    # total_blks (cumulative blocks covered by this split)
        num_total_chunks,
        0           # crc
    )

    def raw_stream():
        yield sparse_hdr
        if start_blk > 0:
            dont_care_hdr = struct.pack(
                '<2H2I',
                0xCAC3,     # CHUNK_TYPE_DONT_CARE
                0,          # reserved
                start_blk,  # chunk_sz in blocks
                12          # total_sz (header only)
            )
            yield dont_care_hdr

        with open(filename, 'rb') as f:
            for file_pos, c_type, c_sz, t_sz in chunks:
                f.seek(file_pos)
                bytes_left = t_sz
                while bytes_left > 0:
                    to_read = min(chunk_buffer_sz, bytes_left)
                    buf = f.read(to_read)
                    if not buf:
                        break
                    bytes_left -= len(buf)
                    yield buf

    # Buffer everything into chunk_buffer_sz (1MB = 2048 * 512 bytes)
    # This prevents short packets (< 512 bytes) from prematurely ending USB bulk transfers!
    buf = bytearray()
    for item in raw_stream():
        buf.extend(item)
        while len(buf) >= chunk_buffer_sz:
            yield bytes(buf[:chunk_buffer_sz])
            del buf[:chunk_buffer_sz]
    if len(buf) > 0:
        yield bytes(buf)

def generate_file_stream(filename):
    with open(filename, 'rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            yield chunk

def main():
    print("=" * 65)
    print("   MSM8916 DEBIAN FLASH - HE THONG MOC KIEM TRA AN TOAN (CHECKPOINTS)")
    print("=" * 65)

    # -----------------------------------------------------------------
    # MOC 1: Kiem tra ket noi thiet bi Fastboot & Query bien Little Kernel
    # -----------------------------------------------------------------
    print("\n[MOC 1/5] Kiem tra ket noi Fastboot va handshake Little Kernel...")
    try:
        fb = FastbootDevice()
        ver = fb.send_cmd("getvar:version")
        prod = fb.send_cmd("getvar:product")
        max_dl = fb.send_cmd("getvar:max-download-size")
        part_boot = fb.send_cmd("getvar:partition-size:boot")
        part_rootfs = fb.send_cmd("getvar:partition-size:rootfs")
        print(f"    -> Product: {prod.strip()}")
        print(f"    -> Fastboot Version: {ver.strip()}")
        print(f"    -> Max Download Size: {max_dl.strip()}")
        print(f"    -> Boot Partition Size: {part_boot.strip()}")
        print(f"    -> Rootfs Partition Size: {part_rootfs.strip()}")
        if not prod.startswith("OKAY") or not part_boot.startswith("OKAY"):
            print("[-] MOC 1 THAT BAI: Thiet bi khong phan hoi dung Fastboot protocol. DUNG LAI!")
            sys.exit(1)
        print("[+] MOC 1 THANH CONG: Handshake Fastboot Little Kernel hoan hao!")
    except Exception as e:
        print(f"[-] MOC 1 THAT BAI: {e}. DUNG LAI NGAY!")
        sys.exit(1)

    # -----------------------------------------------------------------
    # MOC 2: Nap Kernel Debian Linux (boot.img) vao partition 'boot'
    # -----------------------------------------------------------------
    print("\n[MOC 2/5] Nap Linux Kernel (boot.img) vao partition 'boot'...")
    try:
        if not os.path.exists(BOOT_IMG):
            raise FileNotFoundError(f"Khong tim thay file {BOOT_IMG}")
        boot_sz = os.path.getsize(BOOT_IMG)
        with open(BOOT_IMG, 'rb') as f:
            if f.read(8) != b'ANDROID!':
                raise ValueError("boot.img khong dung dinh dang Android Boot Image header")
        print(f"    -> File boot.img: {boot_sz / (1024*1024):.2f} MB (Header Android Boot hop le)")
        
        # Download
        fb.download_data(boot_sz, generate_file_stream(BOOT_IMG))
        # Flash
        fb.flash_partition("boot")
        print("[+] MOC 2 THANH CONG: Da nap Kernel Debian Linux vao partition 'boot'!")
    except Exception as e:
        print(f"[-] MOC 2 THAT BAI: {e}. DUNG LAI NGAY!")
        sys.exit(1)

    # -----------------------------------------------------------------
    # MOC 3: Phan tich va lap ke hoach chia Sparse Image cho rootfs.img
    # -----------------------------------------------------------------
    print("\n[MOC 3/5] Phan tich Android Sparse Image va lap ke hoach chia nho rootfs...")
    try:
        if not os.path.exists(ROOTFS_IMG):
            raise FileNotFoundError(f"Khong tim thay file {ROOTFS_IMG}")
        blk_sz, tot_blks, parts = plan_sparse_chunks(ROOTFS_IMG, MAX_PART_BYTES)
        print(f"    -> File rootfs.img hop le: {tot_blks} blocks ({tot_blks * blk_sz / (1024*1024):.1f} MB uncompressed)")
        print(f"    -> Ke hoach chia: {len(parts)} phan (tat ca deu < 180MB, an toan tuyet doi)")
        for idx, p in enumerate(parts):
            print(f"       + Phan {idx+1}/{len(parts)}: Blocks {p['start_blk']} -> {p['end_blk']} ({p['total_size'] / (1024*1024):.2f} MB)")
        print("[+] MOC 3 THANH CONG: Ke hoach nap rootfs sparse da san sang!")
    except Exception as e:
        print(f"[-] MOC 3 THAT BAI: {e}. DUNG LAI NGAY!")
        sys.exit(1)

    # -----------------------------------------------------------------
    # MOC 4: Nap lan luot tung phan cua rootfs.img vao partition 'rootfs'
    # -----------------------------------------------------------------
    print("\n[MOC 4/5] Tien hanh nap 5 phan Debian Root Filesystem (rootfs)...")
    for idx, p in enumerate(parts):
        part_num = idx + 1
        print(f"\n  --- [MOC 4.{part_num}/5] Nap rootfs Phan {part_num}/{len(parts)} ({p['total_size'] / (1024*1024):.2f} MB) ---")
        try:
            stream = generate_part_stream(ROOTFS_IMG, p, blk_sz)
            fb.download_data(p['total_size'], stream)
            fb.flash_partition("rootfs")
            print(f"  [+] MOC 4.{part_num} THANH CONG: Phan {part_num}/{len(parts)} da duoc ghi an toan vao eMMC!")
        except Exception as e:
            print(f"\n[-] MOC 4.{part_num} THAT BAI: {e}. DUNG LAI NGAY DE BAO VE DU LIEU!")
            sys.exit(1)

    print("\n[+] MOC 4 HOAN TAT XUAT SAC: Toan bo Debian Root Filesystem (rootfs) da nap xong 100%!")

    # -----------------------------------------------------------------
    # MOC 5: Khoi dong lai thiet bi vao Debian Linux
    # -----------------------------------------------------------------
    print("\n[MOC 5/5] Khoi dong lai dongle vao he dieu hanh Debian Linux...")
    try:
        fb.reboot()
        print("[+] MOC 5 THANH CONG: Lenh reboot da duoc gui. Thiet bi dang khoi dong Debian Linux!")
    except Exception as e:
        print(f"[*] Thong bao reboot: {e}")

    print("\n" + "=" * 65)
    print("   QUA TRINH NAP DEBIAN LINUX HOAN TAT 100% THANH CONG!")
    print("=" * 65)

if __name__ == "__main__":
    main()
