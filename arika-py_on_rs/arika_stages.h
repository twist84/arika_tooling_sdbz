#ifndef ARIKA_STAGES_H
#define ARIKA_STAGES_H

#include <stdint.h>

/* Little-endian on-disk layouts. Names are fixed 16-byte CP932 strings.
   Research names are not recovered original source identifiers.
   STG transform/link interpretation is an authored-preview inference. */

typedef struct s_arika_stg_header
{
    uint32_t version;
    uint32_t magic;
    uint32_t name_count;
    uint32_t template_root_count;
} s_arika_stg_header;

typedef struct s_arika_stg_node_header
{
    uint8_t kind;
    uint8_t inline_reference_count;
    uint8_t links;
    uint8_t flags;
    uint32_t name_index;
} s_arika_stg_node_header;

typedef struct s_arika_stg_transform_node
{
    s_arika_stg_node_header header;
    float translation[3];
    float rotation_radians[3];
    float scale[3];
} s_arika_stg_transform_node;

typedef struct s_arika_stg_reference
{
    uint32_t name_index;
    uint32_t flags;
} s_arika_stg_reference;

typedef struct s_arika_hit_header
{
    uint32_t version;
    uint32_t magic;
    uint32_t object_count;
    uint32_t objects_offset;
    uint32_t polygons_offset;
    uint32_t vertices_offset;
    uint32_t reserved[2];
} s_arika_hit_header;

typedef struct s_arika_hit_object
{
    uint32_t flags;
    uint32_t polygon_count;
    uint32_t first_polygon;
    float radius;
    float vectors[3][4];
} s_arika_hit_object;

typedef struct s_arika_hit_polygon
{
    uint32_t vertex_count;
    uint32_t first_vertex;
    uint32_t unknown[2];
    float normal[4];
} s_arika_hit_polygon;

#if defined(__cplusplus) && __cplusplus >= 201103L
static_assert(sizeof(s_arika_stg_header) == 0x10, "STG header size");
static_assert(sizeof(s_arika_stg_node_header) == 8, "STG node header size");
static_assert(sizeof(s_arika_stg_transform_node) == 0x2C, "STG transform size");
static_assert(sizeof(s_arika_stg_reference) == 8, "STG reference size");
static_assert(sizeof(s_arika_hit_header) == 0x20, "HIT header size");
static_assert(sizeof(s_arika_hit_object) == 0x40, "HIT object size");
static_assert(sizeof(s_arika_hit_polygon) == 0x20, "HIT polygon size");
#endif

#endif
