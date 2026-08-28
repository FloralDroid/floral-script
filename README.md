# FloralDroid Image Script

This script adds optional packages and translation backends to FloralDroid
without recompiling the entire image.

## Dependencies
- lzip

## Specify input and output images

The base and output image names are required. The generated image inherits any
entrypoint and default arguments configured by the base image, including
Floral's hardware entrypoint.

```bash
python redroid.py \
    -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-magisk \
    -m
```

## Specify container type

Specify container type. Default is docker

option:
```
 -c {docker,podman}, --container {docker,podman}
```


## Specify an Android version

Use `-a` or `--android-version` to select the Android-compatible package
versions. It must match the selected base image. The value can be `8.1.0`,
`9.0.0`, `10.0.0`, `11.0.0`, `12.0.0`, `12.0.0_64only`, `13.0.0` or
`14.0.0`. The default is `11.0.0`.

```bash
# build from a FloralDroid base image
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-custom
```

## Add OpenGapps to FloralDroid image

<img src="./assets/3.png" style="zoom:50%;" />

```bash
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-gapps \
    -g
```

## Add liteGapps to FloralDroid image

```bash
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-litegapps \
    -lg
```

## Add MindTheGapps to FloralDroid image

```bash
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-mindthegapps \
    -mtg
```

## Add ARM translation backends to FloralDroid image
<img src="./assets/2.png" style="zoom:50%;" />

Android 11 uses libndk_translation from the Guybrush Android 11 firmware.
Android 12 uses only the matching 64-bit translator from an Android 12 AVD. Its
ARM64 guest userspace comes from the FloralDroid AOSP build, so the packager
rejects AVD guest libraries, binaries, and linker configuration in the NDK
payload. Install Houdini when 32-bit ARM application support is required. The
packaging script pins and verifies each source separately. NDK installation is
ARM64-only for every supported Android version; the 32-bit path is owned by
Houdini.

libndk seems to have better performance than libhoudini on AMD.

NDK Translation and Houdini can be selected together. The packager stores them
below `/system/floral/ndk` and `/system/floral/houdini`, removes each backend's
private init/binfmt registration, and emits one
`/system/bin/floral_nativebridge_runner` registration layer. NDK uses the AOSP
guest userspace already present in the image; FloralDroid bind-mounts Houdini's
complete private guest sysroot only for Houdini processes. Docker COPY order
therefore cannot replace one backend with the other.

```bash
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-translation \
    -n -i
```

## Add Magisk to FloralDroid image
<img src="./assets/1.png" style="zoom:50%;" />

Zygisk and modules like LSPosed should work. 



```bash
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-magisk \
    -m
```

## Add widevine DRM(L3) to FloralDroid image

![](assets/4.png)

```bash
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-widevine \
    -w
```



## Example

This command will add Gapps, both ARM translation backends, Magisk and Widevine
to the FloralDroid image at the same time.

```bash
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-gapps-translation-magisk-widevine \
    -gmnwi
```

Then start the docker container.

```bash
docker run -itd --rm --privileged \
    -v ~/data:/data \
    -p 5555:5555 \
    floral:12.0.0-gapps-translation-magisk-widevine \
ro.product.cpu.abilist=x86_64,arm64-v8a,x86,armeabi-v7a,armeabi \
    ro.product.cpu.abilist64=x86_64,arm64-v8a \
    ro.product.cpu.abilist32=x86,armeabi-v7a,armeabi \
    ro.dalvik.vm.isa.arm=x86 \
    ro.dalvik.vm.isa.arm64=x86_64 \
    ro.enable.native.bridge.exec=1 \
    ro.vendor.enable.native.bridge.exec=1 \
    ro.vendor.enable.native.bridge.exec64=1 \
    ro.dalvik.vm.native.bridge=libmixbridge.so \
    ro.floral.nativebridge.default_backend=auto \
```

If you need a 64-bit-only FloralDroid image, start the container with the following command.

```bash
docker run -itd --rm --privileged \
    -v ~/data12:/data \
    -p 5555:5555 \
    floral:12.0.0-translation \
    androidboot.use_memfd=1 \
    ro.product.cpu.abilist=x86_64,arm64-v8a \
    ro.product.cpu.abilist64=x86_64,arm64-v8a \
    ro.dalvik.vm.isa.arm64=x86_64 \
    ro.enable.native.bridge.exec=1 \
    ro.dalvik.vm.native.bridge=libmixbridge.so
```

## Troubleshooting

- Magisk installed: N/A

  According to some feedback from WayDroid users, changing the kernel may solve this issue. https://t.me/WayDroid/126202

- The device isn't Play Protect certified
    1. Run below command on host
    ```
    adb root
    adb shell 'sqlite3 /data/data/com.google.android.gsf/databases/gservices.db \
    "select * from main where name = \"android_id\";"'
    ```

    2. Grab device id and register on this website: https://www.google.com/android/uncertified/

- ARM translation doesn't work
  
    Use a FloralDroid image built with the same `-a` Android version as its base
    image. Android 11 and Android 12 use different translation libraries.
    Android 12 NDK Translation is ARM64-only; ARM32 processes use Houdini.


## Credits
1. [remote-android](https://github.com/remote-android)
2. [waydroid_script](https://github.com/casualsnek/waydroid_script)
3. ~~[Magisk Delta](https://huskydg.github.io/magisk-files/)~~
4. [vendor_intel_proprietary_houdini](https://github.com/supremegamers/vendor_intel_proprietary_houdini)
5. [Magisk](https://github.com/topjohnwu/Magisk)
