

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

    @classmethod
    def finalize_nativebridge_installation(cls, backends, output_dir="./nativebridge"):
        """Build one binfmt/init layer for all selected translation backends."""
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)

        output_system = os.path.join(output_dir, "system")
        output_binfmt = os.path.join(output_system, "etc", "binfmt_misc")
        output_init = os.path.join(output_system, "etc", "init")
        os.makedirs(output_binfmt, exist_ok=True)
        os.makedirs(output_init, exist_ok=True)

        registration_names = (
            "arm_exe",
            "arm_dyn",
            "arm64_exe",
            "arm64_dyn",
        )
        available = set()
        for backend in backends:
            system_dir = os.path.join(backend, "system")
            binfmt_dir = os.path.join(system_dir, "etc", "binfmt_misc")
            for name in registration_names:
                source = os.path.join(binfmt_dir, name)
                if not os.path.isfile(source):
                    continue
                destination = os.path.join(output_binfmt, name)
                if name not in available:
                    shutil.copy2(source, destination)
                    available.add(name)
                os.remove(source)

            init_dir = os.path.join(system_dir, "etc", "init")
            for name in ("ndk_translation.rc", "houdini.rc"):
                init_path = os.path.join(init_dir, name)
                if os.path.isfile(init_path):
                    os.remove(init_path)

        lines = [
            "on early-init",
            "    mount binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc",
            "",
            "on post-fs-data",
        ]
        for name in registration_names:
            if name in available:
                lines.append(
                    "    copy /system/etc/binfmt_misc/{} "
                    "/proc/sys/fs/binfmt_misc/register".format(name))
        lines.append("")
        with open(
                os.path.join(output_init, "floral-nativebridge-translation.rc"),
                "w",
                encoding="utf-8") as init_file:
            init_file.write("\n".join(lines))

    def install(self):
        # pass
        self.download()
        self.extract()
        self.copy()
