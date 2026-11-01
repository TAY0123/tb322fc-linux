#include <windows.h>
#include <stdexcept>
#include <vector>

extern "C" __declspec(dllexport) int toolchain_link_check(int index)
{
    try {
        std::vector<int> values{1, 2, 3};
        if (index < 0)
            throw std::runtime_error("negative index");
        return values.at(index) + (GetCurrentProcessId() != 0);
    } catch (const std::exception &) {
        return -1;
    }
}
