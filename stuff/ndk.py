import os
import shutil
from stuff.general import General
from tools.helper import bcolors, file_checksum, get_download_dir, print_color


class Ndk(General):
    download_loc = get_download_dir()
    copy_dir = "./ndk"
    repository = "supremegamers/vendor_google_proprietary_ndk_translation-prebuilt"
    android_11_release = {
        "commit": "9324a8914b649b885dad6f2bfd14a67e5d1520bf",
        "archive_sha256": (
            "87089b896ce6fed313dd5c2dd1bf22db857621c27e04471aadda69a1a2795fa1"),
        "fingerprint": (
            "google/guybrush/guybrush_cheets:11/R112-15359.58.0/"
            "9891653:user/release-keys"),
        "library_sha256": {
            "lib/libndk_translation.so": (
                "bffb9977067443f1e4a527b59e68b98443ec18a02baecbca8ccae268e66707a3"),
            "lib64/libndk_translation.so": (
                "bdb9e65e197f67a84f45bb18e42f35af869f8f0e8184ef93b848842e5b6c402c"),
        },
    }
    android_12_release = {
        "commit": "181d9290a69309511185c4417ba3d890b3caaaa8",
        "archive_sha256": (
            "0911fb251773671c245433db5c729f125170137b5b863c576919cd0ccd052f69"),
        "fingerprint": (
            "google/sdk_gphone64_x86_64/emulator64_x86_64_arm64:12/"
            "S2B2.211203.006/8015633:user/dev-keys"),
        "library_sha256": {
            "lib64/libndk_translation.so": (
                "46432c5ce6aae55c0191c198573780d52ffbbd518dfcbd8ccf262545e39823a6"),
        },
    }
    releases = {
        "11.0.0": android_11_release,
        "12.0.0": android_12_release,
        "12.0.0_64only": android_12_release,
    }
    all_executable_files = (
        "bin/arm/app_process",
        "bin/arm/linker",
        "bin/arm64/app_process64",
        "bin/arm64/linker64",
        "bin/ndk_translation_program_runner_binfmt_misc",
        "bin/ndk_translation_program_runner_binfmt_misc_arm64",
    )
    android_12_executable_files = (
        "bin/ndk_translation_program_runner_binfmt_misc_arm64",
    )
#     init_rc_component = """
# # Enable native bridge for target executables
# on early-init
#     mount binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc

