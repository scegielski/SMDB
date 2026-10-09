// SMTV single-pass frame worker, adapted from scegielski/dlss5-nr-player nr_video.cpp.
// nr_video.cpp - DLSS 5 Neural Rendering video frame pipeline.
// Feeds a sequence of PNG frames through nvngx_dlssnr.dll (the same runtime
// NR-Media-UI's CLI uses) keeping ONE NGX session alive across frames, so
// temporal history (reset=0) is preserved exactly like in games.
//
// Usage: nr_video.exe in_dir out_dir [--style natural|cinematic|default|0..6]
//                                  [--preset 0..3] [--intensity 0..2]
//                                  [--tone 0..2] [--structure 0..2]
//                                  [--skin -1..2] [--mask 0|1]
// Reads in_dir/*.png sorted, writes out_dir/frame_%05d.png
//
// Build (MSVC, Hostx64):
//   cl /nologo /EHsc /O2 /MT nr_video.cpp /link /OUT:nr_video.exe
//      d3d12.lib dxgi.lib windowscodecs.lib ole32.lib

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#ifndef NVSDK_CONV
#define NVSDK_CONV __cdecl
#endif
#include <windows.h>
#include <d3d11.h>
#include <d3d12.h>
#include <dxgi1_4.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <string>
#include <vector>
#include <algorithm>
#include <io.h>
#include <fcntl.h>
#include "nr_runtime.h"

using Microsoft::WRL::ComPtr;

// ---------------------------------------------------------------------------
// NGX interface (declared inline, mirrors NVIDIA's vtable layout)
// ---------------------------------------------------------------------------
typedef int NVSDK_NGX_Result;
static const NVSDK_NGX_Result NGX_SUCCESS = 1;

struct NVSDK_NGX_Handle { unsigned int Id; };

struct NVSDK_NGX_Parameter
{
    virtual void Set(const char *InName, unsigned long long InValue) = 0;
    virtual void Set(const char *InName, float InValue) = 0;
    virtual void Set(const char *InName, double InValue) = 0;
    virtual void Set(const char *InName, unsigned int InValue) = 0;
    virtual void Set(const char *InName, int InValue) = 0;
    virtual void Set(const char *InName, ID3D11Resource *InValue) = 0;
    virtual void Set(const char *InName, ID3D12Resource *InValue) = 0;
    virtual void Set(const char *InName, void *InValue) = 0;
    virtual NVSDK_NGX_Result Get(const char *InName, unsigned long long *OutValue) const = 0;
    virtual NVSDK_NGX_Result Get(const char *InName, float *OutValue) const = 0;
    virtual NVSDK_NGX_Result Get(const char *InName, double *OutValue) const = 0;
    virtual NVSDK_NGX_Result Get(const char *InName, unsigned int *OutValue) const = 0;
    virtual NVSDK_NGX_Result Get(const char *InName, int *OutValue) const = 0;
    virtual NVSDK_NGX_Result Get(const char *InName, ID3D11Resource **OutValue) const = 0;
    virtual NVSDK_NGX_Result Get(const char *InName, ID3D12Resource **OutValue) const = 0;
    virtual NVSDK_NGX_Result Get(const char *InName, void **OutValue) const = 0;
    virtual void Reset() = 0;
};

typedef struct NVSDK_NGX_PathListInfo
{
    wchar_t const *const *Path;
    unsigned int Length;
} NVSDK_NGX_PathListInfo;

typedef enum NVSDK_NGX_Logging_Level
{
    NVSDK_NGX_LOGGING_LEVEL_OFF = 0,
    NVSDK_NGX_LOGGING_LEVEL_ON,
    NVSDK_NGX_LOGGING_LEVEL_VERBOSE,
} NVSDK_NGX_Logging_Level;

typedef void(NVSDK_CONV *NVSDK_NGX_AppLogCallback)(const char *message,
                                                   NVSDK_NGX_Logging_Level loggingLevel,
                                                   int sourceComponent);

typedef struct NVSDK_NGX_LoggingInfo
{
    NVSDK_NGX_Logging_Level LoggingLevel;
    NVSDK_NGX_AppLogCallback Callback;
    void *UserData;
    bool DisableOtherLoggingSinks;
} NVSDK_NGX_LoggingInfo;

typedef struct NVSDK_NGX_FeatureCommonInfo_Internal NVSDK_NGX_FeatureCommonInfo_Internal;

typedef struct NVSDK_NGX_FeatureCommonInfo
{
    NVSDK_NGX_PathListInfo PathListInfo;
    NVSDK_NGX_FeatureCommonInfo_Internal *InternalData;
    NVSDK_NGX_LoggingInfo LoggingInfo;
} NVSDK_NGX_FeatureCommonInfo;

typedef NVSDK_NGX_Result (*PFN_Init)(unsigned long long, const wchar_t *, ID3D12Device *,
                                     const void *, int);
