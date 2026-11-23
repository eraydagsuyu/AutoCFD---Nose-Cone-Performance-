"""2D karışık (üçgen + dörtgen) mesh'i Fluent ASCII .msh formatında yazar.

Fluent mesh dosya formatı (bölüm indeksleri):
  (0  ...) yorum, (2 2) boyut,
  (10 ...) düğümler, (12 ...) hücreler, (13 ...) yüzler (2D'de kenarlar), (45 ...) bölge isimleri.
Sayılar yüz/hücre/düğüm bölümlerinde onaltılık (hex) yazılır.

Yön kuralı (2D, Fluent 2024 R1 ile doğrulandı): n0 -> n1 yönünde bakıldığında c0 SOL tarafta,
c1 sağ taraftadır (sınır yüzlerinde c1 = 0 ve hücre c0'dır). Ters yazılırsa Fluent tüm hücreleri
negatif hacimli ve yüzleri "left-handed" raporlar.
"""
from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Fluent BC tip kodları
BC_CODES = {
    "interior": 2,
    "wall": 3,
    "pressure-inlet": 4,
    "pressure-outlet": 5,
    "symmetry": 7,
    "pressure-far-field": 9,
    "velocity-inlet": 10,
    "axis": 37,
}


@dataclass
class FaceZone:
    name: str
    bc_type: str          # BC_CODES anahtarı
    faces: np.ndarray     # (n, 4): n0, n1, c0, c1 (1 tabanlı; c1 = 0 sınırda)


def build_faces(cells: list[np.ndarray], xy: np.ndarray):
    """Hücre listesinden kenar tablosu: {(min,max): [(cell, n_a, n_b), ...]} (0 tabanlı)."""
    edges: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for ci, cell in enumerate(cells):
        k = len(cell)
        for j in range(k):
            a, b = int(cell[j]), int(cell[(j + 1) % k])
            edges.setdefault((min(a, b), max(a, b)), []).append((ci, a, b))
    return edges


def make_face_zones(cells: list[np.ndarray], xy: np.ndarray, classify) -> tuple[FaceZone, list[FaceZone]]:
    """classify(n_a, n_b) -> sınır bölge adı (str) veya None (sınıflandırılamadı).

    Hücreler saat yönünün tersine (CCW) tanımlı olmalıdır: CCW hücrede (a -> b) kenarı boyunca
    hücre solda kalır; yüz (a -> b) yönünde yazılır ve bu hücre c0 olur.
    """
    edges = build_faces(cells, xy)
    interior = []
    boundary: dict[str, list] = {}
    unclassified = []
    for (_, _), lst in edges.items():
        if len(lst) == 2:
            (c1_, a1, b1), (c2_, _, _) = lst
            # a1->b1 boyunca c1_ solda -> c0; komşu c2_ sağda -> c1
            interior.append((a1 + 1, b1 + 1, c1_ + 1, c2_ + 1))
        elif len(lst) == 1:
            c, a, b = lst[0]
            name = classify(a, b)
            if name is None:
                unclassified.append((a, b))
                continue
            boundary.setdefault(name, []).append((a + 1, b + 1, c + 1, 0))
        else:
            raise ValueError(f"Kenar {len(lst)} hücreye ait (manifold değil)")
    if unclassified:
        pts = xy[np.array(unclassified[:5]).ravel()]
        raise ValueError(f"{len(unclassified)} sınır kenarı sınıflandırılamadı, örnek düğümler: {pts.tolist()}")
    return np.array(interior, dtype=np.int64), {k: np.array(v, dtype=np.int64) for k, v in boundary.items()}


def write_fluent_msh(path: Path, xy: np.ndarray, cells: list[np.ndarray], interior: np.ndarray,
                     boundary: dict[str, np.ndarray], bc_types: dict[str, str],
                     fluid_name: str = "fluid", comment: str = "") -> None:
    n_nodes = len(xy)
    n_cells = len(cells)
    zone_order = list(boundary.keys())
    n_faces = len(interior) + sum(len(boundary[z]) for z in zone_order)

    NODE_ZONE, CELL_ZONE, INT_ZONE = 1, 2, 3
    lines = [
        f'(0 "{comment or "RocketCFD 2D axisymmetric mesh"}")',
        "(0 \"Dimensions:\")",
        "(2 2)",
        f"(10 (0 1 {n_nodes:x} 0 2))",
        f"(12 (0 1 {n_cells:x} 0))",
        f"(13 (0 1 {n_faces:x} 0))",
        f"(10 ({NODE_ZONE:x} 1 {n_nodes:x} 1 2)(",
    ]
    lines += [f"{x:.12e} {y:.12e}" for x, y in xy]
    lines.append("))")

    # Hücreler: 0 = karışık; tip listesi 1 = üçgen, 3 = dörtgen
    types = ["1" if len(c) == 3 else "3" for c in cells]
    lines.append(f"(12 ({CELL_ZONE:x} 1 {n_cells:x} 1 0)(")
    for i in range(0, len(types), 40):
        lines.append(" ".join(types[i:i + 40]))
    lines.append("))")

    start = 1

    def face_block(zid: int, code: int, arr: np.ndarray):
        nonlocal start
        end = start + len(arr) - 1
        out = [f"(13 ({zid:x} {start:x} {end:x} {code:x} 2)("]
        out += [f"{a:x} {b:x} {c0:x} {c1:x}" for a, b, c0, c1 in arr]
        out.append("))")
        start = end + 1
        return out

    lines += face_block(INT_ZONE, BC_CODES["interior"], interior)
    zone_ids = {}
    for i, z in enumerate(zone_order):
        zid = INT_ZONE + 1 + i
        zone_ids[z] = zid
        lines += face_block(zid, BC_CODES[bc_types[z]], boundary[z])

    lines.append(f"(45 ({CELL_ZONE} fluid {fluid_name})())")
    lines.append(f"(45 ({INT_ZONE} interior interior-{fluid_name})())")
    for z in zone_order:
        lines.append(f"(45 ({zone_ids[z]} {bc_types[z]} {z})())")

    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines) + "\n"
    if path.suffix == ".gz":          # Fluent .msh.gz dosyasını doğrudan okur (~%68 daha küçük)
        with gzip.open(path, "wt", encoding="ascii", compresslevel=9) as fh:
            fh.write(text)
    else:
        path.write_text(text, encoding="ascii")
