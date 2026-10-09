// GPU conversion/blending follows the referenced native player's shaders.
#include <d3dcompiler.h>
static ComPtr<ID3D12Resource> g_gpuInput,g_gpuUpload,g_gpuDisplay;
static ComPtr<ID3D12DescriptorHeap> g_gpuHeap;
static ComPtr<ID3D12RootSignature> g_gpuRoot;
static ComPtr<ID3D12PipelineState> g_gpuConvert,g_gpuBlend;
static HANDLE g_gpuHandle=nullptr;
static std::string g_gpuName;
static UINT g_gpuPitch=0,g_gpuIncrement=0;
static void CleanupGpu() {
    if(g_gpuHandle)CloseHandle(g_gpuHandle);
    g_gpuHandle=nullptr;g_gpuName.clear();
    g_gpuInput.Reset();g_gpuUpload.Reset();g_gpuDisplay.Reset();
    g_gpuHeap.Reset();g_gpuRoot.Reset();g_gpuConvert.Reset();g_gpuBlend.Reset();
}
static bool InitializeGpu(const std::string& mapping) {
    if(g_gpuName==mapping && g_gpuDisplay)return true;
    CleanupGpu();
    g_gpuInput=CreateTex2D(g_width,g_height,DXGI_FORMAT_R8G8B8A8_UNORM,
        D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE,D3D12_RESOURCE_FLAG_NONE);
    auto desc=g_gpuInput ? g_gpuInput->GetDesc() : D3D12_RESOURCE_DESC{};
    desc.Flags=D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS | D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET | D3D12_RESOURCE_FLAG_ALLOW_SIMULTANEOUS_ACCESS;
    D3D12_HEAP_PROPERTIES hp={};hp.Type=D3D12_HEAP_TYPE_DEFAULT;
    if(!g_gpuInput || FAILED(g_dev->CreateCommittedResource(&hp,D3D12_HEAP_FLAG_SHARED,&desc,
            D3D12_RESOURCE_STATE_COMMON,nullptr,IID_PPV_ARGS(&g_gpuDisplay))))return false;
    std::wstring name(mapping.begin(),mapping.end());name+=L"-gpu";
    if(FAILED(g_dev->CreateSharedHandle(g_gpuDisplay.Get(),nullptr,GENERIC_ALL,name.c_str(),&g_gpuHandle)))return false;
    g_gpuPitch=(g_width*4+255)&~255u;
    D3D12_RESOURCE_DESC buffer={};buffer.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;
    buffer.Width=(UINT64)g_gpuPitch*g_height;buffer.Height=1;buffer.DepthOrArraySize=1;
    buffer.MipLevels=1;buffer.SampleDesc.Count=1;buffer.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    hp.Type=D3D12_HEAP_TYPE_UPLOAD;
    if(FAILED(g_dev->CreateCommittedResource(&hp,D3D12_HEAP_FLAG_NONE,&buffer,
            D3D12_RESOURCE_STATE_GENERIC_READ,nullptr,IID_PPV_ARGS(&g_gpuUpload))))return false;
    D3D12_DESCRIPTOR_HEAP_DESC heap={};heap.Type=D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
    heap.NumDescriptors=6;heap.Flags=D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
    if(FAILED(g_dev->CreateDescriptorHeap(&heap,IID_PPV_ARGS(&g_gpuHeap))))return false;
    g_gpuIncrement=g_dev->GetDescriptorHandleIncrementSize(heap.Type);
    auto cpu=g_gpuHeap->GetCPUDescriptorHandleForHeapStart();
    auto srv=[&](UINT i,ID3D12Resource* texture){
        D3D12_SHADER_RESOURCE_VIEW_DESC d={};d.Format=texture->GetDesc().Format;
        d.ViewDimension=D3D12_SRV_DIMENSION_TEXTURE2D;d.Shader4ComponentMapping=D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
        d.Texture2D.MipLevels=1;
        g_dev->CreateShaderResourceView(texture,&d,{cpu.ptr+i*g_gpuIncrement});
    };
    auto uav=[&](UINT i,ID3D12Resource* texture){
        D3D12_UNORDERED_ACCESS_VIEW_DESC d={};d.Format=texture->GetDesc().Format;
        d.ViewDimension=D3D12_UAV_DIMENSION_TEXTURE2D;
        g_dev->CreateUnorderedAccessView(texture,nullptr,&d,{cpu.ptr+i*g_gpuIncrement});
    };
    srv(0,g_gpuInput.Get());srv(1,g_color.Get());uav(2,g_color.Get());
    srv(3,g_output.Get());srv(4,g_color.Get());uav(5,g_gpuDisplay.Get());
    D3D12_DESCRIPTOR_RANGE ranges[2]={};
    ranges[0]={D3D12_DESCRIPTOR_RANGE_TYPE_SRV,2,0,0,0};
    ranges[1]={D3D12_DESCRIPTOR_RANGE_TYPE_UAV,1,0,0,0};
    D3D12_ROOT_PARAMETER roots[3]={};
    for(UINT i=0;i<2;++i){roots[i].ParameterType=D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
        roots[i].DescriptorTable={1,&ranges[i]};}
    roots[2].ParameterType=D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;
    roots[2].Constants={0,0,1};
    D3D12_ROOT_SIGNATURE_DESC rs={};rs.NumParameters=3;rs.pParameters=roots;
    ComPtr<ID3DBlob> signature,error;
    if(FAILED(D3D12SerializeRootSignature(&rs,D3D_ROOT_SIGNATURE_VERSION_1,&signature,&error)))return false;
    if(FAILED(g_dev->CreateRootSignature(0,signature->GetBufferPointer(),signature->GetBufferSize(),IID_PPV_ARGS(&g_gpuRoot))))return false;
    const char* convert=
        "Texture2D<float4> src:register(t0); RWTexture2D<float4> dst:register(u0);"
        "[numthreads(16,16,1)] void main(uint3 p:SV_DispatchThreadID){uint w,h;src.GetDimensions(w,h);"
        "if(p.x<w&&p.y<h)dst[p.xy]=src[p.xy];}";
    const char* blend=
        "Texture2D<float4> nr:register(t0);Texture2D<float4> base:register(t1);"
        "RWTexture2D<unorm float4> dst:register(u0);cbuffer Values:register(b0){float intensity;};"
        "[numthreads(16,16,1)]void main(uint3 p:SV_DispatchThreadID){uint w,h;base.GetDimensions(w,h);"
        "if(p.x<w&&p.y<h){float3 b=base[p.xy].rgb;dst[p.xy]=float4(saturate(b+intensity*(nr[p.xy].rgb-b)),1);}}";
    auto compile=[&](const char* source,ComPtr<ID3D12PipelineState>& state){
        ComPtr<ID3DBlob> code;
        if(FAILED(D3DCompile(source,strlen(source),nullptr,nullptr,nullptr,"main","cs_5_0",
                D3DCOMPILE_OPTIMIZATION_LEVEL3,0,&code,&error)))return false;
        D3D12_COMPUTE_PIPELINE_STATE_DESC d={};d.pRootSignature=g_gpuRoot.Get();
        d.CS={code->GetBufferPointer(),code->GetBufferSize()};
        return SUCCEEDED(g_dev->CreateComputePipelineState(&d,IID_PPV_ARGS(&state)));
    };
    if(!compile(convert,g_gpuConvert)||!compile(blend,g_gpuBlend))return false;
    g_gpuName=mapping;Log("GPU conversion/blend/shared presentation ready");
    return true;
}
static bool ProcessGpu(const uint8_t* input,bool reset) {
    void* mapped=nullptr;
    if(FAILED(g_gpuUpload->Map(0,nullptr,&mapped)))return false;
    for(UINT y=0;y<g_height;++y)memcpy((uint8_t*)mapped+y*g_gpuPitch,input+y*g_width*4,g_width*4);
    g_gpuUpload->Unmap(0,nullptr);
    auto barrier=TransitionBarrier(g_gpuInput.Get(),D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE,D3D12_RESOURCE_STATE_COPY_DEST);
    g_list->ResourceBarrier(1,&barrier);
    D3D12_TEXTURE_COPY_LOCATION src={},dst={};
    src.pResource=g_gpuUpload.Get();src.Type=D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    src.PlacedFootprint.Footprint={DXGI_FORMAT_R8G8B8A8_UNORM,g_width,g_height,1,g_gpuPitch};
    dst.pResource=g_gpuInput.Get();dst.Type=D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    g_list->CopyTextureRegion(&dst,0,0,0,&src,nullptr);
    barrier=TransitionBarrier(g_gpuInput.Get(),D3D12_RESOURCE_STATE_COPY_DEST,D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
    g_list->ResourceBarrier(1,&barrier);
    barrier=TransitionBarrier(g_color.Get(),D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE,D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
    g_list->ResourceBarrier(1,&barrier);
    ID3D12DescriptorHeap* heaps[]={g_gpuHeap.Get()};g_list->SetDescriptorHeaps(1,heaps);
    auto gpu=g_gpuHeap->GetGPUDescriptorHandleForHeapStart();
    g_list->SetComputeRootSignature(g_gpuRoot.Get());g_list->SetPipelineState(g_gpuConvert.Get());
    g_list->SetComputeRootDescriptorTable(0,gpu);
    g_list->SetComputeRootDescriptorTable(1,{gpu.ptr+2*g_gpuIncrement});
    g_list->Dispatch((g_width+15)/16,(g_height+15)/16,1);
    barrier=TransitionBarrier(g_color.Get(),D3D12_RESOURCE_STATE_UNORDERED_ACCESS,D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
    g_list->ResourceBarrier(1,&barrier);
    g_params->Set("DLSSNR.Reset",reset?1:0);
    int r=g_shim_eval((void*)g_nr_eval,g_list.Get(),g_feature,g_params,nullptr);
    if(r!=NGX_SUCCESS){Log("GPU NR evaluation failed: 0x%08X",r);return false;}
    barrier=TransitionBarrier(g_output.Get(),D3D12_RESOURCE_STATE_UNORDERED_ACCESS,D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
    g_list->ResourceBarrier(1,&barrier);
    barrier=TransitionBarrier(g_gpuDisplay.Get(),D3D12_RESOURCE_STATE_COMMON,D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
    g_list->ResourceBarrier(1,&barrier);
    g_list->SetDescriptorHeaps(1,heaps);g_list->SetComputeRootSignature(g_gpuRoot.Get());
    g_list->SetPipelineState(g_gpuBlend.Get());
    g_list->SetComputeRootDescriptorTable(0,{gpu.ptr+3*g_gpuIncrement});
    g_list->SetComputeRootDescriptorTable(1,{gpu.ptr+5*g_gpuIncrement});
    float intensity=g_blendPercent/100.f;UINT bits;memcpy(&bits,&intensity,4);
    g_list->SetComputeRoot32BitConstant(2,bits,0);
    g_list->Dispatch((g_width+15)/16,(g_height+15)/16,1);
    barrier=TransitionBarrier(g_output.Get(),D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE,D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
    g_list->ResourceBarrier(1,&barrier);
    barrier=TransitionBarrier(g_gpuDisplay.Get(),D3D12_RESOURCE_STATE_UNORDERED_ACCESS,D3D12_RESOURCE_STATE_COMMON);
    g_list->ResourceBarrier(1,&barrier);
    return ExecuteAndWait();
}