typedef NVSDK_NGX_Result (*PFN_Init_Ext)(unsigned long long, const wchar_t *, ID3D12Device *,
                                         int, const void *);
// Snippet-build Init_Ext: (app, path, device, FeatureCommonInfo*, version)
typedef NVSDK_NGX_Result (*PFN_Init_Ext_Snippet)(unsigned long long, const wchar_t *,
                                                 ID3D12Device *, const void *, int);
// Core Init_ProjectID (arg order from bridge's disassembly):
//   (projectId, engineType, engineVersion, dataPath, device, version, FCI)
typedef NVSDK_NGX_Result (*PFN_Init_ProjectID)(const char *, int, const char *,
                                               const wchar_t *, ID3D12Device *, int,
                                               const void *);
// The caller shim (caller\nvngx.dll) wraps the snippet's entry points so the
// return address lands inside the shim -- the snippet validates its caller and
// refuses direct calls with 0xBAD00002 (PlatformError). Each wrapper takes the
// real function pointer first and forwards the remaining args.
typedef NVSDK_NGX_Result (*PFN_ShimInit)(void *, unsigned long long, const wchar_t *,
                                         ID3D12Device *, int, const void *);
typedef NVSDK_NGX_Result (*PFN_ShimCreate)(void *, ID3D12GraphicsCommandList *, int,
                                           NVSDK_NGX_Parameter *, NVSDK_NGX_Handle **);
typedef NVSDK_NGX_Result (*PFN_ShimEvaluate)(void *, ID3D12GraphicsCommandList *,
                                             const NVSDK_NGX_Handle *,
                                             const NVSDK_NGX_Parameter *, void *);
typedef NVSDK_NGX_Result (*PFN_ShimRelease)(void *, NVSDK_NGX_Handle *);
typedef NVSDK_NGX_Result (*PFN_ShimShutdown)(void *);
typedef NVSDK_NGX_Result (*PFN_AllocateParameters)(NVSDK_NGX_Parameter **);
typedef NVSDK_NGX_Result (*PFN_D3D12CreateFeature)(ID3D12GraphicsCommandList *, int,
                                                   NVSDK_NGX_Parameter *, NVSDK_NGX_Handle **);
typedef NVSDK_NGX_Result (*PFN_D3D12EvaluateFeature)(ID3D12GraphicsCommandList *,
                                                     const NVSDK_NGX_Handle *,
                                                     const NVSDK_NGX_Parameter *, void *);
typedef NVSDK_NGX_Result (*PFN_D3D12ReleaseFeature)(NVSDK_NGX_Handle *);
typedef NVSDK_NGX_Result (*PFN_Shutdown)(void);

// DLSS 5 Neural Rendering feature id. renodx logs "feature 18 created via the
// signed snippet" -- 18 is the NR feature id it creates after DLSS/DLAA.
static const int NR_FEATURE_ID = 18;

// ---------------------------------------------------------------------------
// globals
// ---------------------------------------------------------------------------
static PFN_Init_Ext            g_direct_init;
static PFN_Init_Ext            g_init_ext;
static PFN_Init_ProjectID      g_init_projectid;
static PFN_AllocateParameters  g_alloc;
static PFN_D3D12CreateFeature  g_create;
static PFN_D3D12EvaluateFeature g_eval;
static PFN_D3D12ReleaseFeature g_release;
static PFN_Shutdown            g_shutdown;
static PFN_D3D12CreateFeature  g_nr_create;
static PFN_D3D12EvaluateFeature g_nr_eval;
static PFN_D3D12ReleaseFeature g_nr_release;
static PFN_ShimInit            g_shim_init;
static PFN_ShimCreate          g_shim_create;
static PFN_ShimEvaluate        g_shim_eval;
static PFN_ShimRelease         g_shim_release;
static PFN_ShimShutdown        g_shim_shutdown;

static ComPtr<ID3D12Device>             g_dev;
static ComPtr<ID3D12CommandQueue>       g_queue;
static ComPtr<ID3D12CommandAllocator>   g_alloc0;
static ComPtr<ID3D12GraphicsCommandList> g_list;
static ComPtr<ID3D12Fence>              g_fence;
static UINT64                           g_fence_value = 0;

static NVSDK_NGX_Parameter *g_params = nullptr;
static NVSDK_NGX_Handle    *g_feature = nullptr;

// ---------------------------------------------------------------------------
// logging
// ---------------------------------------------------------------------------
static void Log(const char *fmt, ...)
{
    va_list ap; va_start(ap, fmt);
    vfprintf(stderr, fmt, ap); fprintf(stderr, "\n");
    va_end(ap);
}

