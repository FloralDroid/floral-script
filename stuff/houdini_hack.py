import os
import re
import shutil
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
