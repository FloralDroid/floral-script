#!/usr/bin/env python3

import argparse
from stuff.gapps import Gapps
from stuff.litegapps import LiteGapps
from stuff.magisk import Magisk
from stuff.mindthegapps import MindTheGapps
from stuff.ndk import Ndk
from stuff.houdini import Houdini
from stuff.houdini_hack import Houdini_Hack
from stuff.general import General
from stuff.widevine import Widevine
import tools.helper as helper
import subprocess


def main():
    dockerfile = ""
    translation_backends = []
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-a', '--android-version',
                        dest='android',
                        help='Specify the Android version to build',
                        default='11.0.0',
                        choices=['14.0.0', '13.0.0', '12.0.0', '12.0.0_64only', '11.0.0', '10.0.0', '9.0.0', '8.1.0'])
    parser.add_argument('-b', '--base-image',
                        dest='base_image',
                        help='Specify the base container image',
                        required=True)
    parser.add_argument('-o', '--output-image',
                        dest='output_image',
                        help='Specify the output container image',
                        required=True)
    parser.add_argument('-g', '--install-gapps',
                        dest='gapps',
                        help='Install OpenGapps to FloralDroid',
                        action='store_true')
    parser.add_argument('-lg', '--install-litegapps',
                        dest='litegapps',
                        help='Install LiteGapps to FloralDroid',
                        action='store_true')
    parser.add_argument('-n', '--install-ndk-translation',
                        dest='ndk',
                        help='Install libndk translation files',
                        action='store_true')
    parser.add_argument('-i', '--install-houdini',
                        dest='houdini',
                        help='Install houdini files',
                        action='store_true')
    parser.add_argument('-mtg', '--install-mindthegapps',
                        dest='mindthegapps',
                        help='Install MindTheGapps to FloralDroid',
                        action='store_true')
    parser.add_argument('-m', '--install-magisk', dest='magisk',
                        help='Install Magisk ( Bootless )',
                        action='store_true')
    parser.add_argument('-w', '--install-widevine', dest='widevine',
                        help='Integrate Widevine DRM (L3)',
                        action='store_true')
    parser.add_argument('-c', '--container', 
                        dest='container',
                        default='docker',
                        help='Specify container type', 
                        choices=['docker', 'podman'])

    args = parser.parse_args()
    payload_android = "12.0.0" if args.android == "12.0.0_64only" else args.android
    # FROM preserves custom image configuration, including Floral's entrypoint
    # and any default arguments configured by the selected base image.

    dockerfile = dockerfile + "FROM {}\n".format(args.base_image)
    if args.gapps:
        if args.android in ["11.0.0"]:
            Gapps().install()
            dockerfile = dockerfile + "COPY gapps /\n"
        else:
            helper.print_color( "WARNING: OpenGapps only supports 11.0.0", helper.bcolors.YELLOW)
    if args.litegapps:
        LiteGapps(args.android).install()
        dockerfile = dockerfile + "COPY litegapps /\n"
    if args.mindthegapps:
        MindTheGapps(args.android).install()
        dockerfile = dockerfile + "COPY mindthegapps /\n"
    if args.ndk:
        if args.android in ["11.0.0", "12.0.0", "12.0.0_64only"]:
            arch = helper.host()[0]
            if arch == "x86" or arch == "x86_64":
                Ndk(payload_android).install()
                translation_backends.append("ndk")
        else:
            helper.print_color(
                "WARNING: NDK Translation is only validated for FloralDroid Android 11/12",
                helper.bcolors.YELLOW)
    if args.houdini:
        if args.android in ["8.1.0", "9.0.0", "11.0.0", "12.0.0", "12.0.0_64only",
                            "13.0.0", "14.0.0"]:
            arch = helper.host()[0]
            if arch == "x86" or arch == "x86_64":
                Houdini(payload_android).install()
                if payload_android not in ("8.1.0", "12.0.0"):
                    Houdini_Hack(payload_android).install()
                translation_backends.append("houdini")
        else:
            helper.print_color(
                "WARNING: Houdini is only validated for FloralDroid Android 11/12/13/14",
                helper.bcolors.YELLOW)
    if args.magisk:
        Magisk().install()
        dockerfile = dockerfile+"COPY magisk /\n"
    if args.widevine:
        Widevine(args.android).install()
        dockerfile = dockerfile+"COPY widevine /\n"
    if translation_backends:
        General.finalize_nativebridge_installation(translation_backends)
        dockerfile = dockerfile+"COPY nativebridge /\n"
        # The Android base image may not contain a shell.  The finalizer
        # removes legacy hack files before this payload is staged, so no
        # in-image cleanup step is required.
    print("\nDockerfile\n"+dockerfile)
    with open("./Dockerfile", "w") as f:
        f.write(dockerfile)
    new_image_name = args.output_image
    subprocess.run([args.container, "build", "-t", new_image_name, "."], check=True)
    helper.print_color("Successfully built {}".format(
        new_image_name), helper.bcolors.GREEN)


if __name__ == "__main__":
    main()
