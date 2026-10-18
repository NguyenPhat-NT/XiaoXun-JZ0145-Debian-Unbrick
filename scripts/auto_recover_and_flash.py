import os
import sys
import time
import struct
import usb.core
import usb.util
import usb.backend.libusb1 as libusb1

sys.path.insert(0, r"c:\hoc\edl")
from edl import main as edl_main, args as edl_args

LIBUSB_PATH = r"C:\hoc\edl\edlclient\Windows\libusb-1.0.dll"
LOADER_PATH = r"C:\hoc\edl\Loaders\cyanogen\007050e100000000_4e3eefa63a67eb7a_fhprg_peek.bin"
ZEROS_FILE = r"C:\hoc\base\base\zeros_1sector.bin"
BOOT_IMG = r"C:\hoc\debian\debian\boot.img"
ROOTFS_IMG = r"C:\hoc\debian\debian\rootfs.img"
MAX_PART_BYTES = 180 * 1024 * 1024

class FastbootDevice:
    def __init__(self, timeout_sec=120):
        backend = libusb1.get_backend(find_library=lambda x: LIBUSB_PATH)
        if not backend:
            raise RuntimeError(f"Khong the load libusb DLL: {LIBUSB_PATH}")
        
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
        print(f"    -> Dang ghi vao partition '{partition_name}' tren eMMC chip (cho ACK)...")
        t0 = time.time()
        self.ep_out.write(cmd.encode('ascii'), timeout=10000)
        resp = bytes(self.ep_in.read(512, timeout=timeout)).decode('latin1', errors='replace')
        dt = time.time() - t0
        if not resp.startswith("OKAY"):
            raise RuntimeError(f"Ghi partition '{partition_name}' THAT BAI: {resp}")
        print(f"    [ACK THANH CONG]: Da ghi xong '{partition_name}' trong {dt:.2f}s! Response: {resp.strip()}")
        return True

    def reboot(self):
        print("    -> Gui lenh reboot dongle vao Debian Linux...")
        try:
            self.send_cmd("reboot", timeout=5000)
        except Exception:
            pass

def plan_sparse_chunks(filename, max_part_bytes=MAX_PART_BYTES):
    with open(filename, 'rb') as f:
        hdr = f.read(28)
        magic, maj, minv, fhdr_sz, chdr_sz, blk_sz, tot_blks, tot_chunks, crc = struct.unpack('<I4H4I', hdr)
        assert magic == 0xED26FF3A

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

    num_total_chunks = (1 if start_blk > 0 else 0) + len(chunks)
    sparse_hdr = struct.pack(
        '<I4H4I',
        0xED26FF3A, 1, 0, 28, 12, blk_sz, end_blk, num_total_chunks, 0
    )

    def raw_stream():
        yield sparse_hdr
        if start_blk > 0:
            dont_care_hdr = struct.pack('<2H2I', 0xCAC3, 0, start_blk, 12)
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

def step_edl_fix():
    print("=" * 65)
    print("   GIAI DOAN 1: KET NOI QUALCOMM EDL 9008 VA RESET BOOT PARTITION")
    print("=" * 65)
    print("[*] Dang cho thiet bi o che do EDL 9008 (cham diem boot vao GND khi cam USB)...")

    m = edl_main(edl_args, imported='')
    m.args["--loader"] = LOADER_PATH
    m.args["--memory"] = "eMMC"

    ret = m.run()
    if not m.fh or not m.fh.connected:
        print("[-] Khong the ket noi Firehose loader EDL!")
        return False

    fh = m.fh.firehose
    print("[+] Firehose ket noi thanh cong! Dang clear sector 526336 (boot partition)...")
    fh.cmd_program(0, 526336, ZEROS_FILE)
    print("[+] Da clear boot sector thanh cong! Gui lenh reset de Little Kernel vao Fastboot...")
    fh.cmd_reset("reset")
    time.sleep(2)
    return True

def step_fastboot_flash():
    print("\n" + "=" * 65)
    print("   GIAI DOAN 2: NAP TOAN DIEN DEBIAN LINUX TRONG FASTBOOT MODE")
    print("=" * 65)
    print("[*] Dang cho thiet bi chuyen sang che do Google Fastboot...")
    fb = FastbootDevice(timeout_sec=60)
    print(f"[+] Little Kernel Fastboot connected: {fb.send_cmd('getvar:product').strip()}")

    # 1. Flash rootfs FIRST
    print("\n--- [Buoc 1/2] Nap toan bo 5 phan Debian Root Filesystem (rootfs) ---")
    blk_sz, tot_blks, parts = plan_sparse_chunks(ROOTFS_IMG, MAX_PART_BYTES)
    for idx, p in enumerate(parts):
        part_num = idx + 1
        print(f"\n  >> Nap rootfs Phan {part_num}/{len(parts)} ({p['total_size'] / (1024*1024):.2f} MB)...")
        stream = generate_part_stream(ROOTFS_IMG, p, blk_sz)
        fb.download_data(p['total_size'], stream)
        fb.flash_partition("rootfs")
        print(f"  [+] Phan {part_num}/{len(parts)} da nap THANH CONG vao eMMC!")

    print("\n[+] TOAN BO ROOTFS DEBIAN DA DUOC NAP 100% THANH CONG!")

    # 2. Flash boot.img SECOND
    print("\n--- [Buoc 2/2] Nap Linux Kernel (boot.img) vao partition 'boot' ---")
    boot_sz = os.path.getsize(BOOT_IMG)
    fb.download_data(boot_sz, generate_file_stream(BOOT_IMG))
    fb.flash_partition("boot")
    print("[+] DA NAP KERNEL DEBIAN VAO PARTITION 'BOOT' THANH CONG!")

    # 3. Reboot into Debian
    print("\n--- Khoi dong lai vao Debian Linux ---")
    fb.reboot()
    print("\n[*** HOAN TAT XUAT SAC ***] Thiet bi dang khoi dong vao Debian Linux!")
    return True

def main():
    # If device is already in Fastboot, skip EDL
    backend = libusb1.get_backend(find_library=lambda x: LIBUSB_PATH)
    dev_fb = usb.core.find(idVendor=0x18D1, idProduct=0xD00D, backend=backend) if backend else None

    if dev_fb:
        print("[+] Thiet bi da o Fastboot mode! Tien hanh nap truc tiep...")
        step_fastboot_flash()
    else:
        # Step 1: EDL fix
        if step_edl_fix():
            # Step 2: Fastboot flash
            step_fastboot_flash()
        else:
            print("[-] Giai doan EDL that bai. Vui long kiem tra lai diem boot!")

if __name__ == "__main__":
    main()
