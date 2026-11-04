// SPDX-License-Identifier: BSD-3-Clause
// Standalone Win32 reference procedure. NOT a QEMU/RCU/WHPX/GPU integration test.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <future>
#include <memory>
#include <mutex>
#include <optional>
#include <thread>

class Mapping : public std::enable_shared_from_this<Mapping> {
    HANDLE section_=nullptr;
    unsigned char* address_=nullptr;
    size_t size_=0, readers_=0;
    uint64_t generation_;
    bool accepting_=true, closed_=false;
    std::mutex mutex_;
    std::condition_variable drained_;
    explicit Mapping(uint64_t generation):generation_(generation) {}
    void release() {
        std::lock_guard<std::mutex> guard(mutex_);
        if (!readers_) std::abort();
        --readers_;
        drained_.notify_all();
    }
public:
    class Lease {
        std::shared_ptr<Mapping> owner_;
        unsigned char* address_;
        size_t length_;
    public:
        Lease(std::shared_ptr<Mapping> owner,unsigned char* address,size_t length):owner_(std::move(owner)),address_(address),length_(length) {}
        Lease(Lease&& other) noexcept:owner_(std::move(other.owner_)),address_(other.address_),length_(other.length_) {}
        Lease(const Lease&)=delete;
        Lease& operator=(const Lease&)=delete;
        ~Lease() { if(owner_) owner_->release(); }
        unsigned char* data() const { return address_; }
        size_t size() const { return length_; }
    };
    static std::shared_ptr<Mapping> create(size_t size,uint64_t generation) {
        if(!size || size>1024*1024) return {};
        auto p=std::shared_ptr<Mapping>(new Mapping(generation));
        p->section_=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,static_cast<DWORD>(size),nullptr);
        if(!p->section_) return {};
        p->address_=static_cast<unsigned char*>(MapViewOfFile(p->section_,FILE_MAP_ALL_ACCESS,0,0,size));
        if(!p->address_) return {};
        p->size_=size;
        return p;
    }
    std::optional<Lease> acquire(uint64_t offset,uint64_t length,uint64_t generation) {
        std::lock_guard<std::mutex> guard(mutex_);
        // Subtraction after the offset check avoids overflowing offset+length.
        if(!accepting_ || closed_ || generation!=generation_ || !length || offset>size_ || length>size_-offset) return {};
        ++readers_;
        return Lease(shared_from_this(),address_+static_cast<size_t>(offset),static_cast<size_t>(length));
    }
    bool accept_callback(uint64_t generation) {
        std::lock_guard<std::mutex> guard(mutex_);
        return accepting_ && !closed_ && generation==generation_;
    }
    bool retire(std::chrono::milliseconds timeout) {
        std::unique_lock<std::mutex> lock(mutex_);
        if(closed_) return true;
        accepting_=false;
        if(!drained_.wait_for(lock,timeout,[this]{return readers_==0;})) return false;
        // Publication is already stopped, and all this procedure's leases have
        // drained. A VMM must additionally retire its RCU and accelerator users.
        if(address_ && !UnmapViewOfFile(address_)) return false;
        address_=nullptr;
        if(section_ && !CloseHandle(section_)) return false;
        section_=nullptr;
        closed_=true;
        return true;
    }
    HANDLE borrowed_section() const { return section_; }
    ~Mapping() { if(!retire(std::chrono::milliseconds(0))) std::abort(); }
};
static unsigned tests=0,failures=0;
static void check(const char* name,bool pass) {
    ++tests;failures+=!pass;
    std::printf("{\"case\":\"%s\",\"status\":\"%s\"}\n",name,pass?"PASS":"FAIL");
}
int main() {
    using namespace std::chrono_literals;
    auto mapping=Mapping::create(4096,1);
    check("real_Win32_mapping_created",bool(mapping));
    if(!mapping) return 1;
    auto lease=mapping->acquire(0,4096,1);
    check("bounded_lease_acquired",bool(lease));
    if(!lease) return 1;
    std::memset(lease->data(),0x5a,lease->size());
    check("overflow_and_range_rejected",!mapping->acquire(UINT64_MAX,4096,1) && !mapping->acquire(4090,20,1) && !mapping->acquire(0,0,1));
    check("stale_generation_rejected",!mapping->acquire(0,4,0) && !mapping->accept_callback(0));
    void* unaligned=MapViewOfFile(mapping->borrowed_section(),FILE_MAP_READ,0,1,16);
    check("Win32_unaligned_mapping_rejected",unaligned==nullptr);
    if(unaligned) UnmapViewOfFile(unaligned);
    check("active_reader_prevents_unmap",!mapping->retire(10ms) && lease->data()[4095]==0x5a);
    check("retirement_stops_new_leases_and_callbacks",!mapping->acquire(0,4,1) && !mapping->accept_callback(1));
    lease.reset();
    check("retirement_after_reader_drain",mapping->retire(100ms));
    check("retirement_is_idempotent",mapping->retire(0ms));
    auto next=Mapping::create(4096,2);
    check("new_generation_does_not_accept_old_callback",next && !next->accept_callback(1) && next->accept_callback(2));
    if(next) check("new_generation_retires",next->retire(0ms));
    auto threaded=Mapping::create(4096,3);
    if(!threaded) return 1;
    std::promise<void> entered,release;
    auto ready=entered.get_future();auto proceed=release.get_future();
    bool pattern_ok=false;
    std::thread reader([&]{
        auto held=threaded->acquire(0,16,3);
        if(!held) std::abort();
        std::memset(held->data(),0x3c,held->size());
        entered.set_value();proceed.wait();pattern_ok=held->data()[15]==0x3c;
    });
    ready.wait();
    bool blocked=!threaded->retire(10ms);
    release.set_value();reader.join();
    check("concurrent_reader_drains_before_unmap",blocked && pattern_ok && threaded->retire(100ms));
    DWORD before=0,after=0;
    GetProcessHandleCount(GetCurrentProcess(),&before);
    bool repeated=true;
    for(unsigned i=0;i<100;++i) {
        auto m=Mapping::create(4096,100+i);
        if(!m) { repeated=false;break; }
        { auto l=m->acquire(0,8,100+i); if(!l){repeated=false;break;} l->data()[7]=static_cast<unsigned char>(i); }
        if(!m->retire(0ms)){repeated=false;break;}
    }
    GetProcessHandleCount(GetCurrentProcess(),&after);
    check("one_hundred_mapping_lifecycles",repeated);
    check("no_handle_growth_after_warmup",after<=before);
    std::printf("{\"tests\":%u,\"failures\":%u,\"handles_before\":%lu,\"handles_after\":%lu,\"GPU\":\"NOT TESTED\",\"QEMU\":\"NOT TESTED\"}\n",tests,failures,before,after);
    return failures?1:0;
}
