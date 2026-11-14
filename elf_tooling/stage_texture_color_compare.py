#!/usr/bin/env python3
"""Compare ELF CStage clear-colour presets with decoded stage PIX textures.

Usage:
    python elf_tooling/stage_texture_color_compare.py extracted/stg --output stage_color_audit

The input directory can contain FPIX files (requires the built arika_backend)
or pre-decoded s01a.pix.000.png images (no native backend required).
Requires numpy and Pillow. The RGB distance is measured in decoded 8-bit RGB,
not in linear light. It tests colour correlation, not a runtime sky algorithm.
"""
import argparse
import csv
from io import BytesIO
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'arika-py_on_rs'))
from arika_stage_background import STAGE_CLASS_RGB


# CStage08/CStage09 have distinct s08a/s09a PIX resources even though their
# scene geometry is shared with the s01/s02 stage families. CStage05's two
# preset colours use the same s05a PIX file.
STAGE_PIX = {
    'CStage00': ('s00a',),
    'CStage01': ('s01a',),
    'CStage02': ('s02a',),
    'CStage03': ('s03a', 's03b'),
    'CStage04': ('s04a', 's04b'),
    'CStage05': ('s05a', 's05a'),
    'CStage06': ('s06a',),
    'CStage07': ('s07a',),
    'CStage08': ('s08a',),
    'CStage09': ('s09a',),
    'CStage10': ('s10a',),
    'CStage11': ('s11a',),
    'CStage12': ('s12a',),
}


def iter_images(root, asset):
    """Yield (texture index, source path, decoded PIL image)."""
    images = sorted(root.rglob(asset + '.pix.*.png'))
    if images:
        for path in images:
            try:
                index = int(path.name.rsplit('.', 2)[-2])
            except ValueError:
                continue
            with Image.open(path) as image:
                yield index, str(path), image.convert('RGBA')
        return

    # Decode source textures directly via arika_core's ctypes wrapper.
    files = sorted(root.rglob(asset + '.pix'))
    if not files:
        return
    import arika_dat
    for path in files:
        data = path.read_bytes()
        metadata = arika_dat.container(data)
        if metadata['magic'] != 'FPIX':
            raise ValueError('expected FPIX in ' + str(path))
        for chunk in metadata['chunks']:
            if chunk['magic'] != 'XPIX':
                continue
            start = chunk['offset']
            body = data[start:start + chunk['size']]
            if body[32:36] != b'TIM2':
                continue
            png = arika_dat.tim2_png_bytes(body[32:])
            with Image.open(BytesIO(png)) as image:
                yield chunk['index'], str(path), image.convert('RGBA')


def pixel_statistics(image, target):
    rgba = np.asarray(image, dtype=np.uint8)
    rgb = rgba[:, :, :3].astype(np.int32)
    visible = rgba[:, :, 3] >= 16
    if not np.any(visible):
        return None

    distance_sq = np.sum((rgb - np.asarray(target, dtype=np.int32)) ** 2, axis=2)
    h, w = visible.shape
    edge = np.zeros((h, w), dtype=bool)
    edge[:4, :] = True
    edge[-4:, :] = True
    edge[:, :4] = True
    edge[:, -4:] = True
    edge &= visible

    def closest(mask):
        if not np.any(mask):
            return None, None
        pos = np.unravel_index(np.argmin(np.where(mask, distance_sq, 2 ** 31 - 1)), mask.shape)
        return float(np.sqrt(distance_sq[pos])), rgb[pos].tolist()

    near = visible & (distance_sq <= 9)
    edge_near = edge & (distance_sq <= 9)
    nearest, nearest_rgb = closest(visible)
    border_nearest, border_rgb = closest(edge)
    return {
        'min_pixel_distance': round(nearest, 3),
        'min_pixel_rgb': nearest_rgb,
        'min_edge_distance': None if border_nearest is None else round(border_nearest, 3),
        'min_edge_rgb': border_rgb,
        'visible_pixels': int(visible.sum()),
        'near3_pixels': int(near.sum()),
        'exact_pixels': int((visible & (distance_sq == 0)).sum()),
        'edge_near3_pixels': int(edge_near.sum()),
        'edge_pixels': int(edge.sum()),
    }


def compare(root, output):
    output.mkdir(parents=True, exist_ok=True)
    cache = {}
    rows = []
    summary = []
    errors = []
    for stage, colours in STAGE_CLASS_RGB.items():
        for state, colour in enumerate(colours):
            asset = STAGE_PIX[stage][state]
            if asset not in cache:
                try:
                    cache[asset] = list(iter_images(root, asset))
                except Exception as exc:
                    cache[asset] = []
                    errors.append('%s: %s' % (asset, exc))
            candidates = []
            for index, source, image in cache[asset]:
                stat = pixel_statistics(image, colour)
                if stat is None:
                    continue
                record = {
                    'stage': stage, 'state': state, 'asset': asset,
                    'elf_hex': '#%02X%02X%02X' % colour,
                    'texture_index': index, 'source': source,
                    'width': image.width, 'height': image.height,
                }
                record.update(stat)
                rows.append(record)
                candidates.append(record)

            ranked = sorted(candidates, key=lambda item: (-item['near3_pixels'], item['min_pixel_distance']))
            nearest = sorted(candidates, key=lambda item: item['min_pixel_distance'])
            result = {
                'stage': stage, 'state': state, 'asset': asset,
                'elf_rgb': list(colour), 'elf_hex': '#%02X%02X%02X' % colour,
                'textures': len(candidates),
                'exact_pixels': sum(item['exact_pixels'] for item in candidates),
                'near3_pixels': sum(item['near3_pixels'] for item in candidates),
                'edge_near3_pixels': sum(item['edge_near3_pixels'] for item in candidates),
                'closest_pixel': nearest[0] if nearest else None,
                'most_matching_pixels': ranked[0] if ranked else None,
            }
            summary.append(result)
            if nearest:
                print('%-8s state %d %-5s ELF %s: nearest pixel %.2f; near3=%d; edge near3=%d' %
                      (stage, state, asset, result['elf_hex'],
                       nearest[0]['min_pixel_distance'], result['near3_pixels'],
                       result['edge_near3_pixels']))
            else:
                print('%-8s state %d %-5s ELF %s: no texture decoded' %
                      (stage, state, asset, result['elf_hex']))

    with (output / 'stage_texture_pixels.csv').open('w', newline='', encoding='utf-8') as stream:
        if rows:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    report = {
        'method': 'decoded visible PIX pixels (alpha >= 16), 4px image border, Euclidean 8-bit RGB',
        'interpretation': 'Correlation does not establish that runtime clear colour is derived from textures',
        'texture_images_decoded': sum(len(items) for items in cache.values()),
        'presets': summary,
        'errors': errors,
    }
    (output / 'stage_texture_summary.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Decoded %d images across %d presets; %d errors' %
          (report['texture_images_decoded'], len(summary), len(errors)))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('textures', type=Path, help='folder with stage PIX or PNG dumps')
    parser.add_argument('--output', type=Path, default=Path('stage_color_audit'))
    args = parser.parse_args()
    if not args.textures.is_dir():
        parser.error('input textures directory does not exist')
    result = compare(args.textures, args.output)
    if not result['texture_images_decoded'] or result['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
