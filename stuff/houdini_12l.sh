#!/system/bin/sh
set -eu

# init regenerates these files during bootstrap and APEX activation. Keep
# the generated namespaces and links; add only the Houdini guest paths.
target=${1:?Missing linker configuration directory}
test -f "$target/ld.config.txt"
for config in "$target/ld.config.txt" "$target"/*/ld.config.txt; do
    if [ ! -f "$config" ]; then
        continue
    fi
    sed -i '
/^# Floral Houdini paths$/,/^# End Floral Houdini paths$/d
/^namespace.default.permitted.paths += \/system\/\${LIB}\/bootstrap$/a\
# Floral Houdini paths\
namespace.default.permitted.paths += /system/${LIB}\
namespace.default.permitted.paths += /system/${LIB}/arm\
namespace.default.permitted.paths += /system/${LIB}/arm/nb\
namespace.default.permitted.paths += /system/${LIB}/arm64\
namespace.default.permitted.paths += /system/${LIB}/arm64/nb\
# End Floral Houdini paths
/^namespace.default.asan.permitted.paths += \/system\/\${LIB}\/bootstrap$/a\
# Floral Houdini paths\
namespace.default.asan.permitted.paths += /system/${LIB}\
namespace.default.asan.permitted.paths += /system/${LIB}/arm\
namespace.default.asan.permitted.paths += /system/${LIB}/arm/nb\
namespace.default.asan.permitted.paths += /system/${LIB}/arm64\
namespace.default.asan.permitted.paths += /system/${LIB}/arm64/nb\
# End Floral Houdini paths
/^namespace.sphal.search.paths += \/vendor\/\${LIB}\/hw$/a\
# Floral Houdini paths\
namespace.sphal.search.paths += /system/${LIB}/arm\
namespace.sphal.search.paths += /system/${LIB}/arm/nb\
namespace.sphal.search.paths += /system/${LIB}/arm64\
namespace.sphal.search.paths += /system/${LIB}/arm64/nb\
# End Floral Houdini paths
/^namespace.sphal.permitted.paths += \/system\/vendor\/\${LIB}$/a\
# Floral Houdini paths\
namespace.sphal.permitted.paths += /system/${LIB}/arm\
namespace.sphal.permitted.paths += /system/${LIB}/arm64\
# End Floral Houdini paths
/^namespace.sphal.asan.search.paths += \/vendor\/\${LIB}\/hw$/a\
# Floral Houdini paths\
namespace.sphal.asan.search.paths += /data/asan/system/${LIB}/arm\
namespace.sphal.asan.search.paths += /system/${LIB}/arm\
namespace.sphal.asan.search.paths += /data/asan/system/${LIB}/arm/nb\
namespace.sphal.asan.search.paths += /system/${LIB}/arm/nb\
namespace.sphal.asan.search.paths += /data/asan/system/${LIB}/arm64\
namespace.sphal.asan.search.paths += /system/${LIB}/arm64\
namespace.sphal.asan.search.paths += /data/asan/system/${LIB}/arm64/nb\
namespace.sphal.asan.search.paths += /system/${LIB}/arm64/nb\
# End Floral Houdini paths
/^namespace.sphal.asan.permitted.paths += \/system\/vendor\/\${LIB}$/a\
# Floral Houdini paths\
namespace.sphal.asan.permitted.paths += /data/asan/system/${LIB}/arm\
namespace.sphal.asan.permitted.paths += /system/${LIB}/arm\
namespace.sphal.asan.permitted.paths += /data/asan/system/${LIB}/arm64\
namespace.sphal.asan.permitted.paths += /system/${LIB}/arm64\
# End Floral Houdini paths
' "$config"
done
