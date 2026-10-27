import os
import re
import shutil
import subprocess
from stuff.general import General
from tools.helper import bcolors, get_download_dir, print_color


class Houdini_Hack(General):
    download_loc = get_download_dir()
    copy_dir = "./houdini"
    dl_file_name = os.path.join(download_loc, "libhoudini_hack.zip")
    extract_to = "/tmp/houdinihackunpack"

    def __init__(self, version):
        self.version = version
        self.dl_link = "https://github.com/rote66/redroid_libhoudini_hack/archive/a2194c5e294cbbfdfe87e51eb9eddb4c3621d8c3.zip"
        self.act_md5 = "8f71a58f3e54eca879a2f7de64dbed58"

    def download(self):
        print_color("Downloading libhoudini_hack now .....", bcolors.GREEN)
        super().download()

    @staticmethod
    def normalize_permissions(source_dir):
        # The overlay contains linker configuration and init files, not
        # executables. Keep it readable without changing the Houdini binaries
        # that were copied before this overlay is applied.
        for parent, directories, files in os.walk(source_dir):
            os.chmod(parent, 0o755)
            for directory in directories:
                os.chmod(os.path.join(parent, directory), 0o755)
            for file_name in files:
                file_path = os.path.join(parent, file_name)
                if not os.path.islink(file_path):
                    os.chmod(file_path, 0o644)

    def copy(self):
        print_color("Copying libhoudini hack files ...", bcolors.GREEN)
        name = re.findall(r"([a-zA-Z0-9]+)\.zip", self.dl_link)[0]
        source_dir = os.path.join(
            self.extract_to,
            "redroid_libhoudini_hack-" + name,
            self.version,
        )
        self.normalize_permissions(source_dir)
        shutil.copytree(
            source_dir,
            os.path.join(self.copy_dir, "system"),
            dirs_exist_ok=True,
        )

        if not self.version == "9.0.0":
            init_path = os.path.join(self.copy_dir, "system", "etc", "init", "hw", "init.rc")
            os.chmod(init_path, 0o644)

    def install_12l(self, container, base_image):
        # The legacy archive replaces init.rc with Android 12 content. Copy
        # the selected image's file instead and retain its 12L customizations.
        system_dir = os.path.join(self.copy_dir, "system")
        init_dir = os.path.join(system_dir, "etc", "init", "hw")
        os.makedirs(init_dir, exist_ok=True)
        init_path = os.path.join(init_dir, "init.rc")
        container_id = subprocess.run(
            [container, "create", base_image], check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        try:
            subprocess.run(
                [container, "cp", container_id + ":/system/etc/init/hw/init.rc",
                 init_path], check=True)
        finally:
            subprocess.run([container, "rm", container_id], check=True)

        with open(init_path, encoding="utf-8") as init_file:
            init = init_file.read()
        hooks = (
            ("    exec -- /system/bin/bootstrap/linkerconfig "
             "--target /linkerconfig/bootstrap\n", "/linkerconfig/bootstrap"),
            ("    update_linker_config\n", "/linkerconfig"),
            ("    perform_apex_config\n", "/linkerconfig"),
        )
        for anchor, target in hooks:
            if init.count(anchor) != 1:
                raise ValueError("Unsupported Android 12L init.rc: " + anchor.strip())
            init = init.replace(
                anchor, anchor + "    exec -- /system/bin/sh "
                "/system/etc/houdini-12l.sh " + target + "\n")
        with open(init_path, "w", encoding="utf-8") as init_file:
            init_file.write(init)
        os.chmod(init_path, 0o644)
        script_path = os.path.join(system_dir, "etc", "houdini-12l.sh")
        shutil.copyfile(
            os.path.join(os.path.dirname(__file__), "houdini_12l.sh"), script_path)
        os.chmod(script_path, 0o644)