// ---------------------------------------------------------------------------
// D3D12 setup
// ---------------------------------------------------------------------------
static int g_gpu_index = -1;   // -1 = auto (first hardware adapter)
static NRRuntime g_runtime = NRRuntime::Unsupported;
static int g_gpu_vendor = 0;   // 0x10DE = NVIDIA only

static ComPtr<ID3D12Device> CreateDevice()
{
    ComPtr<IDXGIFactory4> factory;
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory)))) return nullptr;

    // Enumerate all hardware adapters once, log them, then pick the requested one.
    struct Ad { ComPtr<IDXGIAdapter1> a; DXGI_ADAPTER_DESC1 d; };
    std::vector<Ad> hw;
    ComPtr<IDXGIAdapter1> it;
    for (UINT i = 0; factory->EnumAdapters1(i, &it) != DXGI_ERROR_NOT_FOUND; ++i)
    {
        DXGI_ADAPTER_DESC1 desc = {};
        it->GetDesc1(&desc);
        if (desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) { it.Reset(); continue; }
        Ad e; e.a = it; e.d = desc;
        hw.push_back(e);
        it.Reset();
    }
    for (size_t k = 0; k < hw.size(); ++k)
        Log("GPU[%zu]: %ls (vendor=0x%04X vid=%u, VRAM=%llu MB)",
            k, hw[k].d.Description, (unsigned)hw[k].d.VendorId, hw[k].d.DeviceId,
            (unsigned long long)(hw[k].d.DedicatedVideoMemory >> 20));

    int sel = (g_gpu_index >= 0) ? g_gpu_index : 0;
    // If the user asked for a specific name, match by substring first.
    if (g_gpu_index < 0) { for (size_t k=0;k<hw.size();++k) if (RuntimeForAdapter(hw[k].d.VendorId, hw[k].d.Description) != NRRuntime::Unsupported) { sel=(int)k; break; } }
    for (size_t k = 0; k < hw.size(); ++k)
    {
        if ((int)k != sel) continue;
        ComPtr<ID3D12Device> dev;
        if (SUCCEEDED(D3D12CreateDevice(hw[k].a.Get(), D3D_FEATURE_LEVEL_12_0,
                                        IID_PPV_ARGS(&dev))))
        {
            g_runtime = RuntimeForAdapter(hw[k].d.VendorId, hw[k].d.Description);
            Log("using adapter: %ls", hw[k].d.Description);
            return dev;
        }
        Log("FAIL: D3D12CreateDevice on GPU[%zu] %ls", k, hw[k].d.Description);
    }
    return nullptr;
}

static bool SetupD3D12()
{
    g_dev = CreateDevice();
    if (!g_dev) { Log("FAIL: no D3D12 device"); return false; }

    D3D12_COMMAND_QUEUE_DESC qd = {};
    qd.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
    if (FAILED(g_dev->CreateCommandQueue(&qd, IID_PPV_ARGS(&g_queue))))
        { Log("FAIL: CreateCommandQueue"); return false; }
    if (FAILED(g_dev->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT,
                                             IID_PPV_ARGS(&g_alloc0))))
        { Log("FAIL: CreateCommandAllocator"); return false; }
    if (FAILED(g_dev->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT,
                                        g_alloc0.Get(), nullptr,
                                        IID_PPV_ARGS(&g_list))))
        { Log("FAIL: CreateCommandList"); return false; }
    if (FAILED(g_dev->CreateFence(0, D3D12_FENCE_FLAG_NONE,
                                  IID_PPV_ARGS(&g_fence))))
        { Log("FAIL: CreateFence"); return false; }
    return true;
}

static bool ExecuteAndWait()
{
    if(FAILED(g_list->Close())) return false;
    g_queue->ExecuteCommandLists(1, (ID3D12CommandList *const *)g_list.GetAddressOf());
    ++g_fence_value;
    if(FAILED(g_queue->Signal(g_fence.Get(), g_fence_value))) return false;
    if(g_fence->GetCompletedValue() < g_fence_value) {
        HANDLE ev=CreateEventW(nullptr,FALSE,FALSE,nullptr);
        if(!ev) return false;
        if(FAILED(g_fence->SetEventOnCompletion(g_fence_value,ev))) { CloseHandle(ev); return false; }
        DWORD status=WaitForSingleObject(ev,10000);
        CloseHandle(ev);
        if(status!=WAIT_OBJECT_0) { Log("GPU fence timed out"); return false; }
    }
    if(FAILED(g_alloc0->Reset())) return false;
    return SUCCEEDED(g_list->Reset(g_alloc0.Get(),nullptr));
}

