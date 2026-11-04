// SPDX-License-Identifier: BSD-3-Clause
// Read-only kernel GPU accounting for one child. No ETW/security/driver changes.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winternl.h>
#include <d3dkmthk.h>
#include <dxgi1_2.h>
#include <psapi.h>
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
#include <set>
#include <memory>
static FILE* trace=nullptr;

struct Adapter { LUID luid; UINT nodes; UINT vendor; };
static std::string utf8(const wchar_t* s) {
    int n=WideCharToMultiByte(CP_UTF8,0,s,-1,nullptr,0,nullptr,nullptr);
    if(n<=0) return "";
    std::string out(size_t(n),'\0');WideCharToMultiByte(CP_UTF8,0,s,-1,out.data(),n,nullptr,nullptr);
    out.pop_back();return out;
}
static std::string escaped(const std::string& s){
    std::string r;for(unsigned char c:s){if(c=='\\'||c=='"')r+='\\';if(c>=32)r+=char(c);}return r;
}
static void modules(HANDLE p,std::set<std::wstring>& seen){
    HMODULE list[1024];DWORD needed=0;
    if(!EnumProcessModulesEx(p,list,sizeof(list),&needed,LIST_MODULES_ALL))return;
    for(size_t i=0;i<needed/sizeof(HMODULE)&&i<1024;++i){
        wchar_t path[32768];if(GetModuleFileNameExW(p,list[i],path,32768)&&seen.insert(path).second)
            fprintf(trace,"DLK {\"event\":\"module\",\"path\":\"%s\"}\n",escaped(utf8(path)).c_str());
    }
}
int wmain(int argc,wchar_t** argv){
    if(argc!=5)return 2;
    if(GetFileAttributesW(argv[4])!=INVALID_FILE_ATTRIBUTES)return 2;
    trace=_wfopen(argv[4],L"wb");if(!trace)return 2;
    std::unique_ptr<FILE,decltype(&fclose)> trace_owner(trace,&fclose);
    // Arguments: child absolute exe, simple unquoted argument string, timeout seconds.
    if(wcschr(argv[1],L'"')||wcschr(argv[2],L'"'))return 2;
    std::wstring line=L"\""+std::wstring(argv[1])+L"\" "+argv[2];
    unsigned timeout=wcstoul(argv[3],nullptr,10);if(timeout==0||timeout>300)return 2;
    std::vector<Adapter> adapters;
    IDXGIFactory1* factory=nullptr;
    HRESULT hr=CreateDXGIFactory1(__uuidof(IDXGIFactory1),reinterpret_cast<void**>(&factory));
    if(FAILED(hr)){fprintf(trace,"DLK {\"event\":\"factory_fail\",\"hr\":%lu}\n",DWORD(hr));return 2;}
    for(UINT i=0;;++i){
        IDXGIAdapter1* adapter=nullptr;if(factory->EnumAdapters1(i,&adapter)!=S_OK)break;
        DXGI_ADAPTER_DESC1 desc{};adapter->GetDesc1(&desc);adapter->Release();
        D3DKMT_QUERYSTATISTICS q{};q.Type=D3DKMT_QUERYSTATISTICS_ADAPTER;q.AdapterLuid=desc.AdapterLuid;
        NTSTATUS st=D3DKMTQueryStatistics(&q);
        fprintf(trace,"DLK {\"event\":\"adapter\",\"name\":\"%s\",\"luid_high\":%lu,\"luid_low\":%lu,\"vendor\":%u,\"status\":%lu,\"nodes\":%lu}\n",
            escaped(utf8(desc.Description)).c_str(),DWORD(desc.AdapterLuid.HighPart),desc.AdapterLuid.LowPart,desc.VendorId,DWORD(st),st==0?q.QueryResult.AdapterInformation.NodeCount:0);
        if(st==0&&q.QueryResult.AdapterInformation.NodeCount>0&&q.QueryResult.AdapterInformation.NodeCount<=128)
            adapters.push_back({desc.AdapterLuid,q.QueryResult.AdapterInformation.NodeCount,desc.VendorId});
    }
    factory->Release();if(adapters.empty())return 2;
    STARTUPINFOW si{};si.cb=sizeof(si);PROCESS_INFORMATION pi{};
    if(!CreateProcessW(argv[1],line.data(),nullptr,nullptr,TRUE,CREATE_SUSPENDED,nullptr,nullptr,&si,&pi)){
        fprintf(trace,"DLK {\"event\":\"create_fail\",\"error\":%lu}\n",GetLastError());return 2;}
    LARGE_INTEGER freq{},start{},now{};QueryPerformanceFrequency(&freq);QueryPerformanceCounter(&start);
    fprintf(trace,"DLK {\"event\":\"child\",\"pid\":%lu,\"qpc_frequency\":%lld}\n",pi.dwProcessId,freq.QuadPart);fflush(trace);
    std::set<std::wstring> seen;bool resumed=false,timed_out=false;unsigned sample=0;
    for(;;){
        QueryPerformanceCounter(&now);
        for(const auto& a:adapters)for(UINT node=0;node<a.nodes;++node){
            D3DKMT_QUERYSTATISTICS q{};q.Type=D3DKMT_QUERYSTATISTICS_PROCESS_NODE;q.AdapterLuid=a.luid;q.hProcess=pi.hProcess;q.QueryProcessNode.NodeId=node;
            NTSTATUS st=D3DKMTQueryStatistics(&q);
            fprintf(trace,"DLK {\"event\":\"sample\",\"sample\":%u,\"pid\":%lu,\"qpc_delta\":%lld,\"luid_high\":%lu,\"luid_low\":%lu,\"vendor\":%u,\"node\":%u,\"status\":%lu,\"running_time_raw\":%lld,\"context_switches\":%lu}\n",
                sample,pi.dwProcessId,now.QuadPart-start.QuadPart,DWORD(a.luid.HighPart),a.luid.LowPart,a.vendor,node,DWORD(st),st==0?q.QueryResult.ProcessNodeInformation.RunningTime.QuadPart:-1LL,st==0?q.QueryResult.ProcessNodeInformation.ContextSwitch:0);
        }
        if(!resumed){ResumeThread(pi.hThread);resumed=true;fprintf(trace,"DLK {\"event\":\"resumed\",\"qpc_delta\":%lld}\n",now.QuadPart-start.QuadPart);}
        modules(pi.hProcess,seen);fflush(trace);++sample;
        DWORD wait=WaitForSingleObject(pi.hProcess,100);
        if(wait==WAIT_OBJECT_0)break;
        if(wait==WAIT_FAILED){timed_out=true;break;}
        if(now.QuadPart-start.QuadPart>static_cast<LONGLONG>(timeout)*freq.QuadPart){timed_out=true;break;}
    }
    if(timed_out){TerminateProcess(pi.hProcess,124);WaitForSingleObject(pi.hProcess,5000);}
    DWORD code=0;GetExitCodeProcess(pi.hProcess,&code);
    fprintf(trace,"DLK {\"event\":\"exit\",\"pid\":%lu,\"code\":%lu,\"timeout\":%s,\"samples\":%u}\n",pi.dwProcessId,code,timed_out?"true":"false",sample);
    CloseHandle(pi.hThread);CloseHandle(pi.hProcess);
    return timed_out?124:static_cast<int>(code);
}
