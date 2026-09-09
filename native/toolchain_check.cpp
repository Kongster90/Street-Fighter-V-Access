// Smallest thing that proves the toolchain can produce a DLL this machine will
// load: an export the host can call, plus the attach hook the injected library
// will eventually use.

#include <windows.h>
#include <cstdint>

extern "C" __declspec(dllexport) int sfv_access_probe(int value) {
    return value * 2 + 1;
}

extern "C" __declspec(dllexport) uint64_t sfv_access_module_base() {
    return reinterpret_cast<uint64_t>(GetModuleHandleW(nullptr));
}

BOOL APIENTRY DllMain(HMODULE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        // Injection will do its work from here, off the loader lock.
    }
    return TRUE;
}