// ---------------------------------------------------------------------------
// texture helpers
// ---------------------------------------------------------------------------
static ComPtr<ID3D12Resource> CreateTex2D(UINT w, UINT h, DXGI_FORMAT fmt,
                                          D3D12_RESOURCE_STATES init,
                                          D3D12_RESOURCE_FLAGS flags)
{
    D3D12_RESOURCE_DESC d = {};
    d.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
    d.Width = w; d.Height = h; d.DepthOrArraySize = 1;
    d.MipLevels = 1; d.Format = fmt; d.SampleDesc.Count = 1;
    d.Flags = flags;
    D3D12_HEAP_PROPERTIES hp = {};
    hp.Type = D3D12_HEAP_TYPE_DEFAULT;
    ComPtr<ID3D12Resource> r;
    if (FAILED(g_dev->CreateCommittedResource(&hp, D3D12_HEAP_FLAG_NONE, &d, init,
                                              nullptr, IID_PPV_ARGS(&r))))
        return nullptr;
    return r;
}

// ---------------------------------------------------------------------------
static D3D12_RESOURCE_BARRIER TransitionBarrier(ID3D12Resource *res,
                                                 D3D12_RESOURCE_STATES before,
                                                 D3D12_RESOURCE_STATES after)
{
    D3D12_RESOURCE_BARRIER b = {};
    b.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    b.Transition.pResource = res;
    b.Transition.StateBefore = before;
    b.Transition.StateAfter = after;
    return b;
}

// R16G16B16A16_FLOAT stores IEEE half-floats, not UNORM. The CLI converts
// RGBA8 -> /255 -> [0,1] float -> half. These helpers do the bit conversion.
static uint16_t FloatToHalf(float f)
{
    uint32_t x; memcpy(&x, &f, 4);
    uint32_t s = (x >> 16) & 0x8000u;
    int32_t  e = (int32_t)((x >> 23) & 0xff) - 127 + 15;
    uint32_t m = x & 0x7fffffu;
    if (e <= 0) { if (e < -10) return (uint16_t)s; m = (m | 0x800000u) >> (1 - e); return (uint16_t)(s | (m >> 13)); }
    if (e >= 31) return (uint16_t)(s | 0x7c00u);
    return (uint16_t)(s | ((uint32_t)e << 10) | (m >> 13));
}
static float HalfToFloat(uint16_t h)
{
    uint32_t s = (h >> 15) & 1;
    uint32_t e = (h >> 10) & 0x1f;
    uint32_t m = h & 0x3ff;
    uint32_t x;
    if (e == 0) { if (m == 0) x = s << 31; else { e = 1; while (!(m & 0x400)) { m <<= 1; --e; } m &= 0x3ff; x = (s << 31) | ((e + 112) << 23) | (m << 13); } }
    else if (e == 0x1f) x = (s << 31) | 0x7f800000u | (m << 13);
    else x = (s << 31) | ((e + 112) << 23) | (m << 13);
    float f; memcpy(&f, &x, 4); return f;
}

// ---------------------------------------------------------------------------

