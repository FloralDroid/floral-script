import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

import redroid
from stuff.magisk import Magisk


class RedroidTest(unittest.TestCase):
    def test_magisk_release_is_pinned_to_floral_build(self):
        self.assertEqual(
            Magisk.dl_link,
            "https://github.com/FloralDroid/Magisk/releases/download/"
            "v30.7-floral.1/Magisk-v30.7-floral.1.apk",
        )
        self.assertEqual(Magisk.act_md5, "4e7adff8ddaea6cad9a47a67f89ad881")

    def test_magisk_manager_install_checks_actual_package(self):
        self.assertIn("pm path com.topjohnwu.magisk", Magisk.bootanim_component)
        self.assertNotIn("io.github.huskydg.magisk", Magisk.bootanim_component)

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
                    patch("redroid.subprocess.run") as build, \
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


if __name__ == "__main__":
    unittest.main()
