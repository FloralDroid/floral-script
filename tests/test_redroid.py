import hashlib
import io
import os
import stat
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr
from unittest.mock import Mock, patch

import patch as redroid
from stuff.general import General
from stuff.houdini import Houdini
from stuff.houdini_hack import Houdini_Hack
from stuff.magisk import Magisk
from stuff.ndk import Ndk


class RedroidTest(unittest.TestCase):
    def test_ndk_release_matches_android_version(self):
        android_11 = Ndk("11.0.0")
        android_12 = Ndk("12.0.0")
        android_12_64only = Ndk("12.0.0_64only")

        self.assertEqual(
            android_11.commit,
            "9324a8914b649b885dad6f2bfd14a67e5d1520bf")
        self.assertEqual(
            android_12.commit,
            "c2093bd678eb493ea0f918e01ab76c0695a54c3c")
        self.assertEqual(
            android_12.dl_link,
            "https://raw.githubusercontent.com/zhouziyang/"
            "libndk_translation/c2093bd678eb493ea0f918e01ab76c0695a54c3c/"
            "libndk_translation-12.0.0.tar")
        self.assertEqual(android_12.source_format, "tar")
        self.assertNotIn(".", android_12.copy_paths())
        self.assertIn("lib64/libndk_translation.so", android_12.copy_paths())
        self.assertIn("lib64/libnb.so", android_12.copy_paths())
        self.assertEqual(android_12.release, android_12_64only.release)
        self.assertNotEqual(android_11.dl_file_name, android_12.dl_file_name)

    def test_ndk_rejects_unsupported_android_version(self):
        with self.assertRaisesRegex(ValueError, "Android 13.0.0"):
            Ndk("13.0.0")

    def test_ndk_install_is_arm64_only(self):
        installer = Ndk("11.0.0")
        self.assertIn(
            "bin/ndk_translation_program_runner_binfmt_misc_arm64",
            installer.executable_files())
        self.assertNotIn("bin/arm/app_process", installer.executable_files())
        self.assertIn("lib64/libndk_translation.so", installer.copy_paths())
        self.assertNotIn("bin/arm64", installer.copy_paths())
        self.assertNotIn("lib64", installer.copy_paths())
        self.assertIn("etc/ld.config.arm64.txt", installer.copy_paths())
        self.assertNotIn(".", installer.copy_paths())

    def test_general_extract_removes_stale_files(self):
        with tempfile.TemporaryDirectory() as work_dir:
            archive_path = os.path.join(work_dir, "archive.zip")
            extract_dir = os.path.join(work_dir, "extract")
            os.makedirs(extract_dir)
            with open(os.path.join(extract_dir, "stale"), "w", encoding="utf-8"):
                pass
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("current", "ok")

            installer = General()
            installer.dl_file_name = archive_path
            installer.extract_to = extract_dir
            installer.extract()

            self.assertFalse(os.path.exists(os.path.join(extract_dir, "stale")))
            self.assertTrue(os.path.isfile(os.path.join(extract_dir, "current")))

    def test_general_validates_elf_machine_and_android_api(self):
        with tempfile.NamedTemporaryFile() as elf_file, \
                patch("stuff.general.subprocess.run") as readelf:
            readelf.side_effect = [
                Mock(stdout="  Machine: AArch64\n"),
                Mock(stdout="   description data: 1f 00 00 00 \n"),
            ]

            General.validate_elf(
                elf_file.name, "AArch64", android_api=31)

        self.assertEqual(readelf.call_count, 2)

    def test_general_rejects_wrong_elf_machine(self):
        with tempfile.NamedTemporaryFile() as elf_file, \
                patch("stuff.general.subprocess.run") as readelf:
            readelf.return_value.stdout = "  Machine: AArch64\n"

            with self.assertRaisesRegex(ValueError, "Unexpected ELF machine"):
                General.validate_elf(elf_file.name, "X86-64")

    def test_general_routes_binfmt_and_init_to_dispatcher(self):
        with tempfile.TemporaryDirectory() as system_dir:
            binfmt_dir = os.path.join(system_dir, "etc", "binfmt_misc")
            init_dir = os.path.join(system_dir, "etc", "init")
            os.makedirs(binfmt_dir)
            os.makedirs(init_dir)
            registration_path = os.path.join(binfmt_dir, "arm64_exe")
            with open(registration_path, "w", encoding="utf-8") as registration:
                registration.write(
                    ":arm64_exe:M::magic::/system/bin/houdini64:P\n")
            init_path = os.path.join(init_dir, "translation.rc")
            with open(init_path, "w", encoding="utf-8") as init_file:
                init_file.write(
                    "exec -- /system/bin/"
                    "ndk_translation_program_runner_binfmt_misc_arm64\n")

            General.route_binfmt_to(
                system_dir, "/system/bin/floral_nativebridge_runner")

            with open(registration_path, encoding="utf-8") as registration:
                self.assertEqual(
                    registration.read(),
                    ":arm64_exe:M::magic::/system/bin/"
                    "floral_nativebridge_runner:P\n")
            with open(init_path, encoding="utf-8") as init_file:
                self.assertEqual(
                    init_file.read(),
                    "exec -- /system/bin/floral_nativebridge_runner\n")

    def test_general_finalizes_ndk_host_and_isolates_houdini(self):
        with tempfile.TemporaryDirectory() as work_dir:
            backend_dirs = []
            for backend in ("ndk", "houdini"):
                system_dir = os.path.join(work_dir, backend, "system")
                binfmt_dir = os.path.join(system_dir, "etc", "binfmt_misc")
                init_dir = os.path.join(system_dir, "etc", "init")
                os.makedirs(binfmt_dir)
                os.makedirs(init_dir)
                for name in ("arm64_exe", "arm64_dyn"):
                    with open(os.path.join(binfmt_dir, name), "w", encoding="utf-8") as registration:
                        registration.write(
                            ":{}:M::magic::/system/bin/floral_nativebridge_runner:P\n".format(name))
                init_name = "ndk_translation.rc" if backend == "ndk" else "houdini.rc"
                with open(os.path.join(init_dir, init_name), "w", encoding="utf-8"):
                    pass
                if backend == "houdini":
                    for name in ("ld_config.patch", "ld_config_swcodec.patch"):
                        with open(os.path.join(system_dir, "etc", name), "w", encoding="utf-8"):
                            pass
                if backend == "houdini":
                    for relative_path in (
                            "lib64/arm64/libc.so",
                            "lib64/arm64/nb/libc.so"):
                        guest_library = os.path.join(system_dir, relative_path)
                        os.makedirs(os.path.dirname(guest_library), exist_ok=True)
                        with open(guest_library, "w", encoding="utf-8") as library:
                            library.write(relative_path)
                else:
                    translator = os.path.join(
                        system_dir, "lib64", "libndk_translation.so")
                    os.makedirs(os.path.dirname(translator), exist_ok=True)
                    with open(translator, "w", encoding="utf-8") as library:
                        library.write(backend)
                    with open(
                            os.path.join(system_dir, "etc",
                                         "ld.config.arm64.txt"),
                            "w", encoding="utf-8") as config:
                        config.write(
                            "namespace.default.search.paths = "
                            "/system/${LIB}/arm64\n")
                    proxy = os.path.join(
                        system_dir, "lib64",
                        "libndk_translation_proxy_libc.so")
                    os.makedirs(os.path.dirname(proxy), exist_ok=True)
                    with open(proxy, "w", encoding="utf-8"):
                        pass
                    runner = os.path.join(
                        system_dir, "bin",
                        "ndk_translation_program_runner_binfmt_misc_arm64")
                    os.makedirs(os.path.dirname(runner), exist_ok=True)
                    with open(runner, "w", encoding="utf-8"):
                        pass
                backend_dirs.append(os.path.join(work_dir, backend))

            output_dir = os.path.join(work_dir, "nativebridge")
            General.finalize_nativebridge_installation(backend_dirs, output_dir)

            self.assertTrue(os.path.isfile(os.path.join(
                output_dir, "system", "etc", "binfmt_misc", "arm64_exe")))
            self.assertTrue(os.path.isfile(os.path.join(
                output_dir, "system", "etc", "init",
                "floral-nativebridge-translation.rc")))
            for relative_path in (
                    "bin/arm",
                    "bin/arm64",
                    "lib/arm",
                    "lib64/arm64"):
                self.assertTrue(os.path.isdir(os.path.join(
                    output_dir, "system", relative_path)))
            for relative_path in (
                    "etc/cpuinfo.arm.txt",
                    "etc/cpuinfo.arm64.txt"):
                target = os.path.join(output_dir, "system", relative_path)
                self.assertTrue(os.path.isfile(target))
                self.assertEqual(os.path.getsize(target), 0)
            self.assertFalse(os.path.exists(os.path.join(
                output_dir, "system", "etc", "ld.config.arm.txt")))
            guest_config = os.path.join(
                output_dir, "system", "floral", "ndk", "etc",
                "ld.config.arm64.txt")
            self.assertTrue(os.path.isfile(guest_config))
            with open(guest_config, encoding="utf-8") as config:
                self.assertIn("/system/${LIB}/arm64", config.read())
            ndk_root = os.path.join(output_dir, "system")
            self.assertTrue(os.path.isfile(os.path.join(
                ndk_root, "lib64", "libndk_translation.so")))
            self.assertTrue(os.path.isfile(os.path.join(
                ndk_root, "lib64", "libndk_translation_proxy_libc.so")))
            self.assertTrue(os.path.isfile(os.path.join(
                ndk_root, "bin",
                "ndk_translation_program_runner_binfmt_misc_arm64")))
            self.assertTrue(os.path.isdir(os.path.join(
                ndk_root, "lib64", "arm64")))
            self.assertFalse(os.path.exists(os.path.join(
                ndk_root, "lib64", "arm64", "linker64")))
            self.assertFalse(os.path.exists(os.path.join(
                ndk_root, "etc", "init", "ndk_translation.rc")))
            self.assertFalse(os.path.exists(os.path.join(
                ndk_root, "etc", "ld_config.patch")))
            self.assertFalse(os.path.exists(os.path.join(
                ndk_root, "etc", "ld_config_swcodec.patch")))
            houdini_root = os.path.join(
                output_dir, "system", "floral", "houdini")
            for relative_path in (
                    "lib64/arm64/libc.so",
                    "lib64/arm64/nb/libc.so"):
                self.assertTrue(os.path.isfile(os.path.join(
                    houdini_root, relative_path)))

    def test_general_rejects_ndk_guest_userspace(self):
        with tempfile.TemporaryDirectory() as work_dir:
            ndk_root = os.path.join(work_dir, "ndk")
            guest_root = os.path.join(
                ndk_root, "system", "lib64", "arm64")
            os.makedirs(guest_root)
            config = os.path.join(ndk_root, "system", "etc",
                                  "ld.config.arm64.txt")
            os.makedirs(os.path.dirname(config), exist_ok=True)
            with open(config, "w", encoding="utf-8") as config_file:
                config_file.write("namespace.default.search.paths=/system/lib64/arm64\n")

            output_dir = os.path.join(work_dir, "nativebridge")
            with self.assertRaisesRegex(ValueError, "AOSP guest userspace"):
                General.finalize_nativebridge_installation([ndk_root], output_dir)

    def test_ndk_copy_validates_files_and_normalizes_permissions(self):
        with tempfile.TemporaryDirectory() as work_dir:
            installer = Ndk("12.0.0")
            installer.extract_to = os.path.join(work_dir, "extract")
            installer.copy_dir = os.path.join(work_dir, "copy")
            source_root = os.path.join(installer.extract_to, "system")
            os.makedirs(source_root)

            library_hashes = {}
            for relative_path in installer.release["library_sha256"]:
                file_path = os.path.join(source_root, relative_path)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                contents = relative_path.encode("utf-8")
                with open(file_path, "wb") as library:
                    library.write(contents)
                library_hashes[relative_path] = hashlib.sha256(
                    contents).hexdigest()
            installer.release = dict(installer.release)
            installer.release["library_sha256"] = library_hashes

            required_files = installer.executable_files() + (
                "lib64/arm64/libc.so",
                "lib64/arm64/libdl.so",
                "lib64/arm64/libm.so",
                "etc/init/ndk_translation.rc",
                "etc/ld.config.arm64.txt",
                "etc/binfmt_misc/arm64_dyn",
                "etc/binfmt_misc/arm64_exe",
                "lib64/libndk_translation_proxy_libc.so",
            )
            for relative_path in required_files:
                file_path = os.path.join(source_root, relative_path)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "wb") as required_file:
                    if relative_path.startswith("etc/binfmt_misc/"):
                        required_file.write(
                            b":arm64:M::magic::/system/bin/"
                            b"ndk_translation_program_runner_binfmt_misc_arm64:P\n")
                    else:
                        required_file.write(b"required")
                os.chmod(file_path, 0o600)
            for relative_path, target in (
                    ("lib64/libnb.so", "libndk_translation.so"),
                    ("lib/libnb.so", "libndk_translation.so")):
                link_path = os.path.join(source_root, relative_path)
                os.makedirs(os.path.dirname(link_path), exist_ok=True)
                os.symlink(target, link_path)

            with patch.object(installer, "validate_elf") as validate_elf:
                installer.copy()

            system_dir = os.path.join(installer.copy_dir, "system")
            executable = os.path.join(system_dir, installer.executable_files()[0])
            library = os.path.join(system_dir, "lib64", "libndk_translation.so")
            self.assertEqual(stat.S_IMODE(os.stat(executable).st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(os.stat(library).st_mode), 0o644)
            self.assertFalse(os.path.exists(os.path.join(system_dir, "lib")))
            self.assertFalse(os.path.exists(os.path.join(system_dir, "bin", "arm64")))
            self.assertFalse(os.path.exists(os.path.join(
                system_dir, "lib64", "arm64")))
            self.assertEqual(
                os.readlink(os.path.join(system_dir, "lib64", "libnb.so")),
                "libndk_translation.so")
            self.assertTrue(os.path.isfile(os.path.join(
                system_dir, "lib64", "libndk_translation_proxy_libc.so")))
            self.assertTrue(os.path.isfile(os.path.join(
                system_dir, "etc", "ld.config.arm64.txt")))
            validate_elf.assert_any_call(
                os.path.join(source_root, "lib64", "libndk_translation.so"),
                "X86-64", android_api=31)

    def test_ndk_rejects_tampered_translation_library(self):
        with tempfile.TemporaryDirectory() as work_dir:
            installer = Ndk("12.0.0")
            source_root = os.path.join(work_dir, "system")
            library_path = os.path.join(
                source_root, "lib64", "libndk_translation.so")
            os.makedirs(os.path.dirname(library_path))
            with open(library_path, "wb") as library:
                library.write(b"tampered")

            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                installer.validate_source(source_root)

    def test_houdini_copy_normalizes_permissions(self):
        with tempfile.TemporaryDirectory() as work_dir:
            installer = Houdini("12.0.0")
            installer.extract_to = os.path.join(work_dir, "extract")
            installer.copy_dir = os.path.join(work_dir, "copy")
            archive_root = os.path.join(
                installer.extract_to,
                "vendor_intel_proprietary_houdini-0e0164611d5fe5595229854759c30a9b5c1199a5",
                "prebuilts",
            )
            for relative_path in (
                    "bin/houdini",
                    "bin/houdini64",
                    "lib/arm/libc.so",
                    "lib64/arm64/libc.so",
                    "lib64/arm64/nb/libc.so",
                    "lib64/arm64/nb/libm.so",
                    "lib64/arm64/nb/libdl.so",
                    "lib/libhoudini.so",
                    "lib64/libhoudini.so",
                    "etc/binfmt_misc/arm64_exe",
                    "etc/init/arm.rc"):
                file_path = os.path.join(archive_root, relative_path)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "wb") as payload:
                    if relative_path == "etc/binfmt_misc/arm64_exe":
                        payload.write(
                            b":arm64_exe:M::magic::/system/bin/houdini64:P\n")
                    else:
                        payload.write(b"payload")
                os.chmod(file_path, 0o600)

            with patch.object(installer, "validate_elf") as validate_elf:
                installer.copy()

            system_dir = os.path.join(installer.copy_dir, "system")
            for relative_path in (
                    "lib/arm/libc.so",
                    "lib64/arm64/libc.so",
                    "lib/libhoudini.so",
                    "lib64/libhoudini.so",
                    "etc/binfmt_misc/arm64_exe",
                    "etc/init/arm.rc",
                    "etc/init/houdini.rc"):
                file_path = os.path.join(system_dir, relative_path)
                self.assertEqual(stat.S_IMODE(os.stat(file_path).st_mode), 0o644)

            for relative_path in installer.executable_files:
                file_path = os.path.join(system_dir, relative_path)
                self.assertEqual(stat.S_IMODE(os.stat(file_path).st_mode), 0o755)

            self.assertEqual(
                stat.S_IMODE(
                    os.stat(os.path.join(system_dir, "lib", "arm")).st_mode),
                0o755,
            )
            self.assertEqual(validate_elf.call_count, 3)
            validate_elf.assert_any_call(
                os.path.join(archive_root, "lib64", "libhoudini.so"),
                "X86-64")
            validate_elf.assert_any_call(
                os.path.join(archive_root, "lib64", "arm64", "libc.so"),
                "AArch64", android_api=31)
            validate_elf.assert_any_call(
                os.path.join(
                    archive_root, "lib64", "arm64", "nb", "libc.so"),
                "AArch64", android_api=31)

    def test_houdini_hack_normalizes_only_overlay_permissions(self):
        with tempfile.TemporaryDirectory() as work_dir:
            installer = Houdini_Hack("12.0.0")
            installer.extract_to = os.path.join(work_dir, "extract")
            installer.copy_dir = os.path.join(work_dir, "copy")
            archive_root = os.path.join(
                installer.extract_to,
                "redroid_libhoudini_hack-"
                "a2194c5e294cbbfdfe87e51eb9eddb4c3621d8c3",
                installer.version,
            )
            patch_path = os.path.join(archive_root, "etc", "ld_config.patch")
            os.makedirs(os.path.dirname(patch_path))
            with open(patch_path, "wb") as linker_patch:
                linker_patch.write(b"patch")
            os.chmod(patch_path, 0o600)
            init_path = os.path.join(
                archive_root, "etc", "init", "hw", "init.rc")
            os.makedirs(os.path.dirname(init_path))
            with open(init_path, "wb") as init_file:
                init_file.write(b"init")
            os.chmod(init_path, 0o600)

            houdini_path = os.path.join(
                installer.copy_dir, "system", "bin", "houdini64")
            os.makedirs(os.path.dirname(houdini_path))
            with open(houdini_path, "wb") as interpreter:
                interpreter.write(b"interpreter")
            os.chmod(houdini_path, 0o755)

            installer.copy()

            copied_patch = os.path.join(
                installer.copy_dir, "system", "etc", "ld_config.patch")
            self.assertEqual(
                stat.S_IMODE(os.stat(copied_patch).st_mode), 0o644)
            copied_init = os.path.join(
                installer.copy_dir, "system", "etc", "init", "hw", "init.rc")
            self.assertEqual(
                stat.S_IMODE(os.stat(copied_init).st_mode), 0o644)
            self.assertEqual(
                stat.S_IMODE(os.stat(houdini_path).st_mode), 0o755)

    def test_magisk_release_is_pinned_to_floral_build(self):
        self.assertEqual(
            Magisk.dl_link,
            "https://github.com/FloralDroid/Magisk/releases/download/"
            "v30.7-floral.1/Magisk-v30.7-floral.1.apk",
        )
        self.assertEqual(Magisk.act_md5, "4e7adff8ddaea6cad9a47a67f89ad881")

    def test_magisk_manager_install_checks_actual_package(self):
        self.assertIn("pm uninstall com.topjohnwu.magisk", Magisk.bootanim_component)
        self.assertNotIn("io.github.huskydg.magisk", Magisk.bootanim_component)
        self.assertIn("pm install -r /system/etc/init/magisk/magisk.apk", Magisk.bootanim_component)

    def test_magisk_bootstrap_handles_disabled_selinux_and_early_post_fs_data(self):
        self.assertEqual(
            Magisk.bootanim_component.count("if [ -r /sys/fs/selinux/policy ]; then"),
            3,
        )
        self.assertIn("mkdir /data/adb/magisk 755", Magisk.bootanim_component)
        self.assertIn(
            "cp -f /system/etc/init/magisk/busybox /data/adb/magisk/busybox",
            Magisk.bootanim_component,
        )
        self.assertIn(
            "cp -f /system/etc/init/magisk/magiskpolicy /data/adb/magisk/magiskpolicy",
            Magisk.bootanim_component,
        )
        self.assertIn(
            "PATH=/system/bin; export PATH; exec /sbin/magisk --auto-selinux --post-fs-data",
            Magisk.bootanim_component,
        )

    def test_magisk_copy_includes_stub_apk_for_signature_verification(self):
        with tempfile.TemporaryDirectory() as work_dir:
            extract_dir = os.path.join(work_dir, "extract")
            lib_dir = os.path.join(extract_dir, "lib", "x86_64")
            os.makedirs(lib_dir)
            os.makedirs(os.path.join(extract_dir, "assets"))
            with open(os.path.join(lib_dir, "libmagisk.so"), "wb") as native:
                native.write(b"native")
            with open(os.path.join(extract_dir, "assets", "stub.apk"), "wb") as stub:
                stub.write(b"stub")

            source_apk = os.path.join(work_dir, "magisk.apk")
            with open(source_apk, "wb") as apk:
                apk.write(b"manager")

            copy_dir = os.path.join(work_dir, "copy")
            magisk_dir = os.path.join(copy_dir, "system", "etc", "init", "magisk")
            with patch.object(Magisk, "extract_to", extract_dir), \
                    patch.object(Magisk, "copy_dir", copy_dir), \
                    patch.object(Magisk, "magisk_dir", magisk_dir), \
                    patch.object(Magisk, "dl_file_name", source_apk):
                Magisk().copy()

            with open(os.path.join(magisk_dir, "stub.apk"), "rb") as stub:
                self.assertEqual(stub.read(), b"stub")
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(copy_dir, "system")).st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(magisk_dir, "magisk")).st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(magisk_dir, "magisk.apk")).st_mode), 0o644)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(magisk_dir, "stub.apk")).st_mode), 0o644)

    def test_base_and_output_images_are_required(self):
        with patch.object(sys, "argv", ["redroid.py"]), \
                redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                redroid.main()

        self.assertEqual(error.exception.code, 2)

    def test_custom_base_image_is_preserved(self):
        arguments = [
            "redroid.py",
            "-a",
            "12.0.0",
            "-b",
            "floral:12.0.0",
            "-o",
            "floral:12.0.0-custom",
        ]

        with tempfile.TemporaryDirectory() as work_dir:
            original_dir = os.getcwd()
            with patch.object(sys, "argv", arguments), \
                    patch("patch.subprocess.run") as build, \
                    patch("builtins.print"):
                os.chdir(work_dir)
                try:
                    redroid.main()
                finally:
                    os.chdir(original_dir)

            with open(os.path.join(work_dir, "Dockerfile"), encoding="utf-8") as dockerfile:
                self.assertEqual(dockerfile.read(), "FROM floral:12.0.0\n")

        build.assert_called_once_with(
            ["docker", "build", "-t", "floral:12.0.0-custom", "."],
            check=True,
        )

    def test_combined_nativebridge_backends_share_one_docker_layer(self):
        arguments = [
            "redroid.py",
            "-a",
            "12.0.0",
            "-b",
            "floral:12.0.0",
            "-o",
            "floral:12.0.0-both",
            "-n",
            "-i",
        ]

        with tempfile.TemporaryDirectory() as work_dir:
            original_dir = os.getcwd()
            with patch.object(sys, "argv", arguments), \
                    patch("patch.Ndk") as ndk, \
                    patch("patch.Houdini") as houdini, \
                    patch("patch.Houdini_Hack") as hack, \
                    patch("patch.General.finalize_nativebridge_installation") as finalize, \
                    patch("patch.helper.host", return_value=("x86_64", 64)), \
                    patch("patch.subprocess.run"), \
                    patch("builtins.print"):
                os.chdir(work_dir)
                try:
                    redroid.main()
                finally:
                    os.chdir(original_dir)

            with open(os.path.join(work_dir, "Dockerfile"), encoding="utf-8") as dockerfile:
                dockerfile = dockerfile.read()
            self.assertIn("COPY nativebridge /\n", dockerfile)
            self.assertNotIn("RUN ", dockerfile)
            self.assertNotIn("ld_config.patch", dockerfile)
            self.assertNotIn("COPY ndk /\n", dockerfile)
            self.assertNotIn("COPY houdini /\n", dockerfile)

        finalize.assert_called_once_with(["ndk", "houdini"])
        ndk.return_value.install.assert_called_once_with()
        houdini.return_value.install.assert_called_once_with()
        hack.return_value.install.assert_not_called()

    def test_ndk_build_passes_selected_android_version(self):
        arguments = [
            "redroid.py",
            "-a",
            "12.0.0",
            "-b",
            "floral:12.0.0",
            "-o",
            "floral:12.0.0-ndk",
            "-n",
        ]

        with tempfile.TemporaryDirectory() as work_dir:
            original_dir = os.getcwd()
            with patch.object(sys, "argv", arguments), \
                    patch("patch.Ndk") as ndk, \
                    patch("patch.General.finalize_nativebridge_installation"), \
                    patch("patch.helper.host", return_value=("x86_64", 64)), \
                    patch("patch.subprocess.run"), \
                    patch("builtins.print"):
                os.chdir(work_dir)
                try:
                    redroid.main()
                finally:
                    os.chdir(original_dir)

        ndk.assert_called_once_with("12.0.0")
        ndk.return_value.install.assert_called_once_with()

    def test_houdini_build_passes_selected_android_version(self):
        arguments = [
            "redroid.py",
            "-a",
            "12.0.0",
            "-b",
            "floral:12.0.0",
            "-o",
            "floral:12.0.0-houdini",
            "-i",
        ]

        with tempfile.TemporaryDirectory() as work_dir:
            original_dir = os.getcwd()
            with patch.object(sys, "argv", arguments), \
                    patch("patch.Houdini") as houdini, \
                    patch("patch.Houdini_Hack") as hack, \
                    patch("patch.General.finalize_nativebridge_installation"), \
                    patch("patch.helper.host", return_value=("x86_64", 64)), \
                    patch("patch.subprocess.run"), \
                    patch("builtins.print"):
                os.chdir(work_dir)
                try:
                    redroid.main()
                finally:
                    os.chdir(original_dir)

        houdini.assert_called_once_with("12.0.0")
        houdini.return_value.install.assert_called_once_with()
        hack.assert_not_called()

    def test_64only_translation_installs_both_12_payloads(self):
        arguments = [
            "redroid.py",
            "-a",
            "12.0.0_64only",
            "-b",
            "floral:12.0.0_64only",
            "-o",
            "floral:12.0.0_64only-translation",
            "-n",
            "-i",
        ]

        with tempfile.TemporaryDirectory() as work_dir:
            original_dir = os.getcwd()
            with patch.object(sys, "argv", arguments), \
                    patch("patch.Ndk") as ndk, \
                    patch("patch.Houdini") as houdini, \
                    patch("patch.Houdini_Hack") as hack, \
                    patch("patch.General.finalize_nativebridge_installation") as finalize, \
                    patch("patch.helper.host", return_value=("x86_64", 64)), \
                    patch("patch.subprocess.run"), \
                    patch("builtins.print"):
                os.chdir(work_dir)
                try:
                    redroid.main()
                finally:
                    os.chdir(original_dir)

        ndk.assert_called_once_with("12.0.0")
        houdini.assert_called_once_with("12.0.0")
        hack.assert_not_called()
        finalize.assert_called_once_with(["ndk", "houdini"])


if __name__ == "__main__":
    unittest.main()
