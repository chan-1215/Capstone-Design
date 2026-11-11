"""Convert the user's two binary STL parts, millimetres -> Unity metres.
Source files remain untouched. Body STL long X -> Unity Z, STL Z -> Unity Y.
Wheel STL axial Z -> Unity X, circular XY -> Unity YZ.
"""
import json
import struct
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'Assets/Resources/Models'
OUT.mkdir(parents=True, exist_ok=True)
manifest = []
for filename, output, wheel in [('Final Test.stl', 'FinalTest_Chassis.obj', False),
                                 ('hweel.stl', 'Hweel_Wheel.obj', True)]:
    source = Path.home() / 'Downloads' / filename
    data = source.read_bytes()
    count = struct.unpack_from('<I', data, 80)[0]
    if len(data) != 84 + 50 * count:
        raise ValueError('Expected binary STL: ' + str(source))
    vertices = np.array([struct.unpack_from('<9f', data, 84 + i * 50 + 12)
                         for i in range(count)]).reshape(-1, 3)
    lo, hi = vertices.min(0), vertices.max(0)
    centre = (lo + hi) / 2
    vertices -= centre
    if wheel:
        vertices = vertices[:, [2, 0, 1]] * 0.001
    else:
        vertices[:, 2] += (hi[2] - lo[2]) / 2
        vertices = vertices[:, [1, 2, 0]] * 0.001
    with (OUT / output).open('w', encoding='ascii') as f:
        f.write('# Original author CAD, STL millimetres converted to metres\n')
        for p in vertices:
            f.write('v %.8f %.8f %.8f\n' % tuple(p))
        for i in range(count):
            f.write('f %d %d %d\n' % (i*3+1, i*3+2, i*3+3))
    manifest.append(dict(source=str(source), output=output, triangles=count,
                         source_size_mm=(hi-lo).tolist(), unity_size_m=np.ptp(vertices, axis=0).tolist()))
(OUT/'cad_manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(manifest, indent=2, ensure_ascii=False))
