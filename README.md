# Remote-Android Script

This script adds Gapps, Magisk and libndk to redroid **without recompiling the entire image**
If redroid-script doesn't work, please create an issue

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

Upstream ReDroid images remain supported when selected explicitly:

```bash
python redroid.py \
    -a 12.0.0 \
    -b redroid/redroid:12.0.0-latest \
    -o redroid/redroid:12.0.0-custom
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
# pull the latest image
python redroid.py -a 11.0.0 \
    -b redroid/redroid:11.0.0-latest \
    -o redroid/redroid:11.0.0-custom
```

## Add OpenGapps to ReDroid image

<img src="./assets/3.png" style="zoom:50%;" />

```bash
python redroid.py -a 11.0.0 \
    -b redroid/redroid:11.0.0-latest \
    -o redroid/redroid:11.0.0-gapps \
    -g
```

## Add liteGapps to ReDroid image

```bash
python redroid.py -a 11.0.0 \
    -b redroid/redroid:11.0.0-latest \
    -o redroid/redroid:11.0.0-litegapps \
    -lg
```

## Add MindTheGapps to ReDroid image

```bash
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-mindthegapps \
    -mtg
```

## Add libndk arm translation to ReDroid image
<img src="./assets/2.png" style="zoom:50%;" />

Android 11 uses libndk_translation from the Guybrush Android 11 firmware.
Android 12 uses only the matching 64-bit translator and guest libraries from an
Android 12 AVD. The Android 12 32-bit translator is excluded because this bundle
does not provide a matching Android 12 32-bit guest image; install Houdini when
32-bit ARM application support is required. The packaging script pins and
verifies each source separately. NDK installation is ARM64-only for every
supported Android version; the 32-bit path is owned by Houdini.

libndk seems to have better performance than libhoudini on AMD.

NDK and Houdini can be selected together. Their payloads retain the upstream
`/system/lib*` layout because the guest runtimes use those paths internally.
The packager removes each backend's private init/binfmt registration and emits
one `/system/bin/floral_nativebridge_runner` registration layer, so Docker COPY
order cannot replace one backend with the other.

```bash
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-ndk \
    -n
```

## Add Magisk to ReDroid image
<img src="./assets/1.png" style="zoom:50%;" />

Zygisk and modules like LSPosed should work. 



```bash
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-magisk \
    -m
```

## Add widevine DRM(L3) to ReDroid image

![](assets/4.png)

```bash
python redroid.py -a 12.0.0 \
    -b floral:12.0.0 \
    -o floral:12.0.0-widevine \
    -w
```



## Example

This command will add Gapps, Magisk, Libndk, Widevine to the ReDroid image at the same time.

```bash
python redroid.py -a 11.0.0 \
    -b redroid/redroid:11.0.0-latest \
    -o redroid/redroid:11.0.0-gapps-ndk-magisk-widevine \
    -gmnw
```

Then start the docker container.

```bash
docker run -itd --rm --privileged \
    -v ~/data:/data \
    -p 5555:5555 \
    redroid/redroid:11.0.0-gapps-ndk-magisk-widevine \
ro.product.cpu.abilist=x86_64,arm64-v8a,x86,armeabi-v7a,armeabi \
    ro.product.cpu.abilist64=x86_64,arm64-v8a \
    ro.product.cpu.abilist32=x86,armeabi-v7a,armeabi \
    ro.dalvik.vm.isa.arm=x86 \
    ro.dalvik.vm.isa.arm64=x86_64 \
    ro.enable.native.bridge.exec=1 \
    ro.vendor.enable.native.bridge.exec=1 \
    ro.vendor.enable.native.bridge.exec64=1 \
    ro.dalvik.vm.native.bridge=libndk_translation.so \
    ro.ndk_translation.version=0.2.3 \
```

If you need to use libndk on `redroid:12.0.0_64only` image, you should start the container with the following command

```bash
docker run -itd --rm --privileged \
    -v ~/data12:/data \
    -p 5555:5555 \
    redroid/redroid:12.0.0_64only-ndk \
    androidboot.use_memfd=1 \
    ro.product.cpu.abilist=x86_64,arm64-v8a \
    ro.product.cpu.abilist64=x86_64,arm64-v8a \
    ro.dalvik.vm.isa.arm64=x86_64 \
    ro.enable.native.bridge.exec=1 \
    ro.dalvik.vm.native.bridge=libndk_translation.so
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

- libndk doesn't work
  
    Use an image built with the same `-a` Android version as its base image.
    Android 11 and Android 12 use different translation libraries. Turning on
    Zygisk may still break libndk for 32-bit apps, while ARM64 apps can continue
    to work.
    
- libhoudini doesn't work
  
    I have no idea. I can't get any version of libhoudini to work on redroid.


## Credits
1. [remote-android](https://github.com/remote-android)
2. [waydroid_script](https://github.com/casualsnek/waydroid_script)
3. ~~[Magisk Delta](https://huskydg.github.io/magisk-files/)~~
4. [vendor_intel_proprietary_houdini](https://github.com/supremegamers/vendor_intel_proprietary_houdini)
5. [Magisk](https://github.com/topjohnwu/Magisk)
