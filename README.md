# SMDB

SMDB is a PyQt5 desktop application for browsing and maintaining a local movie library. It keeps your catalogue in a searchable table, pulls rich metadata from online sources, and lets you jump straight to IMDb pages, poster art, and more without leaving the app.

## Features
- Filter, search, and sort large movie collections with a multi-pane Qt interface.
- Pull cast, crew, artwork, and ratings via IMDbPY, TMDb, OMDb, and OpenSubtitles integrations.
- Inspect media details through MediaInfo (bundled `MediaInfo.dll` for Windows builds).
- Maintain watch lists, backup lists, and curated sub-collections (see `smdb/collections/`).
- Package cross-platform executables with the included PyInstaller specs and helper scripts.

## Prebuilt Executables
- Prebuilt binaries are included under `dist/` — no Python install required.
- Windows: `dist/windows/SMDB.exe` — double‑click or run from a terminal.
- Linux: `dist/linux/SMDB` — if needed run `chmod +x SMDB` and then `./SMDB`.
- Notes: Builds are unsigned (Windows SmartScreen may prompt). On Linux, ensure the Qt/XCB libraries from the prerequisites are present.


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
   - Alternatively, activate `.venv` and run `python -m smdb`.
4. On first launch, use `File → Set movies folder` to point SMDB at the directory containing your movie files.
5. Use `Mode → SMTV` for the TV picture and clicker controls, or `Mode → SMDB` to return to the catalogue. In SMTV mode, `FULL`, `F`, or `F11` fills the screen with the video; `Esc` returns to the controls. Press `G` to open the channel guide.

Application settings (window layout, filters, last-selected folders, etc.) are saved through Qt's `QSettings` and reused on subsequent launches.

SMTV channels are available for any genre with at least one included movie. Each channel loops a shuffled lineup of 25 movies (or all available movies in smaller categories), joining the initial broadcast at a random position and playing films to their ends. Scheduled broadcasts represent full films; manual program jumps retain random starts for unvisited films. Pan the guide timeline to see each channel's repeating lineup and scheduled times.
The guide is a horizontally scrollable TV timeline with hourly headings, a live clock, and the current hour highlighted in yellow. Opening the guide or pressing NOW centers the current-time marker in the visible timeline, with earlier programming to its left. The fixed channel lineup repeats in both directions, wrapping from its last film back to its first. Film blocks span the full film runtime, with the initial film beginning before the current time so startup joins it in progress; starts align to quarter hours, with blank padding until the next start. Normal playback waits through that padding after the film ends. Skipping or seeking changes the playing highlight without moving the timeline's blocks or times.
After a skip or seek, a cyan vertical cursor shows the scheduled film start plus elapsed playback seconds, without scaling by catalogue or file runtime; the yellow cursor continues to show real time. Compact yellow and cyan time labels sit above their cursor ticks at the top of the hour blocks, using 12-hour AM/PM times. Both cursor lines extend through the hour headings; the separate clock banner and bottom keyboard-hint line have been removed. The playback cursor updates every second and hides during standby/loading. The guide scrolls horizontally to keep the cyan cursor visible, extending the displayed time range for larger jumps without changing published program times.
Hold the middle mouse button and drag to pan the guide horizontally and vertically; releasing stops movement. SETUP → Guide can switch to browser-style automatic scrolling: middle-click toggles it, moving away from the anchor controls speed, and another click or Esc stops it. The panning preference is saved between launches. Both modes keep your chosen view; NOW or a playback navigation control resumes cursor following. Left-click tunes a channel.
The guide divider starts halfway down and remains draggable. Drag the vertical divider between the video preview and information pane to adjust their widths independently. The information pane shows the movie's local cover beneath its title, with the synopsis wrapping beside and underneath it; missing covers leave the synopsis available.
Use SETUP's Channels and MPAA Ratings tabs to include or exclude channels and movie ratings with checkboxes. Unrated and Unknown ratings have separate choices. Selections are saved for future launches; Setup remains available when all channels are excluded or rating filters leave no eligible movies.
SETUP's Quality Rating tab filters the numeric Rating column shown in SMDB using inclusive minimum and maximum scores from 0 to 10, with three decimal places. Choose whether to include films without a score. These preferences are saved and apply together with channel and MPAA selections.
Use REPROGRAM CHANNEL to pick a fresh random lineup of up to 25 eligible films for the current channel and start its new broadcast. Other channels keep their lineups; smaller categories use all their eligible films in a new order.
Channel lineups and published times are saved automatically in `smtv_schedule.json` beside the primary movie folder's `smdb_data.json`. Restarting rejoins the same continuing broadcast at the current time. Films are identified by folder path rather than catalogue row number. Different eligible-film selections retain separate schedules; changing the eligible collection creates a new lineup. Reprogram Channel replaces and saves the selected channel's schedule. Missing or invalid saved schedules are regenerated.
The guide uses one timeline without tabs or a separate schedule list. A CHANNELS heading, alternating slate channel labels, and stronger borders separate the fixed channel column and hourly headings from movie blocks. Navigating or seeking moves the playing highlight while original scheduled times stay fixed. Reprogram Channel creates a new lineup and its times.
Drag the border at the right edge of the channel names to adjust their column width. The width remains through guide updates and scales with the channel font; it is bounded to keep programming visible.
Use View / Font Size / Increase or Decrease, or Ctrl+wheel in either mode, to adjust the current text size. Both share the same limits and immediately update the menu. Wheel alone scrolls vertically; Setup dialogs retain normal scrolling.
In SMTV, Ctrl+wheel over channel names, guide programming, information/synopsis, or TV controls adjusts that section independently using the original 25-percentage-point steps. Each size persists between launches. The menu adjusts the last section zoomed. Ctrl+wheel over programming keeps the time beneath the pointer stationary until NOW or playback navigation resumes cursor following.
Use NOW between the ten-second arrows to return the selected channel to its live broadcast and recenter the guide on the current hour. This clears the cyan offset marker without changing the lineup or published schedule.
Use the clicker's NEXT and PREV buttons to move between programs on the current channel. These jumps retain the programs' random starting positions and preserve the published guide schedule.
NEXT and PREV resume the position where you left a previously visited film; an unvisited program uses its assigned random start. Pressing PREV again after returning to a film goes to its beginning; NEXT then restores its saved position.
The film controls use two rows: ◀ / ▶ seek back/forward ten seconds. The barred back arrow restarts the currently playing film, preserving its saved position; repeated clicks stay on that same film. The barred forward arrow restores its saved spot from there, or opens the next film at its saved position (at the beginning if unvisited).

