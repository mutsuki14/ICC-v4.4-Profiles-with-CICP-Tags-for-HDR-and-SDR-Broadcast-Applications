#!/usr/bin/env python3
"""
Generate an ICC v4.4 HDR profile for the KTC M32P10 monitor.

This script creates a BT.2100 PQ Display profile (CICP 9-16-0-0) with:
- BT.2020 color primaries
- PQ (ST 2084) transfer function
- Peak luminance: 1000 cd/m² (VESA DisplayHDR 1000)
- ICC v4.4 with CICP tags

The profile structure is modeled on the reference Adobe BT.2100 PQ profiles
in this repository, with the A2B/B2A LUT data extracted from the reference.
"""

import struct
import hashlib
import os

# ── Reference profile path ──────────────────────────────────────────────────
REFERENCE_PROFILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "PQ Profiles 2022",
    "9-16-0-0 BT2100-PQ-Display-Narrow.icc",
)
OUTPUT_PROFILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "KTC-M32P10-BT2100-PQ-Display.icc",
)

# ── Profile metadata ────────────────────────────────────────────────────────
DESCRIPTION = "KTC M32P10 BT.2100 PQ Display 9-16-0-0"
COPYRIGHT = "Generated for KTC M32P10 2024"
PEAK_LUMINANCE_CD_M2 = 1000


def pad4(data: bytes) -> bytes:
    """Pad data to 4-byte boundary."""
    r = len(data) % 4
    if r:
        data += b"\x00" * (4 - r)
    return data


def build_mluc(text: str) -> bytes:
    """Build an mluc (multiLocalizedUnicodeType) tag."""
    encoded = text.encode("utf-16-be")
    str_offset = 28
    tag = b"mluc"
    tag += b"\x00" * 4
    tag += struct.pack(">I", 1)
    tag += struct.pack(">I", 12)
    tag += b"en"
    tag += b"US"
    tag += struct.pack(">I", len(encoded))
    tag += struct.pack(">I", str_offset)
    tag += encoded
    return pad4(tag)


def build_xyz(x: float, y: float, z: float) -> bytes:
    """Build an XYZType tag."""
    tag = b"XYZ "
    tag += b"\x00" * 4
    tag += struct.pack(">i", int(round(x * 65536)))
    tag += struct.pack(">i", int(round(y * 65536)))
    tag += struct.pack(">i", int(round(z * 65536)))
    return tag


def build_chad(matrix_9: list) -> bytes:
    """Build a chromatic adaptation tag (s15Fixed16ArrayType)."""
    tag = b"sf32"
    tag += b"\x00" * 4
    for v in matrix_9:
        tag += struct.pack(">i", int(round(v * 65536)))
    return tag


def build_cicp(cp: int, tc: int, mc: int, vr: int) -> bytes:
    """Build a CICP tag."""
    tag = b"cicp"
    tag += b"\x00" * 4
    tag += struct.pack("BBBB", cp, tc, mc, vr)
    return tag


def build_tech(sig: bytes) -> bytes:
    """Build a technology tag (signatureType)."""
    tag = b"sig "
    tag += b"\x00" * 4
    tag += sig
    return tag


def build_lumi(cd_m2: float) -> bytes:
    """Build a luminance tag (XYZType) — only Y is meaningful."""
    tag = b"XYZ "
    tag += b"\x00" * 4
    tag += struct.pack(">i", 0)
    tag += struct.pack(">i", int(round(cd_m2 * 65536)))
    tag += struct.pack(">i", 0)
    return tag


def extract_lut_data(ref_data: bytes, tag_sig: str) -> bytes:
    """Extract raw tag data from the reference profile."""
    tag_count = struct.unpack(">I", ref_data[128:132])[0]
    for i in range(tag_count):
        offset = 132 + i * 12
        sig = ref_data[offset:offset + 4].decode("ascii")
        tag_offset = struct.unpack(">I", ref_data[offset + 4:offset + 8])[0]
        tag_size = struct.unpack(">I", ref_data[offset + 8:offset + 12])[0]
        if sig == tag_sig:
            data = ref_data[tag_offset:tag_offset + tag_size]
            return pad4(data)
    raise ValueError(f"Tag '{tag_sig}' not found in reference profile")


