

import os
import shutil
import subprocess
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

    @staticmethod
    def validate_elf(file_path, machine, android_api=None):
        if not os.path.isfile(file_path):
            raise FileNotFoundError("Missing ELF file: {}".format(file_path))

        environment = os.environ.copy()
        environment["LC_ALL"] = "C"
        try:
            header = subprocess.run(
                ["readelf", "--file-header", file_path],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            ).stdout
        except FileNotFoundError as error:
            raise RuntimeError("readelf is required to validate payloads") from error
        except subprocess.CalledProcessError as error:
            raise ValueError("Cannot read ELF file: {}".format(file_path)) from error

        if not any(
                line.startswith("  Machine:") and machine in line
                for line in header.splitlines()):
            raise ValueError(
                "Unexpected ELF machine for {}: expected {}".format(
                    file_path, machine))

        if android_api is None:
            return
        notes = subprocess.run(
            ["readelf", "--notes", file_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        ).stdout
        api_bytes = "{:02x} 00 00 00".format(android_api)
        if "description data: {}".format(api_bytes) not in notes:
            raise ValueError(
                "Unexpected Android API for {}: expected {}".format(
                    file_path, android_api))

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
        """Stage selected translation backends below one isolated system root."""
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)

        output_system = os.path.join(output_dir, "system")
        output_backends = os.path.join(output_system, "floral")
        output_binfmt = os.path.join(output_system, "etc", "binfmt_misc")
        output_init = os.path.join(output_system, "etc", "init")
        os.makedirs(output_binfmt, exist_ok=True)
        os.makedirs(output_init, exist_ok=True)
        os.makedirs(output_backends, exist_ok=True)

        # Zygote bind-mounts the selected payload over these paths after
        # /system is read-only, so every possible target must exist in the
        # image before boot.
        for relative_path in (
                "bin/arm",
                "bin/arm64",
                "lib/arm",
                "lib64/arm64"):
            os.makedirs(os.path.join(output_system, relative_path), exist_ok=True)
        for relative_path in (
                "etc/cpuinfo.arm.txt",
                "etc/cpuinfo.arm64.txt"):
            with open(os.path.join(output_system, relative_path), "w", encoding="utf-8"):
                pass

        registration_names = (
            "arm_exe",
            "arm_dyn",
            "arm64_exe",
            "arm64_dyn",
        )
        available = set()
        for backend in backends:
            backend_name = os.path.basename(os.path.normpath(backend))
            if backend_name not in ("ndk", "houdini"):
                raise ValueError("Unknown native bridge backend: {}".format(backend_name))
            source_system = os.path.join(backend, "system")
            if not os.path.isdir(source_system):
                raise FileNotFoundError(
                    "Missing native bridge backend payload: {}".format(source_system))

            if backend_name == "ndk":
                for relative_path in (
                        "bin/arm64",
                        "lib64/arm64"):
                    forbidden = os.path.join(source_system, relative_path)
                    if os.path.exists(forbidden):
                        raise ValueError(
                            "NDK payload must not contain AOSP guest userspace: "
                            "{}".format(forbidden))
                config_path = os.path.join(
                    source_system, "etc", "ld.config.arm64.txt")
                if not os.path.isfile(config_path):
                    raise FileNotFoundError(
                        "Missing NDK guest linker config: {}".format(config_path))

            system_dir = os.path.join(output_backends, backend_name)
            shutil.copytree(source_system, system_dir, dirs_exist_ok=True)
            if backend_name == "ndk":
                # The AOSP guest linker reads its architecture-specific config
                # from /system/etc, while NDK's private guest sysroot is not
                # mounted at runtime.
                config_path = os.path.join(
                    system_dir, "etc", "ld.config.arm64.txt")
                shutil.copy2(
                    config_path,
                    os.path.join(output_system, "etc", "ld.config.arm64.txt"))
                os.remove(config_path)
            cls.route_binfmt_to(system_dir, "/system/bin/floral_nativebridge_runner")
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

            # Linker paths are generated from system/linkerconfig; the payload
            # patches are tied to one generated file layout and become stale.
            for name in ("ld_config.patch", "ld_config_swcodec.patch"):
                patch_path = os.path.join(system_dir, "etc", name)
                if os.path.isfile(patch_path):
                    os.remove(patch_path)

            # This is a complete base init script from the Houdini archive,
            # not a backend-specific init fragment.
            backend_init = os.path.join(init_dir, "hw", "init.rc")
            if os.path.isfile(backend_init):
                os.remove(backend_init)

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