## Collections and Metadata
- Text files inside `smdb/collections/` define curated sets such as Noir or Criterion; drop your own lists in the same format to extend the filter menu.
- Movie metadata is cached in `.smdb` JSON files next to your media. Existing files are read with `utilities.readSmdbFile`, and the app supplements missing details by querying online APIs when possible.
- Poster art and artwork caches live under the application's data folders; you can clear them from the UI if artwork becomes stale.

## Building Stand-alone Packages
- `MakeExe.sh` / `MakeExe.bat` wrap PyInstaller to build one-file and one-folder bundles using the specs in `smdb/SMDB-onefile.spec` and `smdb/SMDB-onefolder.spec`.
- Each build prompts you to choose the target layout and opens the platform-specific `dist/<platform>/` output folder when it finishes.
- PyInstaller ships with the default setup because it is listed in `requirements.txt`; you can re-run the helper scripts anytime after `setup.sh`/`setup.bat`.

## Development Notes
- `smdb/__main__.py` hosts the entry point used by `python -m smdb` and the launcher scripts.
- `MainWindow.py` drives the UI, including menus for toggling panes and requesting metadata updates.
- Utility helpers, widgets, and data models live alongside the main window inside the `smdb/` package.
- Requirements are tracked in `requirements.txt`; update it when adding/removing runtime dependencies.

## Troubleshooting
- If Qt fails to start on Linux, rerun `./setup.sh` without `SKIP_APT=1` to ensure the XCB libraries are installed.
- On Windows, confirm that the bundled `MediaInfo.dll` stays next to the executable when distributing a PyInstaller build.

### SMTV subtitles

Use SUBTITLES on the TV controls to turn captions on/off, select an embedded text track, or load an external SRT/VTT file. Nearby files named like the movie (for example `Movie.srt`, `Movie.en.srt`, or `Movie.fr.vtt`) are discovered automatically. The on/off preference persists between launches. Captions follow the actual movie position through seeking, program changes, guide previews, and fullscreen. Video and captions paint together inside the same view; there is no separate floating subtitle window.

Embedded text subtitles use FFmpeg/FFprobe, packaged with the Windows builds when available on the build machine; source runs use tools on PATH. Image-based tracks such as PGS/VobSub are listed but disabled. Text markup is rendered as plain captions.

When subtitles are enabled and a visible SMTV movie has no usable local or embedded captions, SMTV automatically tries the existing OpenSubtitles English-download routine with the configured API key. The video displays `Downloading subtitles...` until the validated SRT is saved beside the movie and loaded. Downloads run in the background; failed attempts report unavailability and are not repeatedly retried during that run.

Right-click the SMTV video pane to use the SMDB movie-list context menu for the displayed film (folder, JSON, IMDb, subtitles, lists, tags, and other movie actions). The database filters and prior selection are preserved when the menu closes.
