"""Derive a green microfiber material from the supplied cloth reference photo."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import blender_cloth_material as cloth

OUT = ROOT / 'exports/blender_microfiber_20261027'
ASSETS = ROOT / 'assets/blender_microfiber'
REFERENCE = Path('C:/Users/kenne/OneDrive/Pictures/cloth.jpg')
TILE_METRES = .012
REPEATS = tuple(v / TILE_METRES for v in cloth.UV_METRES)
HEIGHT_METRES = .00012
BUMP_STRENGTH = .65


def write_image(name, rgb, space, path):
    size = rgb.shape[0]
    image = bpy.data.images.new('Microfiber ' + name, width=size, height=size, alpha=False)
    image.colorspace_settings.name = space
    rgba = np.ones((size, size, 4), dtype=np.float32)
    rgba[:, :, :3] = rgb
    image.pixels.foreach_set(rgba.ravel())
    image.filepath_raw = str(path)
    image.file_format = next(i.identifier for i in image.bl_rna.properties['file_format'].enum_items
                             if i.name.startswith('PNG'))
    image.save()
    image.pack()
    return image


def reference_height():
    photo = bpy.data.images.load(str(REFERENCE), check_existing=False)
    width, height = photo.size
    assert abs(width / height - 1600 / 1542) < .001, 'Recheck the crop for a different reference'
    pixels = np.empty(width * height * 4, dtype=np.float32)
    photo.pixels.foreach_get(pixels)
    crop = pixels.reshape(height, width, 4)[::-1][round(height * 80 / 1542):round(height * 380 / 1542),
                                                   round(width * 1150 / 1600):round(width * 1450 / 1600), :3]
    assert crop[:, :, 2].mean() > crop[:, :, 0].mean(), 'Crop must contain the blue cloth'
    # Resize only the reference patch, never a production sensor image.
    luminance = crop @ np.array([.2126, .7152, .0722], dtype=np.float32)
    x = np.linspace(0, crop.shape[1] - 1, 512)
    y = np.linspace(0, crop.shape[0] - 1, 512)
    luminance = np.array([np.interp(x, np.arange(len(row)), row) for row in luminance])
    luminance = np.array([np.interp(y, np.arange(len(row)), row) for row in luminance.T]).T
    f = np.fft.fftfreq(512)
    frequencies = f[:, None] ** 2 + f[None, :] ** 2
    illumination = np.fft.ifft2(np.fft.fft2(luminance) * np.exp(-2 * np.pi ** 2 * 10 ** 2 * frequencies)).real
    detail = np.log(np.maximum(luminance, .001)) - np.log(np.maximum(illumination, .001))
    # Periodic-plus-smooth decomposition removes the photographed crop boundary.
    boundary = np.zeros_like(detail)
    boundary[0] = detail[-1] - detail[0]
    boundary[-1] = -boundary[0]
    difference = detail[:, -1] - detail[:, 0]
    boundary[:, 0] += difference
    boundary[:, -1] -= difference
    denominator = 2 * np.cos(2 * np.pi * f[:, None]) + 2 * np.cos(2 * np.pi * f[None, :]) - 4
    denominator[0, 0] = 1
    smooth = np.fft.fft2(boundary) / denominator
    smooth[0, 0] = 0
    periodic = detail - np.fft.ifft2(smooth).real
    periodic = np.fft.ifft2(np.fft.fft2(periodic) * np.exp(-2 * np.pi ** 2 * .65 ** 2 * frequencies)
                          * (1 - np.exp(-2 * np.pi ** 2 * 12 ** 2 * frequencies))).real
    variance = np.fft.ifft2(np.fft.fft2(periodic ** 2) * np.exp(-2 * np.pi ** 2 * 18 ** 2 * frequencies)).real
    periodic /= np.sqrt(np.maximum(variance, .0001))
    low, high = np.percentile(periodic, [1, 99])
    assert high > low + .01, 'No usable tuft texture in the reference'
    relief = np.clip((periodic - low) / (high - low), 0, 1).astype(np.float32)
    assert np.isfinite(relief).all()
    for axis in (0, 1):
        seam = np.abs(np.take(relief, 0, axis) - np.take(relief, -1, axis))
        assert float(seam.max()) < float(np.abs(np.diff(relief, axis=axis)).max()) * 1.2
    return relief


def main():
    assert not (ASSETS / 'material.json').exists() and not (OUT / 'microfiber.blend').exists(), 'Use a new version instead of overwriting a study'
    source = bpy.data.scenes['03 Instrument Finish Comparison']
    drape = next(o for o in source.objects if o.type == 'MESH' and o.name.startswith('Green_Drape'))
    original_file = bpy.data.filepath
    source_hash = hashlib.sha256((ROOT / 'assets/hospital_isaac.usdz').read_bytes()).hexdigest()
    reference_bytes = REFERENCE.read_bytes()
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    (OUT / 'reference.jpg').write_bytes(reference_bytes)
    # MDL texture loading cannot read the package-member syntax used by USD.
    with zipfile.ZipFile(ROOT / 'assets/hospital_isaac.usdz') as package:
        (ASSETS / 'drape_creases_normal.png').write_bytes(package.read('0/drape_creases_normal.png'))
    relief = reference_height()
    spacing = TILE_METRES / relief.shape[0]
    dx = (np.roll(relief, -1, 1) - np.roll(relief, 1, 1)) * HEIGHT_METRES / (2 * spacing)
    dy = (np.roll(relief, -1, 0) - np.roll(relief, 1, 0)) * HEIGHT_METRES / (2 * spacing)
    normals = np.stack((-dx, -dy, np.ones_like(dx)), axis=-1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
    assert np.isfinite(normals).all() and np.allclose(np.linalg.norm(normals, axis=-1), 1, atol=1e-6)
    source_material = drape.data.materials[0]
    base = next(n.image for n in source_material.node_tree.nodes if n.type == 'TEX_IMAGE' and 'basecolor' in n.image.name)
    data_space = next(n.image.colorspace_settings.name for n in source_material.node_tree.nodes
                      if n.type == 'TEX_IMAGE' and 'normal' in n.image.name)
    pixels = np.empty(base.size[0] * base.size[1] * 4, dtype=np.float32)
    base.pixels.foreach_get(pixels)
    green = pixels.reshape(-1, 4)[:, :3].mean(axis=0, dtype=np.float64)
    shade = 1 + .18 * (relief - relief.mean())
    roughness = np.clip(.84 + .08 * (relief.mean() - relief), 0, 1)
    maps = {}
    for name, rgb in [('basecolor', np.clip(green * shade[:, :, None], 0, 1)),
                      ('roughness', np.repeat(roughness[:, :, None], 3, axis=2)),
                      ('normal', normals * .5 + .5)]:
        maps[name] = write_image(name, rgb, base.colorspace_settings.name if name == 'basecolor' else data_space,
                                ASSETS / (name + '.png'))
    height_image = write_image('height', np.repeat(relief[:, :, None], 3, axis=2), data_space, OUT / 'height.png')
    cloth.REPEATS = REPEATS
    mat = cloth.material(source_material, 'Reference Microfiber', maps)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    surface = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    surface.inputs['Specular IOR Level'].default_value = .35
    ramp = next(n for n in nodes if n.type == 'MATH' and n.operation == 'MULTIPLY_ADD')
    ramp.inputs[1].default_value = .3
    ramp.inputs[2].default_value = .82 - .3 * float(roughness.mean())
    mapping = next(n for n in nodes if n.type == 'VECT_MATH' and n.label.startswith('Measured'))
    mapping.label = 'Photo-derived tuft tile; 12 mm estimated physical span'
    height_node = nodes.new('ShaderNodeTexImage')
    height_node.image = height_image
    height_node.extension = next(i.identifier for i in height_node.bl_rna.properties['extension'].enum_items if i.name == 'Repeat')
    links.new(mapping.outputs['Vector'], height_node.inputs['Vector'])
    crease = next(n for n in nodes if n.type == 'NORMAL_MAP')
    bump = nodes.new('ShaderNodeBump')
    bump.label = 'Microfiber pile over original crease normal'
    bump.inputs['Distance'].default_value = HEIGHT_METRES
    bump.inputs['Strength'].default_value = BUMP_STRENGTH
    links.new(height_node.outputs['Color'], bump.inputs['Height'])
    links.new(crease.outputs['Normal'], bump.inputs['Normal'])
    links.new(bump.outputs['Normal'], surface.inputs['Normal'])
    previous = next(o for o in bpy.data.scenes['06 Cloth Fibres'].objects if o.type == 'MESH').data.materials[0]
    scenes = [cloth.study_scene(source, drape, '07 Previous Woven Cloth', previous),
              cloth.study_scene(source, drape, '07 Reference Microfiber', mat)]
    for scene, label in zip(scenes, ('previous', 'microfiber')):
        mesh = next(o for o in scene.objects if o.type == 'MESH')
        assert mesh.matrix_world == drape.matrix_world
        assert [v.co[:] for v in mesh.data.vertices] == [v.co[:] for v in drape.data.vertices]
        assert [p.vertices[:] for p in mesh.data.polygons] == [p.vertices[:] for p in drape.data.polygons]
        assert [v.uv[:] for v in mesh.data.uv_layers.active.data] == [v.uv[:] for v in drape.data.uv_layers.active.data]
        for close in (False, True):
            cloth.frame(scene, close)
            scene.render.filepath = str(OUT / (label + ('_close.png' if close else '_context.png')))
            bpy.ops.render.render(scene=scene.name, write_still=True)
    assert hashlib.sha256((ROOT / 'assets/hospital_isaac.usdz').read_bytes()).hexdigest() == source_hash
    assert hashlib.sha256(REFERENCE.read_bytes()).hexdigest() == hashlib.sha256(reference_bytes).hexdigest()
    manifest = dict(contract='blender_microfiber_v2', texture_size=[512, 512], tile_metres=TILE_METRES,
                    uv_metres=cloth.UV_METRES, uv_repeats=REPEATS, height_metres=HEIGHT_METRES,
                    bump_strength=BUMP_STRENGTH, roughness_weight=.3, roughness_mean=float(roughness.mean()),
                    reference_sha256=hashlib.sha256(reference_bytes).hexdigest(),
                    reference_crop_normalized=[1150 / 1600, 80 / 1542, 1450 / 1600, 380 / 1542],
                    source_file=original_file, source_hospital_sha256=source_hash,
                    geometry='Unchanged points, topology, UVs, transforms; shader bump only',
                    material='Photo-derived irregular microfiber tufts, green recolour, original crease normals retained',
                    limitations='Photo luminance approximates height; scale estimated without a ruler. No individual fibre geometry or fuzzy silhouette.',
                    asset_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in ASSETS.glob('*.png')})
    (ASSETS / 'material.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    bpy.context.window.scene = scenes[1]
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'microfiber.blend'))
    print('MICROFIBER_STUDY_PASSED', json.dumps(manifest))


if __name__ == '__main__':
    main()
