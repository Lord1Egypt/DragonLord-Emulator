/* SPDX-License-Identifier: BSD-3-Clause */
/* Actual Windows DLL calls; FFI core/CPU transfers only, never GPU rendering. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
struct iovec { void *iov_base; size_t iov_len; };
#include "rutabaga_gfx_ffi.h"

_Static_assert(sizeof(void*)==8,"64-bit test only");
_Static_assert(sizeof(struct rutabaga_fence)==24,"fence ABI size");
_Static_assert(_Alignof(struct rutabaga_fence)==8,"fence ABI alignment");
_Static_assert(offsetof(struct rutabaga_fence,fence_id)==8,"fence ID offset");
_Static_assert(offsetof(struct rutabaga_fence,ctx_id)==16,"context offset");
_Static_assert(offsetof(struct rutabaga_fence,ring_idx)==20,"ring offset");
_Static_assert(sizeof(struct rutabaga_handle)==16,"HANDLE wire storage");
#ifndef OBSERVE_UNCORRECTED_HEADER
_Static_assert(sizeof(((struct rutabaga_fence*)0)->ring_idx)==1,"C ring field must match actual Rust u8");
#endif
static unsigned failures, tests, callbacks;
static void check(const char *name,int pass) {
    ++tests; failures+=!pass;
    printf("{\"case\":\"%s\",\"status\":\"%s\"}\n",name,pass?"PASS":"FAIL");
}
static FARPROC symbol(HMODULE module,const char *name) {
    FARPROC p=GetProcAddress(module,name);
    if(!p) { fprintf(stderr,"Missing export: %s\n",name); exit(2); }
    return p;
}
static int valid_handle(HANDLE h) { DWORD flags=0; return GetHandleInformation(h,&flags)!=0; }
static void fence_callback(uint64_t cookie,const struct rutabaga_fence *f) {
    if(cookie==UINT64_C(0x1122334455667788) && f->fence_id==UINT64_C(0x123456789abcdef0) && f->ring_idx==0) ++callbacks;
}
int main(int argc,char **argv) {
    if(argc!=3 && argc!=4) return 2;
    if(argc==4 && !SetDllDirectoryA(argv[3])) return 2;
    HMODULE helper=LoadLibraryExA(argv[1],NULL,LOAD_WITH_ALTERED_SEARCH_PATH);
    if(!helper) { fprintf(stderr,"Boundary DLL load error %lu\n",GetLastError()); return 2; }
    typedef size_t (*size_fn)(void);
    typedef int32_t (*fence_fn)(void *);
    typedef int64_t (*handle_fn)(int64_t);
    typedef int32_t (*consume_fn)(int64_t);
    size_fn rust_size=(size_fn)symbol(helper,"boundary_fence_size");
    size_fn rust_align=(size_fn)symbol(helper,"boundary_fence_alignment");
    size_fn rust_offset=(size_fn)symbol(helper,"boundary_ring_offset");
    size_fn rust_width=(size_fn)symbol(helper,"boundary_ring_width");
    fence_fn fill=(fence_fn)symbol(helper,"boundary_fill_fence");
    fence_fn verify=(fence_fn)symbol(helper,"boundary_check_fence");
    struct rutabaga_fence f;
    memset(&f,0xa5,sizeof(f));
    check("C_Rust_size_alignment_offsets",rust_size()==sizeof(f) && rust_align()==_Alignof(struct rutabaga_fence) && rust_offset()==offsetof(struct rutabaga_fence,ring_idx));
    check("C_Rust_ring_field_width",rust_width()==sizeof(f.ring_idx));
    int filled=fill(&f);
    check("Rust_to_C_fields_without_padding_read",filled==0 && f.flags==1 && f.fence_id==UINT64_C(0x123456789abcdef0) && f.ctx_id==0x10203040 && f.ring_idx==63);
    printf("{\"C_ring_bytes\":%zu,\"Rust_ring_bytes\":%zu,\"C_ring_value\":%u}\n",sizeof(f.ring_idx),rust_width(),(unsigned)f.ring_idx);
    f.flags=1; f.fence_id=UINT64_C(0x123456789abcdef0); f.ctx_id=0x10203040; f.ring_idx=63;
    check("C_to_Rust_fields",verify(&f)==0);
    check("helper_null_pointer_rejection",fill(NULL)!=0 && verify(NULL)!=0);
    if(failures) { FreeLibrary(helper); return 1; }
    handle_fn clone=(handle_fn)symbol(helper,"boundary_clone_borrowed_handle");
    consume_fn consume=(consume_fn)symbol(helper,"boundary_consume_handle");
    handle_fn roundtrip=(handle_fn)symbol(helper,"boundary_import_export_handle");
    consume_fn importfail=(consume_fn)symbol(helper,"boundary_failure_after_import");
    HANDLE original=CreateEventW(NULL,TRUE,FALSE,NULL);
    check("create_real_Win32_HANDLE",original!=NULL);
    HANDLE duplicate=(HANDLE)(intptr_t)clone((int64_t)(intptr_t)original);
    check("borrow_clone_preserves_original",duplicate!=INVALID_HANDLE_VALUE && valid_handle(original) && valid_handle(duplicate));
    check("Rust_owned_drop_closes_duplicate",consume((int64_t)(intptr_t)duplicate)==0 && !valid_handle(duplicate) && valid_handle(original));
    HANDLE exported=(HANDLE)(intptr_t)roundtrip((int64_t)(intptr_t)original);
    check("owned_import_export_preserves_full_handle",exported==original && valid_handle(exported));
    check("caller_closes_exported_handle",CloseHandle(exported)!=0 && !valid_handle(exported));
    HANDLE failed=CreateEventW(NULL,TRUE,FALSE,NULL);
    check("close_on_failure_after_ownership_transfer",importfail((int64_t)(intptr_t)failed)==-7 && !valid_handle(failed));
    check("invalid_sentinel_handle_rejection",clone(-1)==-1 && clone(0)==-1 && consume(-1)!=0);

    HMODULE ffi=LoadLibraryExA(argv[2],NULL,LOAD_WITH_ALTERED_SEARCH_PATH);
    if(!ffi) { fprintf(stderr,"FFI DLL load error %lu\n",GetLastError()); return 2; }
    typedef int32_t(*init_fn)(const struct rutabaga_builder*,struct rutabaga**);
    typedef int32_t(*finish_fn)(struct rutabaga**);
    typedef int32_t(*resource_fn)(struct rutabaga*,uint32_t,const struct rutabaga_create_3d*);
    typedef int32_t(*attach_fn)(struct rutabaga*,uint32_t,const struct rutabaga_iovecs*);
    typedef int32_t(*id_fn)(struct rutabaga*,uint32_t);
    typedef int32_t(*write_fn)(struct rutabaga*,uint32_t,uint32_t,const struct rutabaga_transfer*);
    typedef int32_t(*read_fn)(struct rutabaga*,uint32_t,uint32_t,const struct rutabaga_transfer*,const struct iovec*);
    typedef int32_t(*make_fence_fn)(struct rutabaga*,const struct rutabaga_fence*);
    init_fn init=(init_fn)symbol(ffi,"rutabaga_init"); finish_fn finish=(finish_fn)symbol(ffi,"rutabaga_finish");
    resource_fn create=(resource_fn)symbol(ffi,"rutabaga_resource_create_3d");
    attach_fn attach=(attach_fn)symbol(ffi,"rutabaga_resource_attach_backing");
    id_fn detach=(id_fn)symbol(ffi,"rutabaga_resource_detach_backing");
    id_fn unref=(id_fn)symbol(ffi,"rutabaga_resource_unref");
    write_fn write=(write_fn)symbol(ffi,"rutabaga_resource_transfer_write");
    read_fn read=(read_fn)symbol(ffi,"rutabaga_resource_transfer_read");
    make_fence_fn fence=(make_fence_fn)symbol(ffi,"rutabaga_create_fence");
    struct rutabaga_builder builder={0};
    builder.user_data=UINT64_C(0x1122334455667788); builder.wsi=RUTABAGA_WSI_SURFACELESS; builder.fence_cb=fence_callback;
    struct rutabaga *instance=NULL;
    builder.wsi=999;
    check("FFI_invalid_initialization_fails",init(&builder,&instance)!=0 && instance==NULL);
    builder.wsi=RUTABAGA_WSI_SURFACELESS;
    for(unsigned cycle=0;cycle<20;++cycle) {
        if(init(&builder,&instance)!=0 || !instance) { check("FFI_core_initialization",0); break; }
        struct rutabaga_create_3d create_info={0};
        create_info.target=2; create_info.format=1; create_info.bind=2; create_info.width=16; create_info.height=16; create_info.depth=1; create_info.array_size=1;
        unsigned char input[1024],output[1024];
        for(unsigned i=0;i<1024;++i) input[i]=(unsigned char)((i*37+cycle)&255);
        memset(output,0,sizeof(output));
        struct iovec backing={input,sizeof(input)}, destination={output,sizeof(output)};
        struct rutabaga_iovecs iovs={&backing,1};
        struct rutabaga_transfer transfer={0}; transfer.w=16; transfer.h=16; transfer.d=1; transfer.stride=64; transfer.layer_stride=1024;
        int ok=create(instance,1,&create_info)==0;
        ok=ok && create(instance,1,&create_info)!=0;
        ok=ok && attach(instance,1,&iovs)==0 && write(instance,0,1,&transfer)==0;
        ok=ok && read(instance,0,1,&transfer,&destination)==0 && memcmp(input,output,sizeof(input))==0;
        check("FFI_core_bounded_CPU_transfer_roundtrip",ok);
        check("FFI_core_detach_unref_invalid_ID",detach(instance,1)==0 && unref(instance,1)==0 && unref(instance,1)!=0);
        create_info.width=UINT32_MAX; create_info.height=UINT32_MAX;
        check("FFI_overflow_allocation_rejection",create(instance,2,&create_info)!=0);
        f.flags=RUTABAGA_FLAG_FENCE; f.ctx_id=0; f.ring_idx=0; f.fence_id=UINT64_C(0x123456789abcdef0);
        unsigned previous=callbacks;
        check("FFI_core_callback_roundtrip",fence(instance,&f)==0 && callbacks==previous+1);
        check("FFI_core_finish_clears_opaque_pointer",finish(&instance)==0 && instance==NULL);
    }
    FreeLibrary(ffi); FreeLibrary(helper);
    printf("{\"tests\":%u,\"failures\":%u,\"GPU\":\"NOT TESTED\"}\n",tests,failures);
    return failures?1:0;
}
