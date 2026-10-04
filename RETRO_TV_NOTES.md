# Retro TV (smdb/RetroChannelWidget.py) - Status and Open Issues

## Open issues (as of last session)
1. **Stand-by screen/tone is inconsistent.** The "PLEASE STAND BY" screen and its tone do not reliably accompany every visible delay when tuning or switching channels. Requirement: the tone should always play whenever stand-by is shown.
2. **Channel content is inconsistent when switching.** What the guide shows, what plays, and what the banner/label says sometimes disagree after channel up/down.

## Uncommitted state
- Last commit: `c75b56a` (guide NOW/NEXT uses the schedule clock).
- Uncommitted: the stand-by tone was changed from signal-driven to a 150ms poll timer (`standbyPollTimer` / `_syncStandbyTone`), and the `showingStandby` signal plus `_setStandbyConnection`/`_onStandbyChanged` were removed. It passed a headless smoke test but the user reports it still does not work consistently in real use. Decide whether to keep it or revert (`git diff`).

## Architecture summary
- One `ChannelEngine` per genre: a stack of stand-by screen + two `ClipSlot`s (double buffer, `QMediaPlayer` + `QVideoWidget`). The current channel plus 1 neighbour on each side are kept warm (muted).
- `ChannelClock` holds a per-channel wall-clock epoch and a lazily generated rotation; `whatsOnNow()` and `slotInfo()` define the schedule. Clocks persist until `refreshChannels()` rebuilds them.
- Video path resolution runs on `QThreadPool` (`_PathResolveTask`) with request-ID invalidation of stale results.
- Guide overlay reparents the live engine container into the preview frame; non-warmed channels use a throwaway preview clip (`guidePreviewSlot`).
- `StandbyTone` is a `QSoundEffect` looping a generated WAV, all on the GUI thread (no separate thread).

## History of fixes (committed)
- `8b0afca` reuse the live engine widget for the guide preview.
- `eed2176` channel up/down in the guide fully retunes.
- `9f57f6b` watchdog (3s) rebinds the video output if playback position stalls.
- `58aec9e` removed per-toggle video rebinds (guide toggle was slow).
- `c75b56a` guide NOW/NEXT for non-warmed channels uses the clock.

## Hypotheses for the remaining problems (not yet verified)
- Stand-by state: `isShowingStandby()` reads the engine's `QStackedLayout`, but `_tuneTo()` ends with `displayStack.setCurrentWidget(engine.container)` and the guide reparents containers, so the visible state may differ from the engine's internal state. Also `_onSlotReady` fires on duration known, which can precede actual first-frame paint, and `_hardCut`/`_promote` change the stack independently. Consider a single source of truth (e.g. one stand-by overlay owned by the widget, shown until the first frame is confirmed, e.g. via `QMediaPlayer.mediaStatus`/video frame probe) instead of per-engine screens.
- `QSoundEffect` may not restart reliably if `play()` is called while `isPlaying()` is stale; consider always `stop()` then `play()` on transition, or a persistent looping player.
- Channel inconsistency: the engine's `currentRow` is set only after async path resolution, while `_updateNowPlayingLabel`/banner/guide read it immediately after `_tuneTo()`; the candidate-row fallback (`candidateRows(count=5)`) may play a different row than the clock's primary row that the guide shows. Consider having the clock/engine record the resolved row back into the schedule so guide, banner and playback all agree.
- Rapid channel switching: neighbour engines are torn down and recreated per tune, so freshly created engines always start in stand-by and re-resolve; reuse of warmed engines has not been checked for stale `currentRow`/slot state.

## Testing notes
- `QVideoWidget.grab()` always returns black; verify via state, not screenshots.
- Headless smoke tests: use `.venv\Scripts\python.exe`, an ffmpeg-generated clip (`ffmpeg -y -f lavfi -i "testsrc=size=320x240:rate=15:duration=5" -pix_fmt yuv420p clip.mp4`), and fake model/main window objects. A `RuntimeError: wrapped C/C++ object of type QMediaPlayer has been deleted` at interpreter exit is a benign artifact.
- Real-world behaviour (audio, frame rendering) must be confirmed by launching `.venv\Scripts\python.exe -m smdb`.
