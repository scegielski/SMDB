# SMDB

SMDB is a PyQt5 desktop application for browsing and maintaining a local movie library. It keeps your catalogue in a searchable table, pulls rich metadata from online sources, and lets you jump straight to IMDb pages, poster art, and more without leaving the app.

## Features
- Filter, search, and sort large movie collections with a multi-pane Qt interface.
- Pull cast, crew, artwork, and ratings via IMDbPY, TMDb, OMDb, and OpenSubtitles integrations.
- Inspect media details through MediaInfo (bundled `MediaInfo.dll` for Windows builds).
- Maintain watch lists, backup lists, and curated sub-collections (see `src/collections/`).
- Package cross-platform executables with the included PyInstaller specs and helper scripts.

## Prerequisites
- Python 3.9+ (Python 3.11 works well on all supported platforms).
- `pip` (installed automatically inside the virtual environment).
- On Linux, the Qt/XCB support libraries listed in `setup.sh` (installed automatically when `apt-get` is available).
- Internet access for metadata enrichment (IMDB, TMDb, OMDb, OpenSubtitles).

## Quick Start
1. Clone the repository and move into its root.
2. Create the virtual environment and install dependencies:
   - POSIX shells: `./setup.sh`
   - Windows (CMD/PowerShell): `setup.bat`
   - When the setup script finishes it can immediately invoke the PyInstaller helper (`MakeExe.sh` / `MakeExe.bat`) to produce stand-alone builds; choose that option if you need distributable executables right away.
3. Launch the app from the project root:
   - POSIX shells: `./SMDB.sh`
   - Windows: `SMDB.bat`
   - Alternatively, activate `.venv` and run `python -m src`.
4. On first launch, use `File → Set movies folder` to point SMDB at the directory containing your movie files.

Application settings (window layout, filters, last-selected folders, etc.) are saved through Qt's `QSettings` and reused on subsequent launches.

## Collections and Metadata
- Text files inside `src/collections/` define curated sets such as Noir or Criterion; drop your own lists in the same format to extend the filter menu.
- Movie metadata is cached in `.smdb` JSON files next to your media. Existing files are read with `utilities.readSmdbFile`, and the app supplements missing details by querying online APIs when possible.
- Poster art and artwork caches live under the application's data folders; you can clear them from the UI if artwork becomes stale.

## Building Stand-alone Packages
- `MakeExe.sh` / `MakeExe.bat` wrap PyInstaller to build one-file and one-folder bundles using the specs in `src/SMDB-onefile.spec` and `src/SMDB-onefolder.spec`.
- Each build prompts you to choose the target layout and opens the `dist/` output folder when it finishes.
- PyInstaller ships with the default setup because it is listed in `requirements.txt`; you can re-run the helper scripts anytime after `setup.sh`/`setup.bat`.

## Development Notes
- `src/__main__.py` hosts the entry point used by `python -m src` and the launcher scripts.
- `MainWindow.py` drives the UI, including menus for toggling panes and requesting metadata updates.
- Utility helpers, widgets, and data models live alongside the main window inside the `src/` package.
- Requirements are tracked in `requirements.txt`; update it when adding/removing runtime dependencies.

## Troubleshooting
- If Qt fails to start on Linux, rerun `./setup.sh` without `SKIP_APT=1` to ensure the XCB libraries are installed.
- On Windows, confirm that the bundled `MediaInfo.dll` stays next to the executable when distributing a PyInstaller build.
