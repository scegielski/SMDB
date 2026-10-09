// D3D12 shared-texture presentation through Qt's desktop OpenGL compositor.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <GL/gl.h>
#include <wrl/client.h>
#include <cstdio>
using Microsoft::WRL::ComPtr;
typedef HANDLE (WINAPI *OpenDevice)(void*);
typedef BOOL (WINAPI *CloseDevice)(HANDLE);
typedef HANDLE (WINAPI *RegisterObject)(HANDLE,void*,GLuint,GLenum,GLenum);
typedef BOOL (WINAPI *UnregisterObject)(HANDLE,HANDLE);
typedef BOOL (WINAPI *LockObjects)(HANDLE,GLint,HANDLE*);
struct Surface {
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11Texture2D> shared,texture;
    ComPtr<ID3D11DeviceContext> context;
    HANDLE interop=nullptr,object=nullptr;
};
static char lastError[256];
extern "C" __declspec(dllexport) const char* DlssInteropError(){return lastError;}
static OpenDevice openDevice;
static CloseDevice closeDevice;
static RegisterObject registerObject;
static UnregisterObject unregisterObject;
static LockObjects lockObjects,unlockObjects;
extern "C" __declspec(dllexport) bool DlssInteropAvailable() {
    openDevice=(OpenDevice)wglGetProcAddress("wglDXOpenDeviceNV");
    closeDevice=(CloseDevice)wglGetProcAddress("wglDXCloseDeviceNV");
    registerObject=(RegisterObject)wglGetProcAddress("wglDXRegisterObjectNV");
    unregisterObject=(UnregisterObject)wglGetProcAddress("wglDXUnregisterObjectNV");
    lockObjects=(LockObjects)wglGetProcAddress("wglDXLockObjectsNV");
    unlockObjects=(LockObjects)wglGetProcAddress("wglDXUnlockObjectsNV");
    return openDevice && closeDevice && registerObject && unregisterObject && lockObjects && unlockObjects;
}
extern "C" __declspec(dllexport) void DlssInteropClose(Surface* s) {
    if(!s)return;
    if(s->object)unregisterObject(s->interop,s->object);
    if(s->interop)closeDevice(s->interop);
    delete s;
}
extern "C" __declspec(dllexport) Surface* DlssInteropOpen(const wchar_t* name,GLuint texture) {
    if(!DlssInteropAvailable()){sprintf_s(lastError,"Missing NV interop extension");return nullptr;}
    auto s=new Surface;
    ComPtr<IDXGIFactory1> factory;CreateDXGIFactory1(IID_PPV_ARGS(&factory));
    ComPtr<IDXGIAdapter1> adapter;
    for(UINT i=0;factory && factory->EnumAdapters1(i,&adapter)!=DXGI_ERROR_NOT_FOUND;++i){
        DXGI_ADAPTER_DESC1 desc;adapter->GetDesc1(&desc);
        if(desc.VendorId==0x10de && !(desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE))break;
        adapter.Reset();
    }
    if(!adapter || FAILED(D3D11CreateDevice(adapter.Get(),D3D_DRIVER_TYPE_UNKNOWN,nullptr,
            D3D11_CREATE_DEVICE_BGRA_SUPPORT,nullptr,0,D3D11_SDK_VERSION,&s->device,nullptr,nullptr))) {
        sprintf_s(lastError,"D3D11 device creation failed");delete s;return nullptr;
    }
    ComPtr<ID3D11Device1> d1;s->device.As(&d1);
    HRESULT hr=d1 ? d1->OpenSharedResourceByName(name,DXGI_SHARED_RESOURCE_READ|DXGI_SHARED_RESOURCE_WRITE,IID_PPV_ARGS(&s->shared)) : E_NOINTERFACE;
    if(FAILED(hr)) {
        sprintf_s(lastError,"OpenSharedResourceByName failed: 0x%08X",hr);delete s;return nullptr;
    }
    D3D11_TEXTURE2D_DESC desc;s->shared->GetDesc(&desc);
    desc.BindFlags=D3D11_BIND_SHADER_RESOURCE|D3D11_BIND_RENDER_TARGET;
    desc.MiscFlags=0;desc.CPUAccessFlags=0;desc.Usage=D3D11_USAGE_DEFAULT;
    if(FAILED(s->device->CreateTexture2D(&desc,nullptr,&s->texture))){
        sprintf_s(lastError,"Interop presentation texture creation failed");delete s;return nullptr;
    }
    s->device->GetImmediateContext(&s->context);
    s->interop=openDevice(s->device.Get());
    if(s->interop)s->object=registerObject(s->interop,s->texture.Get(),texture,GL_TEXTURE_2D,0 /* READ_ONLY */);
    if(!s->object){sprintf_s(lastError,"WGL register/open failed: error %lu, device=%p",GetLastError(),s->interop);DlssInteropClose(s);return nullptr;}
    return s;
}
extern "C" __declspec(dllexport) void DlssInteropCopy(Surface* s) {
    if(!s)return;
    s->context->CopyResource(s->texture.Get(),s->shared.Get());
    s->context->Flush();
}
extern "C" __declspec(dllexport) bool DlssInteropLock(Surface* s) {
    return s && lockObjects(s->interop,1,&s->object);
}
extern "C" __declspec(dllexport) bool DlssInteropUnlock(Surface* s) {
    return s && unlockObjects(s->interop,1,&s->object);
}