static std::wstring g_base;
static HMODULE g_core=nullptr, g_nr=nullptr, g_shim=nullptr;
static ComPtr<ID3D12Resource> g_color, g_output, g_upload, g_readback;
static UINT g_width=0, g_height=0, g_pitch=0;
static void Cleanup() {
    if(g_feature) { if(g_shim_release) g_shim_release((void*)g_nr_release,g_feature); else if(g_release) g_release(g_feature); }
    g_feature=nullptr;
    if(g_params && g_core) { auto destroy=(NVSDK_NGX_Result (*)(NVSDK_NGX_Parameter*))GetProcAddress(g_core,"NVSDK_NGX_D3D12_DestroyParameters"); if(destroy) destroy(g_params); }
    g_params=nullptr;
    if(g_shutdown) g_shutdown();
    g_color.Reset();g_output.Reset();g_upload.Reset();g_readback.Reset();
    g_list.Reset();g_alloc0.Reset();g_queue.Reset();g_fence.Reset();g_dev.Reset();
    g_fence_value=0;g_width=g_height=0;
}
static bool Initialize(UINT w, UINT h) {
    if(!SetupD3D12() || g_runtime==NRRuntime::Unsupported) return false;
    const std::string style="natural";
    const int preset=3,intensity=1,tone=1,structure=1,skin=-1,mask=0;
    const DXGI_FORMAT fmt = DXGI_FORMAT_R16G16B16A16_FLOAT; // as the CLI
    auto color = CreateTex2D(w, h, fmt, D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE,
                             D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS);
    // The NR feature writes the output as a UAV: the CLI logs
    // "Color=NON_PIXEL_SHADER_RESOURCE Output=UNORDERED_ACCESS".
    auto output = CreateTex2D(w, h, fmt, D3D12_RESOURCE_STATE_UNORDERED_ACCESS,
                              D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS);
    if (!color || !output) { Log("FAIL: create textures"); return false; }

    // Persistent upload heap + readback for the color texture.
    UINT row_pitch = (w * 8 + 255) & ~255u; // 256-byte aligned row pitch
    UINT64 total = (UINT64)row_pitch * h;
    D3D12_RESOURCE_DESC ubd = {};
    ubd.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
    ubd.Alignment = D3D12_DEFAULT_RESOURCE_PLACEMENT_ALIGNMENT;
    ubd.Width = total; ubd.Height = 1; ubd.DepthOrArraySize = 1;
    ubd.MipLevels = 1; ubd.SampleDesc.Count = 1;
    ubd.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    D3D12_HEAP_PROPERTIES uhp = {};
    uhp.Type = D3D12_HEAP_TYPE_UPLOAD;
    ComPtr<ID3D12Resource> upload;
    if (FAILED(g_dev->CreateCommittedResource(&uhp, D3D12_HEAP_FLAG_NONE, &ubd,
                                              D3D12_RESOURCE_STATE_GENERIC_READ,
                                              nullptr, IID_PPV_ARGS(&upload))))
        { Log("FAIL: upload heap"); return false; }

    D3D12_HEAP_PROPERTIES rhp = {};
    rhp.Type = D3D12_HEAP_TYPE_READBACK;
    ComPtr<ID3D12Resource> readback;
    if (FAILED(g_dev->CreateCommittedResource(&rhp, D3D12_HEAP_FLAG_NONE, &ubd,
                                              D3D12_RESOURCE_STATE_COPY_DEST,
                                              nullptr, IID_PPV_ARGS(&readback))))
        { Log("FAIL: readback heap"); return false; }

    // NGX init: load the driver's NGX core (_nvngx.dll), which has the full
    // export set including AllocateParameters. nvngx_dlssnr.dll (the NR model)
    // must sit next to this exe; NGX finds it by name.
    HMODULE ngx = (g_core ? g_core : (g_core = LoadLibraryW((g_base + L"\\_nvngx.dll").c_str())));
    if (!ngx) { Log("FAIL: cannot load _nvngx.dll (driver NGX core)"); return false; }
    g_init_ext = (PFN_Init_Ext)GetProcAddress(ngx, "NVSDK_NGX_D3D12_Init_Ext");
    g_init_projectid = (PFN_Init_ProjectID)GetProcAddress(ngx, "NVSDK_NGX_D3D12_Init_ProjectID");
    g_alloc    = (PFN_AllocateParameters)GetProcAddress(ngx, "NVSDK_NGX_D3D12_AllocateParameters");
    g_create   = (PFN_D3D12CreateFeature)GetProcAddress(ngx, "NVSDK_NGX_D3D12_CreateFeature");
    g_eval     = (PFN_D3D12EvaluateFeature)GetProcAddress(ngx, "NVSDK_NGX_D3D12_EvaluateFeature");
    g_release  = (PFN_D3D12ReleaseFeature)GetProcAddress(ngx, "NVSDK_NGX_D3D12_ReleaseFeature");

    // The NR snippet must be loaded so the core sees it as an NGX layer
    // (renodx LoadLibrary's it; bridge logs it as "NGX layer 0"). The CLI
    // creates the NR feature "direct" -- through the snippet's own export,
    // after the core session (and its DLSS feature) is up.
    HMODULE nr = (g_nr ? g_nr : (g_nr = LoadLibraryW((g_base + L"\\" + RuntimeRelativePath(g_runtime)).c_str())));
    if (!nr) { Log("FAIL: cannot load nvngx_dlssnr.dll (NR runtime)"); return false; }
    g_direct_init = (PFN_Init_Ext)GetProcAddress(nr, "NVSDK_NGX_D3D12_Init_Ext");
    g_nr_create   = (PFN_D3D12CreateFeature)GetProcAddress(nr, "NVSDK_NGX_D3D12_CreateFeature");
    g_nr_eval     = (PFN_D3D12EvaluateFeature)GetProcAddress(nr, "NVSDK_NGX_D3D12_EvaluateFeature");
    g_nr_release  = (PFN_D3D12ReleaseFeature)GetProcAddress(nr, "NVSDK_NGX_D3D12_ReleaseFeature");
    g_shutdown = (PFN_Shutdown)GetProcAddress(ngx, "NVSDK_NGX_D3D12_Shutdown");
    if (!g_init_ext || !g_alloc || !g_create || !g_eval || !g_release || !g_shutdown)
    { Log("FAIL: NGX entry points missing (init=%p alloc=%p create=%p eval=%p rel=%p shut=%p)",
          g_init_ext, g_alloc, g_create, g_eval, g_release, g_shutdown); return false; }

    // The caller shim wraps the snippet's entry points so the snippet's caller
    // validation passes (return address lands inside the shim). Load it and
    // wire the wrappers to the snippet's exports.
    HMODULE shim = (g_shim ? g_shim : (g_shim = LoadLibraryW((g_base + L"\\caller\\nvngx.dll").c_str())));
    if (shim)
    {
        g_shim_init     = (PFN_ShimInit)GetProcAddress(shim, "DLSSNR_CallInit");
        g_shim_create   = (PFN_ShimCreate)GetProcAddress(shim, "DLSSNR_CallCreate");
        g_shim_eval     = (PFN_ShimEvaluate)GetProcAddress(shim, "DLSSNR_CallEvaluate");
        g_shim_release  = (PFN_ShimRelease)GetProcAddress(shim, "DLSSNR_CallRelease");
        g_shim_shutdown = (PFN_ShimShutdown)GetProcAddress(shim, "DLSSNR_CallShutdown");
    }
    Log("caller shim: %s (init=%p create=%p eval=%p)", shim ? "loaded" : "MISSING",
        g_shim_init, g_shim_create, g_shim_eval);

    wchar_t data_path[MAX_PATH] = L".";
    wcsncpy_s(data_path, g_base.c_str(), _TRUNCATE);
    Log("NGX data path: %ls", data_path);
    // The CLI's project maps to app id 141959980 (0x0876232C); the snippet
    // init must use the same id as the core session.
    const unsigned long long APP_ID = 141959980ULL; // 0x0876232C
    int inited = 0;
    const wchar_t *path_list[1] = { data_path };
    NVSDK_NGX_PathListInfo pli = {};
    pli.Path = path_list;
    pli.Length = 1;
    NVSDK_NGX_FeatureCommonInfo fci = {};
    fci.PathListInfo = pli;
    fci.InternalData = nullptr;
    fci.LoggingInfo.LoggingLevel = NVSDK_NGX_LOGGING_LEVEL_OFF;
    fci.LoggingInfo.Callback = nullptr;
    fci.LoggingInfo.UserData = nullptr;
    fci.LoggingInfo.DisableOtherLoggingSinks = false;

    // The DLSS 5 Neural Rendering feature only initialises on a session opened
    // with Init_ProjectID (the CLI logs "MapProjectId ... projectID 53f803cc-
    // a12f-4d69-90d5-19b7599cad19, engine: custom, engineVersion 0.1"). Plain
    // Init_Ext opens a session where CreateFeature(18) is refused.
    if (g_init_projectid)
    {
        for (int ver = 0x13; ver <= 0x20 && !inited; ++ver)
        {
            NVSDK_NGX_Result r = g_init_projectid("53f803cc-a12f-4d69-90d5-19b7599cad19",
                                                  0 /* ENGINE_TYPE_CUSTOM */, "0.1",
                                                  data_path, g_dev.Get(), ver, nullptr);
            if (r == NGX_SUCCESS) { Log("core Init_ProjectID ver=0x%02X ok", ver); inited = 1; }
            else Log("core Init_ProjectID ver=0x%02X -> 0x%08X", ver, (unsigned)r);
        }
    }
    if (!inited)
    {
        for (int ver = 0x13; ver <= 0x20 && !inited; ++ver)
        {
            NVSDK_NGX_Result r = g_init_ext(APP_ID, data_path, g_dev.Get(), ver, &fci);
            if (r == NGX_SUCCESS) { Log("core Init_Ext ver=0x%02X ok", ver); inited = 1; }
            else Log("core Init_Ext ver=0x%02X -> 0x%08X", ver, (unsigned)r);
        }
    }
    if (!inited) { Log("FAIL: NGX init"); return false; }

    // The snippet's own init (CLI logs "DLSSNR direct init"). It needs the
    // core session above, and must be called through the shim so the snippet's
    // caller validation passes. Version 0x15 (21) matches the CLI.
    if (g_direct_init && g_shim_init)
    {
        NVSDK_NGX_Result r = g_shim_init((void *)g_direct_init, APP_ID, data_path,
                                         g_dev.Get(), 0x15, &fci);
        Log("snippet Init_Ext (via shim) -> 0x%08X", (unsigned)r);
    }
    else if (g_direct_init)
    {
        NVSDK_NGX_Result r = g_direct_init(APP_ID, data_path, g_dev.Get(), 0x15, &fci);
        Log("snippet Init_Ext (direct) -> 0x%08X", (unsigned)r);
    }

    NVSDK_NGX_Result ra = g_alloc(&g_params);
    if (ra != NGX_SUCCESS || !g_params) { Log("FAIL: AllocateParameters 0x%08X", (unsigned)ra); return false; }

    // Feature parameters. The CLI (reference) passes only DLSSNR.* keys for
    // the NR feature (id 18). Its diagnostic log records: Style=1 (int, not a
    // string) Preset=3 Intensity=1 LocalToneStrength=1 LocalStructureStrength=1
    // SkinStructureStrength=-1 UseAutoMask=0 Enabled=1 UICorrection=0
    // DepthInverted=1 MVecScale=(1,1) ScalingRatio=1, and Color/Output only
    // (MVec/Depth/ControlMask are absent).
    int style_int = 1; // natural
    if (style == "default") style_int = 0;
    else if (style == "natural") style_int = 1;
    else if (style == "cinematic") style_int = 2;
    else style_int = atoi(style.c_str());
    g_params->Set("DLSSNR.Width", w);
    g_params->Set("DLSSNR.Height", h);
    g_params->Set("DLSSNR.Enabled", 1);
    g_params->Set("DLSSNR.Reset", 1);
    g_params->Set("DLSSNR.Style", style_int);
    g_params->Set("DLSSNR.Hint.Render.Preset", preset);
    g_params->Set("DLSSNR.Intensity", (float)intensity);
    g_params->Set("DLSSNR.LocalToneStrength", (float)tone);
    g_params->Set("DLSSNR.LocalStructureStrength", (float)structure);
    g_params->Set("DLSSNR.SkinStructureStrength", (float)skin);
    g_params->Set("DLSSNR.UseAutoMask", mask);
    g_params->Set("DLSSNR.UICorrection", 0);
    g_params->Set("DLSSNR.DepthInverted", 1);
    g_params->Set("DLSSNR.ScalingRatio", 1.0f);
    g_params->Set("DLSSNR.MVecScaleX", 1.0f);
    g_params->Set("DLSSNR.MVecScaleY", 1.0f);
    g_params->Set("DLSSNR.Color", color.Get());
    g_params->Set("DLSSNR.Output", output.Get());
    g_params->Set("DLSSNR.Backbuffer", output.Get());
    g_params->Set("DLSSNR.ColorSubrectBaseX", 0);
    g_params->Set("DLSSNR.ColorSubrectBaseY", 0);
    g_params->Set("DLSSNR.ColorSubrectWidth", w);
    g_params->Set("DLSSNR.ColorSubrectHeight", h);
    g_params->Set("DLSSNR.OutputSubrectBaseX", 0);
    g_params->Set("DLSSNR.OutputSubrectBaseY", 0);
    g_params->Set("DLSSNR.OutputSubrectWidth", w);
    g_params->Set("DLSSNR.OutputSubrectHeight", h);

    Log("creating NR feature %d ...", NR_FEATURE_ID);

    // The CLI creates the NR feature "direct" through the snippet (wrapped by
    // the shim), not through the core's CreateFeature. Drop the DLSS SR
    // prerequisite (photos have none) and go straight to the snippet.
    if (g_nr_create && g_shim_create)
    {
        NVSDK_NGX_Result rc = g_shim_create((void *)g_nr_create, g_list.Get(),
                                            NR_FEATURE_ID, g_params, &g_feature);
        if (rc != NGX_SUCCESS || !g_feature)
        { Log("FAIL: CreateFeature(18) via shim -> 0x%08X", (unsigned)rc); return false; }
    }
    else
    {
        NVSDK_NGX_Result rc = g_create(g_list.Get(), NR_FEATURE_ID, g_params, &g_feature);
        if (rc != NGX_SUCCESS || !g_feature)
        { Log("FAIL: CreateFeature(18) -> 0x%08X", (unsigned)rc); return false; }
    }
    Log("feature created, handle=%p", g_feature);

    if(!ExecuteAndWait()) return false;
    g_color=color; g_output=output; g_upload=upload; g_readback=readback;
    g_width=w; g_height=h; g_pitch=row_pitch;
    return true;
}