def build_profile() -> bytes:
    """Build the complete ICC profile."""
    with open(REFERENCE_PROFILE, "rb") as f:
        ref_data = f.read()

    desc_data = build_mluc(DESCRIPTION)
    cprt_data = build_mluc(COPYRIGHT)
    wtpt_data = build_xyz(0.964203125, 1.0, 0.824905396)
    chad_data = build_chad([
        1.047882080078125, 0.022918701171875, -0.0502166748046875,
        0.0295867919921875, 0.990478515625, -0.0170745849609375,
        -0.009246826171875, 0.01507568359375, 0.751678466796875,
    ])

    a2b0_data = extract_lut_data(ref_data, "A2B0")
    b2a0_data = extract_lut_data(ref_data, "B2A0")

    cicp_data = build_cicp(9, 16, 0, 0)
    tech_data = build_tech(b"vidm")
    lumi_data = build_lumi(PEAK_LUMINANCE_CD_M2)

    tags_unique = [
        (b"desc", desc_data),
        (b"cprt", cprt_data),
        (b"wtpt", wtpt_data),
        (b"chad", chad_data),
        (b"A2B0", a2b0_data),
        (b"B2A0", b2a0_data),
        (b"cicp", cicp_data),
        (b"tech", tech_data),
        (b"lumi", lumi_data),
    ]

    tag_count = 11
    header_size = 128
    tag_table_size = 4 + tag_count * 12

    data_start = header_size + tag_table_size
    if data_start % 4:
        data_start += 4 - (data_start % 4)

    tag_data_blob = b""
    tag_entries = []

    for sig, data in tags_unique:
        offset = data_start + len(tag_data_blob)
        actual_size = len(data)
        tag_entries.append((sig, offset, actual_size))

        if sig == b"A2B0":
            tag_entries.append((b"A2B1", offset, actual_size))
        elif sig == b"B2A0":
            tag_entries.append((b"B2A1", offset, actual_size))

        tag_data_blob += data

    tag_table = struct.pack(">I", tag_count)
    for sig, offset, size in tag_entries:
        tag_table += sig
        tag_table += struct.pack(">I", offset)
        tag_table += struct.pack(">I", size)

    profile_size = data_start + len(tag_data_blob)

    header = b""
    header += struct.pack(">I", profile_size)
    header += b"ADBE"
    header += bytes([4, 64, 0, 0])
    header += b"mntr"
    header += b"RGB "
    header += b"XYZ "
    header += struct.pack(">HHHHHh", 2024, 1, 1, 0, 0, 0)
    header += b"acsp"
    header += b"APPL"
    header += struct.pack(">I", 0)
    header += b"\x00" * 4
    header += b"\x00" * 4
    header += b"\x00" * 8
    header += struct.pack(">I", 0)
    header += struct.pack(">i", int(round(0.964203125 * 65536)))
    header += struct.pack(">i", int(round(1.0 * 65536)))
    header += struct.pack(">i", int(round(0.824905396 * 65536)))
    header += b"ADBE"
    header += b"\x00" * 16
    header += b"\x00" * 28

    assert len(header) == 128

    padding = data_start - header_size - len(tag_table)
    profile = header + tag_table + (b"\x00" * padding) + tag_data_blob

    assert len(profile) == profile_size

    id_data = bytearray(profile)
    id_data[44:48] = b"\x00" * 4
    id_data[64:68] = b"\x00" * 4
    id_data[84:100] = b"\x00" * 16
    profile_id = hashlib.md5(bytes(id_data)).digest()

    profile = bytearray(profile)
    profile[84:100] = profile_id
    profile = bytes(profile)

    return profile


def main():
    profile = build_profile()
    with open(OUTPUT_PROFILE, "wb") as f:
        f.write(profile)
    print(f"Generated: {OUTPUT_PROFILE}")
    print(f"Size: {len(profile)} bytes")
    print(f"Profile ID: {profile[84:100].hex()}")


if __name__ == "__main__":
    main()
