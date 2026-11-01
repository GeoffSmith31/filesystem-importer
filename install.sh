#!/usr/bin/env bash

set -euo pipefail

# Locate the project and packaged application.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist/Filesystem-Importer"
RESOURCE_DIR="$DIST_DIR/_internal/resources"

# Per-user installation locations.
APP_PARENT="$HOME/.local/opt"
APP_DIR="$APP_PARENT/filesystem-importer"
ICON_ROOT="$HOME/.local/share/icons/hicolor"
DESKTOP_DIR="$HOME/.local/share/applications"

# Check that the application has been built.
if [[ ! -x "$DIST_DIR/Filesystem-Importer" ]]; then
    echo "ERROR: Packaged application not found."
    echo "Build it first using PyInstaller."
    exit 1
fi

if [[ ! -d "$RESOURCE_DIR/hicolor" ]]; then
    echo "ERROR: Packaged icon resources not found."
    exit 1
fi

echo "Installing Filesystem Importer..."

# Create the installation directories.
mkdir -p "$APP_PARENT"

# Replace any previous installation.
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"

# Copy the complete PyInstaller application.
cp -a "$DIST_DIR/." "$APP_DIR/"

# Install all available icon sizes.
for ICON_FILE in "$RESOURCE_DIR"/hicolor/*/apps/filesystem-importer.png; do
    [[ -f "$ICON_FILE" ]] || continue

    SIZE_DIR="$(basename "$(dirname "$(dirname "$ICON_FILE")")")"

    install -D -m 644 \
        "$ICON_FILE" \
        "$ICON_ROOT/$SIZE_DIR/apps/filesystem-importer.png"
done

# Create the desktop launcher.
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/filesystem-importer.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Filesystem Importer
Comment=Import photographs into Photo Manager
Exec="$APP_DIR/Filesystem-Importer"
Icon=filesystem-importer
Terminal=false
Categories=Graphics;
StartupWMClass=Filesystem-Importer
EOF

# Refresh the desktop application database, if available.
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR"
fi

echo
echo "Filesystem Importer installed successfully."
echo "Application: $APP_DIR/Filesystem-Importer"
echo "Launcher:    $DESKTOP_DIR/filesystem-importer.desktop"
echo
echo "You can now launch it from the Ubuntu application menu."
