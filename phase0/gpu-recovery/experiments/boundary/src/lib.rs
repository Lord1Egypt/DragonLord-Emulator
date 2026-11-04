// SPDX-License-Identifier: BSD-3-Clause
// Uses the actual pinned crate types, not a duplicated Rust fence definition.
use rutabaga_gfx::{RutabagaDescriptor, RutabagaFence, RutabagaFromRawDescriptor,
    RutabagaIntoRawDescriptor, RutabagaRawDescriptor};
use std::mem::{align_of, offset_of, size_of, size_of_val, ManuallyDrop};
use std::ptr::addr_of_mut;

#[link(name = "kernel32")]
extern "system" {
    fn GetHandleInformation(handle: *mut std::ffi::c_void, flags: *mut u32) -> i32;
}

fn valid_handle(raw: i64) -> bool {
    if raw == 0 || raw == -1 { return false; }
    let mut flags = 0;
    unsafe { GetHandleInformation(raw as usize as *mut _, &mut flags) != 0 }
}

#[no_mangle]
pub extern "C" fn boundary_fence_size() -> usize { size_of::<RutabagaFence>() }
#[no_mangle]
pub extern "C" fn boundary_fence_alignment() -> usize { align_of::<RutabagaFence>() }
#[no_mangle]
pub extern "C" fn boundary_ring_offset() -> usize { offset_of!(RutabagaFence, ring_idx) }
#[no_mangle]
pub extern "C" fn boundary_ring_width() -> usize {
    let f = RutabagaFence { flags: 0, fence_id: 0, ctx_id: 0, ring_idx: 0 };
    size_of_val(&f.ring_idx)
}

#[no_mangle]
pub unsafe extern "C" fn boundary_fill_fence(out: *mut RutabagaFence) -> i32 {
    if out.is_null() { return -1; }
    // Individual field stores deliberately preserve caller-owned padding. C must
    // not read that padding as part of a wider ring_idx field.
    addr_of_mut!((*out).flags).write(1);
    addr_of_mut!((*out).fence_id).write(0x1234_5678_9abc_def0);
    addr_of_mut!((*out).ctx_id).write(0x1020_3040);
    addr_of_mut!((*out).ring_idx).write(63);
    0
}

#[no_mangle]
pub unsafe extern "C" fn boundary_check_fence(input: *const RutabagaFence) -> i32 {
    if input.is_null() { return -1; }
    let f = &*input;
    if f.flags == 1 && f.fence_id == 0x1234_5678_9abc_def0 &&
        f.ctx_id == 0x1020_3040 && f.ring_idx == 63 { 0 } else { -1 }
}

#[no_mangle]
pub extern "C" fn boundary_clone_borrowed_handle(raw: i64) -> i64 {
    if !valid_handle(raw) { return -1; }
    // This wrapper borrows the input. Only the duplicate is exported/owned by C.
    let borrowed = ManuallyDrop::new(unsafe {
        RutabagaDescriptor::from_raw_descriptor(raw as usize as RutabagaRawDescriptor)
    });
    match borrowed.try_clone() {
        Ok(copy) => copy.into_raw_descriptor() as usize as i64,
        Err(_) => -1,
    }
}

#[no_mangle]
pub extern "C" fn boundary_consume_handle(raw: i64) -> i32 {
    if !valid_handle(raw) { return -1; }
    let owned = unsafe { RutabagaDescriptor::from_raw_descriptor(raw as usize as RutabagaRawDescriptor) };
    drop(owned);
    0
}

#[no_mangle]
pub extern "C" fn boundary_import_export_handle(raw: i64) -> i64 {
    if !valid_handle(raw) { return -1; }
    let owned = unsafe { RutabagaDescriptor::from_raw_descriptor(raw as usize as RutabagaRawDescriptor) };
    owned.into_raw_descriptor() as usize as i64
}

#[no_mangle]
pub extern "C" fn boundary_failure_after_import(raw: i64) -> i32 {
    if !valid_handle(raw) { return -1; }
    let _owned = unsafe { RutabagaDescriptor::from_raw_descriptor(raw as usize as RutabagaRawDescriptor) };
    // Simulated later-operation failure: local ownership must close on return.
    -7
}
