#!/usr/bin/env bash
# Builds dist/bb-trainer-<version>-x86_64.AppImage: the trainer with its own Python, GTK 4
# and libadwaita (from conda-forge), so only glibc comes from the system.
#   packaging/build-appimage.sh [version]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-dev}"
BUILD="$ROOT/build"
APPDIR="$BUILD/AppDir"
U="$APPDIR/usr"
TOOLS="$BUILD/tools"
export MAMBA_ROOT_PREFIX="$BUILD/mamba"

rm -rf "$APPDIR"
mkdir -p "$TOOLS" "$ROOT/dist"

if [ ! -x "$TOOLS/bin/micromamba" ]; then
    curl -fsSL https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C "$TOOLS" bin/micromamba
fi
if [ ! -x "$TOOLS/appimagetool" ]; then
    curl -fsSL -o "$TOOLS/appimagetool" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOLS/appimagetool"
fi

echo "== Python, GTK 4 and libadwaita"
"$TOOLS/bin/micromamba" create -y -p "$U" -c conda-forge --override-channels \
    python=3.12 pygobject gtk4 'libadwaita>=1.5' librsvg gdk-pixbuf adwaita-icon-theme
"$TOOLS/bin/micromamba" list -p "$U" | grep -E '^ *(python|pygobject|gtk4|libadwaita|glib) '
# what is bundled, with each package's own license texts (conda-meta is trimmed away below)
mkdir -p "$U/share/licenses"
"$TOOLS/bin/micromamba" list -p "$U" > "$U/share/licenses/packages.txt"
for meta in "$U"/conda-meta/*.json; do
    package="$(basename "$meta" .json)"
    if [ -d "$MAMBA_ROOT_PREFIX/pkgs/$package/info/licenses" ]; then
        cp -r "$MAMBA_ROOT_PREFIX/pkgs/$package/info/licenses" "$U/share/licenses/$package"
    fi
done

echo "== Trim"
rm -rf "$U"/{conda-meta,include,man,ssl,compiler_compat} \
       "$U"/share/{doc,man,info,gtk-doc,gir-1.0,bash-completion,zsh,aclocal,vala,gettext,installed-tests} \
       "$U"/lib/{pkgconfig,cmake} "$U"/share/pkgconfig
find "$U/lib" -maxdepth 1 \( -name '*.a' -o -name '*.la' \) -delete
find "$U/lib" -maxdepth 1 \( -name 'libtcl*' -o -name 'libtk*' -o -name 'tcl8*' -o -name 'tk8*' \) \
    -exec rm -rf {} +
PY="$U/lib/python3.12"
rm -rf "$PY"/{test,idlelib,tkinter,turtledemo,ensurepip,lib2to3,config-3.12-x86_64-linux-gnu} \
       "$PY"/lib-dynload/_tkinter*.so
find "$U" -name __pycache__ -type d -prune -exec rm -rf {} +
find "$U/bin" -mindepth 1 -maxdepth 1 \
    ! -name 'python3*' ! -name 'gdk-pixbuf-query-loaders' ! -name 'glib-compile-schemas' -delete
# translations: only the trainer's languages
find "$U/share/locale" -mindepth 1 -maxdepth 1 ! -name 'pl' ! -name 'en*' -exec rm -rf {} + || true

echo "== Caches"
"$U/bin/glib-compile-schemas" "$U/share/glib-2.0/schemas"
LOADERS="$U/lib/gdk-pixbuf-2.0/2.10.0"
GDK_PIXBUF_MODULEDIR="$LOADERS/loaders" "$U/bin/gdk-pixbuf-query-loaders" \
    | sed "s|$U|@APPDIR_USR@|g" > "$LOADERS/loaders.cache.in"
grep -q svg "$LOADERS/loaders.cache.in" || { echo "no SVG loader for gdk-pixbuf" >&2; exit 1; }

echo "== Trainer"
mkdir -p "$U/share/bb-trainer"
cp "$ROOT"/*.py "$ROOT"/stub.s "$ROOT"/README*.md "$ROOT"/LICENSE "$U/share/bb-trainer/"
install -m 755 "$ROOT/packaging/AppRun" "$APPDIR/AppRun"
cp "$ROOT/packaging/bb-trainer.desktop" "$ROOT/packaging/bb-trainer.svg" "$APPDIR/"
ln -s bb-trainer.svg "$APPDIR/.DirIcon"
mkdir -p "$U/share/applications" "$U/share/icons/hicolor/scalable/apps"
cp "$ROOT/packaging/bb-trainer.desktop" "$U/share/applications/"
cp "$ROOT/packaging/bb-trainer.svg" "$U/share/icons/hicolor/scalable/apps/"

echo "== Check the bundle"
LD_LIBRARY_PATH="$U/lib" GI_TYPELIB_PATH="$U/lib/girepository-1.0" PYTHONNOUSERSITE=1 \
    "$U/bin/python3" -c '
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk
print("GTK", Gtk.get_major_version(), Gtk.get_minor_version(),
      "libadwaita", Adw.get_major_version(), Adw.get_minor_version())
assert (Adw.get_major_version(), Adw.get_minor_version()) >= (1, 5)'

echo "== AppImage"
OUT="$ROOT/dist/bb-trainer-$VERSION-x86_64.AppImage"
rm -f "$OUT"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOLS/appimagetool" --no-appstream "$APPDIR" "$OUT"
ls -lh "$OUT"
