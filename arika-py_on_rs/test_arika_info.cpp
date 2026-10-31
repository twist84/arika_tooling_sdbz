#include "arika_info.h"
#include <cassert>
#include <fstream>
#include <iterator>
#include <vector>

int main(int argc, char **argv)
{
    assert(argc == 2);
    std::ifstream input(argv[1], std::ios::binary);
    std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(input)), {});
    const auto original = bytes;
    assert(arika_info_decode(bytes.data(), bytes.size()));
    assert(bytes.size() == 98304);
    assert(bytes[0x2C] == 0x8E && bytes[0x2D] == 0x07);
    assert(arika_info_encode(bytes.data(), bytes.size()));
    assert(bytes == original);
}
