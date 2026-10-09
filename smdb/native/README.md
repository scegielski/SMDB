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

The worker receives a 12-byte little-endian header (width, height, flags: bit 0 resets temporal history; bit 1 prepares resources without evaluating a frame) followed by tightly packed RGBA8. On Windows, bit 2 selects named shared memory: the header is followed by a four-byte ASCII name length and mapping name, with input/output RGBA8 stored in the two halves of that mapping. Only the completion length returns through the pipe in this mode. Replies contain a four-byte payload length followed by RGBA8, or zero on initialization/evaluation failure. It retains NGX temporal history between frames, recreates resources for resolution changes, and uses aligned upload/readback rows. GPU fences complete before buffers are reused. A separate process isolates runtime crashes; SMTV restores ordinary Qt video on failure or timeout.

The visible video prepares its GPU session in the background while DLSS is off. Toggle-off restores normal rendering but retains the session, so subsequent toggles reuse initialized resources. Resolution changes prepare a new session. Warm-only requests neither display enhanced frames nor count as processed frames. Only the visible video processes frames. Qt keeps audio, seeking, captions, and on-screen displays; enhanced frames fit the original aspect ratio. The queue keeps only the newest waiting frame to prevent accumulated latency. Discontinuous timestamps, seeks, channel changes, and media changes reset temporal history. DLSS starts off on each launch and is controlled with a checkable remote button.

NVIDIA/NGX/DLSS components retain their owners' terms. This integration is independent and is not endorsed by NVIDIA. The supplied RTX40 runtime is the same community Ada runtime used by the existing player.

Frame conversion uses exact lookup tables and reused native buffers. Incoming decoded frames are retained without conversion while the worker is busy; the latest frame is converted on completion. This avoids converting discarded frames and keeps playback latency bounded.

Intensity matches the original player: a 0–200% blend of original and enhanced pixels, with 100% as the default. NR evaluation parameters remain unchanged. Protocol bit 3 adds a four-byte unsigned intensity percentage immediately after the header, before the mapping name or frame payload. Zero reproduces original RGBA8; the CPU blend uses precomputed fixed-point contributions and clamps the final result.

## GPU presentation

The default Windows path now follows `nr_player.cpp`: GPU conversion to FP16, NGX evaluation, GPU intensity blending, and GPU presentation. Qt still supplies decoded RGBA8 input and manages audio, seeking, subtitles, and overlays. Enhanced output is never read back to CPU memory or converted into a QPixmap.

Protocol bit 4 selects GPU output with named shared-memory input. The worker publishes a named D3D12 RGBA8 texture (`mapping-name-gpu`) and acknowledges completion after its fence. `dlss_interop.dll` opens it through D3D11, copies the completed frame into a GPU texture registered with WGL_NV_DX_interop2, and exposes that texture to a composited QOpenGLWidget. Copies occur only on completed-frame notifications; ordinary repaints use the cached GPU texture. OpenGL consumption completes before the next worker request. The build script compiles both the worker and interop DLL, and PyInstaller includes both.

Unsupported OpenGL interop automatically falls back to the original CPU presentation path while keeping DLSS enabled. On the same visible 960x540 view with a 1920x1080 60fps clip, GPU presentation displayed approximately 45 enhanced fps versus 20 with CPU presentation. This is a local measurement, not a guarantee of 60fps or complete decoder parity with the standalone player. Hardware checks cover orientation, captions/OSD, paused seeking, fullscreen transitions, resolution changes, toggle-off, and fallback.
