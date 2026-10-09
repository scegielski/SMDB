# SMTV DLSS 5 frame worker

The worker adapts the single-pass D3D12/NGX feature-18 pipeline from `nr_video.cpp` in [scegielski/dlss5-nr-player](https://github.com/scegielski/dlss5-nr-player), the project from the Build dlss5-nr-player chat. Adapter-based RTX40/RTX50 selection comes from that player's `nr_runtime.h`. It uses the same core, neural-rendering runtime, and caller helper, with Natural style and one pass.

Build with Visual Studio C++ tools and a Windows SDK:

```bat
smdb\native\build_dlss.bat
```

Keep the locally supplied dependencies in a runtime directory containing:

- `_nvngx.dll`
- `nvngx_dlssnr.dll` (RTX50)
- `runtime40/nvngx_dlssnr.dll` (RTX40)
- `caller/nvngx.dll`

Set `SMDB_DLSS_RUNTIME` to that directory or place it at `smdb/native/runtime`. The local build also locates the existing player under the user's Documents/Codex directory. PyInstaller packages the worker and supplied runtime files when available. Native binaries and proprietary runtime DLLs are ignored by Git; no runtime is downloaded.

The worker receives a 12-byte little-endian header (width, height, flags: bit 0 resets temporal history; bit 1 prepares resources without evaluating a frame) followed by tightly packed RGBA8. Replies contain a four-byte payload length followed by RGBA8, or zero on initialization/evaluation failure. It retains NGX temporal history between frames, recreates resources for resolution changes, and uses aligned upload/readback rows. GPU fences complete before buffers are reused. A separate process isolates runtime crashes; SMTV restores ordinary Qt video on failure or timeout.

The visible video prepares its GPU session in the background while DLSS is off. Toggle-off restores normal rendering but retains the session, so subsequent toggles reuse initialized resources. Resolution changes prepare a new session. Warm-only requests neither display enhanced frames nor count as processed frames. Only the visible video processes frames. Qt keeps audio, seeking, captions, and on-screen displays; enhanced frames fit the original aspect ratio. The queue keeps only the newest waiting frame to prevent accumulated latency. Discontinuous timestamps, seeks, channel changes, and media changes reset temporal history. DLSS starts off on each launch and is controlled with a checkable remote button.

NVIDIA/NGX/DLSS components retain their owners' terms. This integration is independent and is not endorsed by NVIDIA. The supplied RTX40 runtime is the same community Ada runtime used by the existing player.
