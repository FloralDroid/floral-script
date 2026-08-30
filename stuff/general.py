

import os
import shutil
import zipfile

from tools.helper import bcolors, download_file, file_checksum, print_color


class General:
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

    def install(self):
        # pass
        self.download()
        self.extract()
        self.copy()
