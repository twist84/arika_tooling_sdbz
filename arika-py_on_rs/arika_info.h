#ifndef ARIKA_INFO_H
#define ARIKA_INFO_H

#include <stdint.h>
#include <stddef.h>

/* Little-endian on-disk structures after decoding. */
typedef struct s_arika_info_header
{
    uint8_t signature_and_key[16];
    uint32_t reserved[7];
    uint32_t file_count;
} s_arika_info_header;

typedef struct s_arika_info_entry
{
    char name_cp932[32];
    uint32_t unknown;
    uint32_t sector_offset;
    uint32_t sector_count;
    uint32_t byte_size;
} s_arika_info_entry;

static inline int arika_info_decode(uint8_t *data, size_t size)
{
    size_t i;
    if (!data || size < 0x30) return 0;
    for (i = 16; i < size; ++i)
    {
        uint8_t swapped = (uint8_t)((data[i] << 4) | (data[i] >> 4));
        data[i] = (uint8_t)((uint8_t)~swapped - data[i & 15]);
    }
    return 1;
}

static inline int arika_info_encode(uint8_t *data, size_t size)
{
    size_t i;
    if (!data || size < 0x30) return 0;
    for (i = 16; i < size; ++i)
    {
        uint8_t inverted = (uint8_t)~(uint8_t)(data[i] + data[i & 15]);
        data[i] = (uint8_t)((inverted << 4) | (inverted >> 4));
    }
    return 1;
}

#ifdef __cplusplus
static_assert(sizeof(s_arika_info_header) == 0x30, "INFO header size");
static_assert(sizeof(s_arika_info_entry) == 0x30, "INFO entry size");
#endif
#endif
