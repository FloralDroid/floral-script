import gzip
import os
import shutil
import re
from stuff.general import General
from tools.helper import bcolors, download_file, host, print_color, get_download_dir

class Magisk(General):
    download_loc = get_download_dir()
    dl_link = "https://github.com/FloralDroid/Magisk/releases/download/v30.7-floral.2/Magisk-v30.7-floral.2.apk"
    dl_file_name = os.path.join(download_loc, "magisk.apk")
    act_sha256 = "45256c900d2d907ff5692347b2a4dd2c20c0e8782f32b56fb45786c51dcbd41f"
    extract_to = "/tmp/magisk_unpack"
    copy_dir = "./magisk"
    magisk_dir = os.path.join(copy_dir, "system", "etc", "init", "magisk")
    machine = host()
    oringinal_bootanim = """
service bootanim /system/bin/bootanimation
    class core animation
    user graphics
    group graphics audio
    disabled
    oneshot
    ioprio rt 0
    task_profiles MaxPerformance
    
"""
    bootanim_component = """
on post-fs-data
    start logd
    # redroid commonly disables SELinux; avoid feeding a missing policy to magiskpolicy.
    exec u:r:su:s0 root root -- /system/bin/sh -c "if [ -r /sys/fs/selinux/policy ]; then exec {MAGISKSYSTEMDIR}/magiskpolicy --live --magisk; fi"
    exec u:r:magisk:s0 root root -- /system/bin/sh -c "if [ -r /sys/fs/selinux/policy ]; then exec {MAGISKSYSTEMDIR}/magiskpolicy --live --magisk; fi"
    exec u:r:update_engine:s0 root root -- /system/bin/sh -c "if [ -r /sys/fs/selinux/policy ]; then exec {MAGISKSYSTEMDIR}/magiskpolicy --live --magisk; fi"
    # Seed DATABIN before post-fs-data; package installation happens at boot-complete.
    mkdir /data/adb 700
    mkdir /data/adb/magisk 755
    exec u:r:su:s0 root root -- /system/bin/sh -c "cp -f {MAGISKSYSTEMDIR}/busybox /data/adb/magisk/busybox && chmod 755 /data/adb/magisk/busybox; if [ -f {MAGISKSYSTEMDIR}/magiskpolicy ]; then cp -f {MAGISKSYSTEMDIR}/magiskpolicy /data/adb/magisk/magiskpolicy && chmod 755 /data/adb/magisk/magiskpolicy; fi"
    exec u:r:su:s0 root root -- {MAGISKSYSTEMDIR}/{magisk_name} --auto-selinux --setup-sbin {MAGISKSYSTEMDIR} {MAGISKTMP}
    # Inject applets into /system/bin. Android app UIDs cannot traverse Magisk's /system/xbin mount.
    exec u:r:su:s0 root root -- /system/bin/sh -c "PATH=/system/bin; export PATH; exec {MAGISKTMP}/magisk --auto-selinux --post-fs-data"
on nonencrypted
    exec u:r:su:s0 root root -- {MAGISKTMP}/magisk --auto-selinux --service
on property:vold.decrypt=trigger_restart_framework
    exec u:r:su:s0 root root -- {MAGISKTMP}/magisk --auto-selinux --service
on property:sys.boot_completed=1
    mkdir /data/adb/magisk 755
    exec u:r:su:s0 root root -- {MAGISKTMP}/magisk --auto-selinux --boot-complete
    exec -- /system/bin/sh -c "pm install -r /system/etc/init/magisk/magisk.apk >/dev/null 2>&1 || {{ pm uninstall com.topjohnwu.magisk >/dev/null 2>&1 || true; pm install /system/etc/init/magisk/magisk.apk; }}"
   
on property:init.svc.zygote=restarting
    exec u:r:su:s0 root root -- {MAGISKTMP}/magisk --auto-selinux --zygote-restart
   
on property:init.svc.zygote=stopped
    exec u:r:su:s0 root root -- {MAGISKTMP}/magisk --auto-selinux --zygote-restart
    """.format(MAGISKSYSTEMDIR="/system/etc/init/magisk", MAGISKTMP="/sbin", magisk_name="magisk")

    def download(self):
        print_color("Downloading latest Magisk now .....", bcolors.GREEN)
        super().download()   

    def copy(self):
        if os.path.exists(self.copy_dir):
            shutil.rmtree(self.copy_dir)
        if not os.path.exists(self.magisk_dir):
            os.makedirs(self.magisk_dir, exist_ok=True)

        if not os.path.exists(os.path.join(self.copy_dir, "sbin")):
            os.makedirs(os.path.join(self.copy_dir, "sbin"), exist_ok=True)

        print_color("Copying magisk libs now ...", bcolors.GREEN)
        
        arch_map = {
            "x86": "x86",
            "x86_64": "x86_64",
            "arm": "armeabi-v7a",
            "arm64": "arm64-v8a"
        }
        lib_dir = os.path.join(self.extract_to, "lib", arch_map[self.machine[0]])
        for parent, dirnames, filenames in os.walk(lib_dir):
            for filename in filenames:
                o_path = os.path.join(lib_dir, filename)  
                filename = re.search(r'lib(.*)\.so', filename)
                n_path = os.path.join(self.magisk_dir, filename.group(1))
                shutil.copyfile(o_path, n_path)
                os.chmod(n_path, 0o755)
        shutil.copyfile(self.dl_file_name, os.path.join(self.magisk_dir,"magisk.apk") )

        # The daemon trusts the certificate from the bundled stub APK. Keep it
        # beside the native binaries so --setup-sbin can place it in /sbin.
        stub_path = os.path.join(self.extract_to, "assets", "stub.apk")
        if not os.path.isfile(stub_path):
            raise FileNotFoundError(f"Missing Magisk stub APK: {stub_path}")
        shutil.copyfile(stub_path, os.path.join(self.magisk_dir, "stub.apk"))

        # Updating Magisk from Magisk manager will modify bootanim.rc, 
        # So it is necessary to backup the original bootanim.rc.
        bootanim_path = os.path.join(self.copy_dir, "system", "etc", "init", "bootanim.rc")
        gz_filename = os.path.join(bootanim_path)+".gz"
        with gzip.open(gz_filename,'wb') as f_gz:
            f_gz.write(self.oringinal_bootanim.encode('utf-8'))
        os.chmod(gz_filename, 0o644)
        with open(bootanim_path, "w") as initfile:
            initfile.write(self.oringinal_bootanim+self.bootanim_component)

        # Docker preserves directory modes when copying this staging tree into
        # the image. Keep system directories traversable regardless of the
        # host umask, and use normal read-only modes for packaged artifacts.
        for directory in (
                self.copy_dir,
                os.path.join(self.copy_dir, "system"),
                os.path.join(self.copy_dir, "system", "etc"),
                os.path.join(self.copy_dir, "system", "etc", "init"),
                self.magisk_dir,
                os.path.join(self.copy_dir, "sbin")):
            os.chmod(directory, 0o755)
        os.chmod(os.path.join(self.magisk_dir, "magisk.apk"), 0o644)
        os.chmod(os.path.join(self.magisk_dir, "stub.apk"), 0o644)
        os.chmod(bootanim_path, 0o644)