# on property:ro.enable.native.bridge.exec=1
#     copy /system/etc/binfmt_misc/arm_exe /proc/sys/fs/binfmt_misc/register
#     copy /system/etc/binfmt_misc/arm_dyn /proc/sys/fs/binfmt_misc/register
#     copy /system/etc/binfmt_misc/arm64_exe /proc/sys/fs/binfmt_misc/register
#     copy /system/etc/binfmt_misc/arm64_dyn /proc/sys/fs/binfmt_misc/register
# """

    def __init__(self, android_version, arm64_only=True):
        if android_version not in self.releases:
            raise ValueError(
                "No available libndk translation for Android {}".format(
                    android_version))

        self.android_version = android_version
        self.arm64_only = arm64_only
        self.release = self.releases[android_version]
        self.commit = self.release["commit"]
        self.dl_link = "https://codeload.github.com/{}/zip/{}".format(
            self.repository, self.commit)
        self.dl_file_name = os.path.join(
            self.download_loc,
            "libndktranslation-{}.zip".format(android_version))
        self.extract_to = "/tmp/libndkunpack-{}".format(android_version)
        self.archive_root = (
            "vendor_google_proprietary_ndk_translation-prebuilt-{}".format(
                self.commit))
        self.act_sha256 = self.release["archive_sha256"]

    def validate_source(self, source_root):
        readme_path = os.path.join(source_root, "README.md")
        with open(readme_path, encoding="utf-8") as readme:
            if self.release["fingerprint"] not in readme.read():
                raise ValueError(
                    "NDK translation source fingerprint does not match "
                    "Android {}".format(self.android_version))

        prebuilt_dir = os.path.join(source_root, "prebuilts")
        library_hashes = self.release["library_sha256"]
        if self.arm64_only:
            library_hashes = {
                path: checksum for path, checksum in library_hashes.items()
                if path.startswith("lib64/")
            }
        for relative_path, expected_sha256 in library_hashes.items():
            library_path = os.path.join(prebuilt_dir, relative_path)
            actual_sha256 = file_checksum(library_path, "sha256")
            if actual_sha256 != expected_sha256:
                raise ValueError(
                    "SHA-256 mismatch for {}: expected {}, got {}".format(
                        relative_path, expected_sha256, actual_sha256))
            machine = (
                "X86-64" if relative_path.startswith("lib64/") else "80386")
            self.validate_elf(library_path, machine)

        required_files = self.executable_files() + (
            "etc/init/ndk_translation.rc",)
        if self.arm64_only or self.android_version.startswith("12.0.0"):
            required_files += ("etc/ld.config.arm64.txt",)
        for relative_path in required_files:
            required_path = os.path.join(prebuilt_dir, relative_path)
            if not os.path.isfile(required_path):
                raise FileNotFoundError(
                    "Missing NDK translation file: {}".format(required_path))

    def executable_files(self):
        if self.arm64_only:
            return self.android_12_executable_files
        if self.android_version.startswith("12.0.0"):
            return self.android_12_executable_files
        return self.all_executable_files

    def copy_paths(self):
        if self.arm64_only or self.android_version.startswith("12.0.0"):
            return (
                "bin/ndk_translation_program_runner_binfmt_misc_arm64",
                "etc/binfmt_misc/arm64_dyn",
                "etc/binfmt_misc/arm64_exe",
                "etc/init/ndk_translation.rc",
                "etc/ld.config.arm64.txt",
                "lib64/libndk_translation.so",
            )
        if not self.android_version.startswith("12.0.0"):
            return (".",)
        return ()

    def normalize_permissions(self, system_dir):
        # GitHub ZIP extraction does not reliably preserve executable bits.
        # Normalize the tree, then opt in only the runtime executables.
        for parent, directories, files in os.walk(system_dir):
            os.chmod(parent, 0o755)
            for directory in directories:
                os.chmod(os.path.join(parent, directory), 0o755)
            for file_name in files:
                file_path = os.path.join(parent, file_name)
                if not os.path.islink(file_path):
                    os.chmod(file_path, 0o644)

        for relative_path in self.executable_files():
            os.chmod(os.path.join(system_dir, relative_path), 0o755)

    def download(self):
        print_color("Downloading libndk now .....", bcolors.GREEN)
        super().download()

    def copy(self):
        if os.path.exists(self.copy_dir):
            shutil.rmtree(self.copy_dir)

        print_color("Copying libndk library files ...", bcolors.GREEN)
        source_root = os.path.join(self.extract_to, self.archive_root)
        self.validate_source(source_root)
        system_dir = os.path.join(self.copy_dir, "system")
        source_dir = os.path.join(source_root, "prebuilts")
        for relative_path in self.copy_paths():
            source_path = os.path.join(source_dir, relative_path)
            target_path = os.path.join(system_dir, relative_path)
            if relative_path == ".":
                shutil.copytree(source_dir, system_dir, dirs_exist_ok=True)
            elif os.path.isdir(source_path):
                shutil.copytree(source_path, target_path, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(source_path, target_path)
        self.normalize_permissions(system_dir)
        if self.android_version.startswith("12.0.0"):
            self.route_binfmt_to(
                system_dir, "/system/bin/floral_nativebridge_runner")

        init_path = os.path.join(
            system_dir, "etc", "init", "ndk_translation.rc")
        os.chmod(init_path, 0o644)
        # if not os.path.isfile(init_path):
        #     os.makedirs(os.path.dirname(init_path), exist_ok=True)
        # with open(init_path, "w") as initfile:
        #     initfile.write(self.init_rc_component)