// Precompute exact scalar conversions once instead of doing floating-point
// bit conversion and clamping for every channel of every video frame.
static uint16_t g_byteToHalf[256];
static uint8_t g_halfToByte[65536];
static void InitializeConversions() {
    for(unsigned i=0;i<256;++i) g_byteToHalf[i]=FloatToHalf(i/255.0f);
    for(unsigned i=0;i<65536;++i)
        g_halfToByte[i]=(uint8_t)std::max(0.f,std::min(255.f,HalfToFloat((uint16_t)i)*255.f+0.5f));
}

static bool Process(const uint8_t* input, uint8_t* result, bool reset) {
    const UINT w=g_width,h=g_height;
    void* mapped=nullptr;
    if(FAILED(g_upload->Map(0,nullptr,&mapped))) return false;
    for(UINT y=0;y<h;++y) {
        uint16_t* row=(uint16_t*)((uint8_t*)mapped+y*g_pitch);
        for(UINT x=0;x<w;++x) for(UINT c=0;c<4;++c)
            row[x*4+c]=g_byteToHalf[input[(y*w+x)*4+c]];
    }
    g_upload->Unmap(0,nullptr);
    auto b=TransitionBarrier(g_color.Get(),D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE,D3D12_RESOURCE_STATE_COPY_DEST);
    g_list->ResourceBarrier(1,&b);
    D3D12_TEXTURE_COPY_LOCATION dst={},src={};
    dst.pResource=g_color.Get();dst.Type=D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    src.pResource=g_upload.Get();src.Type=D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    src.PlacedFootprint.Footprint={DXGI_FORMAT_R16G16B16A16_FLOAT,w,h,1,g_pitch};
    g_list->CopyTextureRegion(&dst,0,0,0,&src,nullptr);
    b=TransitionBarrier(g_color.Get(),D3D12_RESOURCE_STATE_COPY_DEST,D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
    g_list->ResourceBarrier(1,&b);
    g_params->Set("DLSSNR.Reset",reset?1:0);
    int r=g_shim_eval((void*)g_nr_eval,g_list.Get(),g_feature,g_params,nullptr);
    if(r!=NGX_SUCCESS) { Log("NR evaluation failed: 0x%08X",r);return false; }
    b=TransitionBarrier(g_output.Get(),D3D12_RESOURCE_STATE_UNORDERED_ACCESS,D3D12_RESOURCE_STATE_COPY_SOURCE);
    g_list->ResourceBarrier(1,&b);
    dst=src;dst.pResource=g_readback.Get();
    src={};src.pResource=g_output.Get();src.Type=D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    g_list->CopyTextureRegion(&dst,0,0,0,&src,nullptr);
    b=TransitionBarrier(g_output.Get(),D3D12_RESOURCE_STATE_COPY_SOURCE,D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
    g_list->ResourceBarrier(1,&b);
    if(!ExecuteAndWait()) return false;
    if(FAILED(g_readback->Map(0,nullptr,&mapped))) return false;
    for(UINT y=0;y<h;++y) {
        const uint16_t* row=(const uint16_t*)((const uint8_t*)mapped+y*g_pitch);
        for(UINT x=0;x<w;++x) {
            for(UINT c=0;c<3;++c) result[(y*w+x)*4+c]=g_halfToByte[row[x*4+c]];
            result[(y*w+x)*4+3]=255;
        }
    }
    g_readback->Unmap(0,nullptr);
    return true;
}
int wmain(int argc,wchar_t** argv) {
    if(argc!=2) return 1;
    g_base=argv[1];
    _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
    InitializeConversions();
    // Large binary frame transfers should not issue thousands of tiny CRT reads/writes.
    setvbuf(stdin,nullptr,_IOFBF,1024*1024);
    setvbuf(stdout,nullptr,_IOFBF,1024*1024);
    std::vector<uint8_t> input,output;
    HANDLE sharedHandle=nullptr; uint8_t* shared=nullptr; std::string sharedName;
    struct Header { uint32_t width,height,reset; } header;
    while(fread(&header,1,sizeof(header),stdin)==sizeof(header)) {
        if(!header.width || !header.height || header.width>8192 || header.height>8192) break;
        const size_t length=(size_t)header.width*header.height*4;
        const bool useShared=(header.reset & 4)!=0;
        if(useShared) {
            uint32_t nameLength=0;
            if(fread(&nameLength,4,1,stdin)!=1 || !nameLength || nameLength>128) break;
            std::string name(nameLength,'\0');
            if(fread(&name[0],1,nameLength,stdin)!=nameLength) break;
            if(name!=sharedName) {
                if(shared) UnmapViewOfFile(shared);
                if(sharedHandle) CloseHandle(sharedHandle);
                sharedHandle=OpenFileMappingA(FILE_MAP_ALL_ACCESS,FALSE,name.c_str());
                shared=sharedHandle ? (uint8_t*)MapViewOfFile(sharedHandle,FILE_MAP_ALL_ACCESS,0,0,length*2) : nullptr;
                sharedName=name;
                if(!shared) { uint32_t n=0;fwrite(&n,4,1,stdout);fflush(stdout);return 4; }
            }
        } else {
            input.resize(length);output.resize(length);
            if(fread(input.data(),1,length,stdin)!=length) break;
        }
        const uint8_t* inputPixels=useShared ? shared : input.data();
        uint8_t* outputPixels=useShared ? shared+length : output.data();
        if(header.width!=g_width || header.height!=g_height) {
            Cleanup();
            if(!Initialize(header.width,header.height)) { uint32_t n=0;fwrite(&n,4,1,stdout);fflush(stdout);Cleanup();return 2; }
        }
        if(header.reset & 2) { if(!useShared) output = input; } // Prepare resources without changing normal playback.
        else if(!g_shim_eval || !Process(inputPixels,outputPixels,(header.reset & 1)!=0)) { uint32_t n=0;fwrite(&n,4,1,stdout);fflush(stdout);return 3; }
        uint32_t n=(uint32_t)length;
        fwrite(&n,4,1,stdout);if(!useShared) fwrite(output.data(),1,length,stdout);fflush(stdout);
    }
    if(shared) UnmapViewOfFile(shared);
    if(sharedHandle) CloseHandle(sharedHandle);
    Cleanup();return 0;
}
