

import os
import shutil
import zipfile

from tools.helper import bcolors, download_file, file_checksum, print_color


class General:
    native_bridge_runners = (
        "/system/bin/ndk_translation_program_runner_binfmt_misc_arm64",
        "/system/bin/ndk_translation_program_runner_binfmt_misc",
        "/system/bin/houdini64",
        "/system/bin/houdini",
    )

    def checksum(self):
        if hasattr(self, "act_sha256"):
            return "sha256", self.act_sha256
        return "md5", self.act_md5

    def download(self):
        algorithm, expected_checksum = self.checksum()
        local_checksum = ""
        if os.path.isfile(self.dl_file_name):
            local_checksum = file_checksum(self.dl_file_name, algorithm)
        if local_checksum == expected_checksum:
            return

        if os.path.isfile(self.dl_file_name):
            os.remove(self.dl_file_name)
            print_color(
                "{} mismatch, redownloading now ....".format(algorithm),
                bcolors.YELLOW)

        local_checksum = download_file(
            self.dl_link, self.dl_file_name, algorithm)
        if local_checksum != expected_checksum:
            os.remove(self.dl_file_name)
            raise ValueError(
                "{} mismatch for {}: expected {}, got {}".format(
                    algorithm, self.dl_link, expected_checksum, local_checksum))

    def extract(self):
        print_color("Extracting archive...", bcolors.GREEN)
        print(self.dl_file_name)
        print(self.extract_to)
        # A fixed extraction directory must never retain files from an older
        # release, otherwise a removed blob can leak into the next image.
        if os.path.exists(self.extract_to):
            shutil.rmtree(self.extract_to)
        with zipfile.ZipFile(self.dl_file_name) as z:
            z.extractall(self.extract_to)

    def copy(self):
        pass

    @classmethod
    def route_binfmt_to(cls, system_dir, interpreter):
        """Route copied ARM binfmt registrations through one dispatcher."""
        binfmt_dir = os.path.join(system_dir, "etc", "binfmt_misc")
        if os.path.isdir(binfmt_dir):
            for file_name in os.listdir(binfmt_dir):
                file_path = os.path.join(binfmt_dir, file_name)
                if not os.path.isfile(file_path):
                    continue
                with open(file_path, encoding="utf-8") as registration:
                    contents = registration.read()
                newline = "\n" if contents.endswith("\n") else ""
                fields = contents.rstrip("\n").rsplit(":", 2)
                if len(fields) != 3:
                    raise ValueError(
                        "Invalid binfmt registration: {}".format(file_path))
                with open(file_path, "w", encoding="utf-8") as registration:
                    registration.write(
                        "{}:{}:{}{}".format(
                            fields[0], interpreter, fields[2], newline))

        init_dir = os.path.join(system_dir, "etc", "init")
        if not os.path.isdir(init_dir):
            return
        for file_name in os.listdir(init_dir):
            if not file_name.endswith(".rc"):
                continue
            file_path = os.path.join(init_dir, file_name)
            with open(file_path, encoding="utf-8") as init_file:
                contents = init_file.read()
            updated = contents
            for runner in cls.native_bridge_runners:
                updated = updated.replace(runner, interpreter)
            if updated != contents:
                with open(file_path, "w", encoding="utf-8") as init_file:
                    init_file.write(updated)

    def install(self):
        # pass
        self.download()
        self.extract()
        self.copy()
