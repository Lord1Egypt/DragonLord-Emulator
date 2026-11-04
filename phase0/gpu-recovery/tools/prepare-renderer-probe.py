#!/usr/bin/env python3
"""Add device identity and optional fail-closed assertions to copied Gfxstream tests."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

P = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--native-root', type=Path, required=True)
a = p.parse_args()
relative = 'host/vulkan/compositor_vk_unittest.cpp'
f = a.native_root / 'src/hardware/google/gfxstream' / relative
before = f.read_text()
needle = '            m_compositorQueueFamilyIndex = queueFamilyIndex;'
assert before.count(needle) == 1, 'Unexpected source; refuse overlay'
insertion = '''            VkPhysicalDeviceProperties props{};
            k_vk->vkGetPhysicalDeviceProperties(device, &props);
            VkPhysicalDeviceIDProperties ids{};
            ids.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ID_PROPERTIES;
            VkPhysicalDeviceProperties2 props2{};
            props2.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2;
            props2.pNext = &ids;
            k_vk->vkGetPhysicalDeviceProperties2(device, &props2);
            printf("DLGPU_DEVICE name=%s vendor=%u device=%u type=%u api=%u driver=%u luidValid=%u luid=",
                   props.deviceName, props.vendorID, props.deviceID, unsigned(props.deviceType),
                   props.apiVersion, props.driverVersion, unsigned(ids.deviceLUIDValid));
            for (unsigned i = 0; i < VK_LUID_SIZE; ++i) printf("%02x", ids.deviceLUID[i]);
            printf("\\n");
            fflush(stdout);
            if (const char* expected = std::getenv("DLGPU_EXPECT_VENDOR")) {
                ASSERT_EQ(props.vendorID, std::strtoul(expected, nullptr, 0));
            }
            if (const char* expected = std::getenv("DLGPU_EXPECT_TYPE")) {
                ASSERT_EQ(unsigned(props.deviceType), std::strtoul(expected, nullptr, 0));
            }
'''
after = before.replace('#include <algorithm>', '#include <algorithm>\n#include <cstdio>\n#include <cstdlib>').replace(needle,insertion+needle)
patch = ''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+relative,tofile='b/'+relative))
expected = P / 'gfxstream-device-observation.patch'
if expected.exists() and expected.read_text() != patch:
    raise SystemExit('Overlay differs from reviewed patch')
expected.write_text(patch)
f.write_text(after)
manifest = json.loads((P / 'evidence/gfxstream-source-overlay.json').read_text())
manifest['files'].append({'path': relative,'original_sha256':hashlib.sha256(before.encode()).hexdigest(), 'patched_sha256':hashlib.sha256(after.encode()).hexdigest()})
manifest['observation_patch_sha256'] = hashlib.sha256(patch.encode()).hexdigest()
manifest['scope'] = 'Isolated printf safety fix and selected-device observation/assertions; Gfxstream compositor unchanged'
(a.native_root / 'gfxstream-observed-overlay.json').write_text(json.dumps(manifest,indent=2)+'\n')
(P / 'evidence/gfxstream-observed-overlay.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Copied renderer tests instrumented; runtime NOT TESTED')
