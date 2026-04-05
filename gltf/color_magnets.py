"""
Color alternating magnet meshes in backcore.gltf by angular position.
Magnets: meshes 1-8 (group 1) and 13-20 (group 2).
Decodes vertex positions to find each magnet's centroid angle, then
assigns alternating red/blue in angular order.
"""

import json, struct, base64, math

INPUT  = "backcore.gltf"
OUTPUT = "backcore_colored.gltf"

MAGNET_MESHES = list(range(1, 9)) + list(range(13, 21))  # 16 magnets

RED  = [0.8,  0.1,  0.1,  1.0]   # N-pole
BLUE = [0.1,  0.2,  0.8,  1.0]   # S-pole

print("Loading GLTF ...")
with open(INPUT, "r", encoding="utf-8") as f:
    gltf = json.load(f)

# --- decode the binary buffer ---
uri = gltf["buffers"][0]["uri"]
b64 = uri.split(",", 1)[1]
buf_data = base64.b64decode(b64)

accessors   = gltf["accessors"]
buffer_views = gltf["bufferViews"]

def get_positions(accessor_idx):
    """Return list of (x, y, z) for a VEC3 FLOAT accessor."""
    acc = accessors[accessor_idx]
    bv  = buffer_views[acc["bufferView"]]
    offset = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    count  = acc["count"]
    stride = bv.get("byteStride", 12)   # 3 floats = 12 bytes default
    pts = []
    for i in range(count):
        x, y, z = struct.unpack_from("<fff", buf_data, offset + i * stride)
        pts.append((x, y, z))
    return pts

def centroid_angle(mesh_idx):
    """Compute the XY centroid angle (radians) for the first primitive of a mesh."""
    prim = gltf["meshes"][mesh_idx]["primitives"][0]
    pos_acc = prim["attributes"]["POSITION"]
    pts = get_positions(pos_acc)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return math.atan2(cy, cx)

# --- compute angle for each magnet mesh ---
print("Computing magnet angles ...")
mesh_angles = []
for mesh_idx in MAGNET_MESHES:
    angle = centroid_angle(mesh_idx)
    print(f"  mesh {mesh_idx:2d}  angle = {math.degrees(angle):7.2f} deg")
    mesh_angles.append((angle, mesh_idx))

# sort by angle so we go around the ring
mesh_angles.sort(key=lambda x: x[0])
print("\nSorted order:")
for rank, (angle, mesh_idx) in enumerate(mesh_angles):
    pole = "N (red)" if rank % 2 == 0 else "S (blue)"
    print(f"  rank {rank:2d}  mesh {mesh_idx:2d}  {math.degrees(angle):7.2f} deg  -> {pole}")

# --- add two new materials ---
materials = gltf.setdefault("materials", [])
red_idx  = len(materials)
blue_idx = red_idx + 1

materials.append({
    "doubleSided": True,
    "name": "magnet_N_red",
    "pbrMetallicRoughness": {
        "baseColorFactor": RED,
        "metallicFactor": 0.3,
        "roughnessFactor": 0.5
    }
})
materials.append({
    "doubleSided": True,
    "name": "magnet_S_blue",
    "pbrMetallicRoughness": {
        "baseColorFactor": BLUE,
        "metallicFactor": 0.3,
        "roughnessFactor": 0.5
    }
})

# --- assign alternating colors in angular order ---
print(f"\nAssigning colors (red={red_idx}, blue={blue_idx}) ...")
for rank, (angle, mesh_idx) in enumerate(mesh_angles):
    target_mat = red_idx if rank % 2 == 0 else blue_idx
    pole = "N (red)" if rank % 2 == 0 else "S (blue)"
    count = 0
    for prim in gltf["meshes"][mesh_idx]["primitives"]:
        prim["material"] = target_mat
        count += 1
    print(f"  mesh {mesh_idx:2d}  rank {rank:2d}  -> {pole}  ({count} primitives)")

print("Writing output ...")
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(gltf, f, separators=(",", ":"))

print(f"Done -> {OUTPUT}")
