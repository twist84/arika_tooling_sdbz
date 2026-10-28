#ifndef ARIKA_MODELS_H
#define ARIKA_MODELS_H

#include <stdint.h>

/* Little-endian file layouts. Offsets are relative to their containing chunk,
   except RFSM bindings, which are absolute within the RFSM file. */
typedef struct s_arika_vector4
{
    float x;
    float y;
    float z;
    float w;
} s_arika_vector4;

typedef struct s_arika_chunk_header
{
    char magic[4];
    uint32_t byte_size;
    uint32_t count;
    uint32_t reserved[5];
} s_arika_chunk_header;

typedef struct s_arika_hierarchy_node
{
    int32_t index;
    int32_t parent;
    int32_t first_child;
    int32_t next_sibling;
    s_arika_vector4 scale;
    s_arika_vector4 rotation_degrees;
    s_arika_vector4 translation;
} s_arika_hierarchy_node;

typedef struct s_arika_xmod_prefix
{
    char magic[4];
    uint32_t byte_size;
    uint32_t unknown_08;
    uint32_t vertex_flags;
    uint32_t mesh_index;
    uint32_t unknown_14;
    uint32_t unknown_18;
    uint32_t unknown_1c;
    uint32_t vertex_flags_copy;
    uint32_t unknown_24;
    uint32_t dma_byte_size;
    uint32_t unknown_2c;
    uint32_t vertex_count;
    uint32_t triangle_count;
    uint32_t unknown_38;
    uint32_t palette_mask;
} s_arika_xmod_prefix;

typedef struct s_arika_mot2_channel
{
    uint16_t channel_count;
    uint16_t key_count;
    uint32_t vectors_offset;
    uint32_t times_offset;
} s_arika_mot2_channel;

typedef struct s_arika_mot2_header
{
    char magic[4];
    uint32_t byte_size;
    float frames_per_second;
    uint16_t frame_count;
    uint16_t node_count;
    uint16_t constant_vector_count;
    uint16_t animated_channel_count;
    uint32_t nodes_offset;
    uint32_t constants_offset;
    s_arika_mot2_channel translation;
    s_arika_mot2_channel rotation;
    s_arika_mot2_channel scale;
} s_arika_mot2_header;

typedef struct s_arika_mot2_node
{
    uint16_t animated_flags; /* 1 translation, 2 rotation, 4 scale */
    uint16_t translation_index;
    uint16_t rotation_index;
    uint16_t scale_index;
} s_arika_mot2_node;

typedef struct s_arika_rfsm_bindings
{
    uint32_t unknown;
    uint32_t channel_to_bone_offset;
    uint32_t bone_to_node_offset;
} s_arika_rfsm_bindings;

typedef struct s_arika_face_group
{
    uint32_t program_count;
    uint32_t program_offsets;
} s_arika_face_group;

typedef struct s_arika_face_record
{
    float time_seconds;
    uint8_t expression;
    uint8_t behavior;
    uint16_t flags;
} s_arika_face_record;

#ifdef __cplusplus
static_assert(sizeof(s_arika_face_group) == 8, "face group size");
static_assert(sizeof(s_arika_face_record) == 8, "face record size");
static_assert(sizeof(s_arika_chunk_header) == 0x20, "chunk header size");
static_assert(sizeof(s_arika_hierarchy_node) == 0x40, "hierarchy node size");
static_assert(sizeof(s_arika_xmod_prefix) == 0x40, "XMOD prefix size");
static_assert(sizeof(s_arika_mot2_header) == 0x40, "MOT2 header size");
static_assert(sizeof(s_arika_mot2_node) == 8, "MOT2 node size");
static_assert(sizeof(s_arika_rfsm_bindings) == 12, "RFSM binding size");
#endif
#endif
