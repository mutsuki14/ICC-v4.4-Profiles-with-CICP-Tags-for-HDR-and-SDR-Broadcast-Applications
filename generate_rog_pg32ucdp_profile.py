#!/usr/bin/env python3
"""
Generate an ICC v4.4 HDR profile for the ASUS ROG Swift PG32UCDP monitor.

This script creates a BT.2100 PQ Display profile (CICP 9-16-0-0) with:
- BT.2020 color primaries
- PQ (ST 2084) transfer function
- Peak luminance: 1300 cd/m²
- ICC v4.4 with CICP tags

The profile structure is modeled on the reference Adobe BT.2100 PQ profiles
in this repository, with the A2B/B2A LUT data extracted from the reference.
"""

import struct
import hashlib
import sys
import os

# ── Reference profile path ──────────────────────────────────────────────────
REFERENCE_PROFILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "PQ Profiles 2022",
    "9-16-0-0 BT2100-PQ-Display-Narrow.icc",
)
OUTPUT_PROFILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "ROG-PG32UCDP-BT2100-PQ-Display.icc",
)

# ── Profile metadata ────────────────────────────────────────────────────────
DESCRIPTION = "ROG PG32UCDP BT.2100 PQ Display 9-16-0-0"
COPYRIGHT = "Generated for ASUS ROG PG32UCDP 2024"
PEAK_LUMINANCE_CD_M2 = 1300


def pad4(data: bytes) -> bytes:
    """Pad data to 4-byte boundary."""
    r = len(data) % 4
    if r:
        data += b"\x00" * (4 - r)
    return data


def build_mluc(text: str) -> bytes:
    """Build an mluc (multiLocalizedUnicodeType) tag."""
    encoded = text.encode("utf-16-be")
    str_offset = 28  # 4(sig) + 4(reserved) + 4(count) + 4(recsize) + 2(lang) + 2(country) + 4(len) + 4(off)
    tag = b"mluc"                              # type signature
    tag += b"\x00" * 4                         # reserved
    tag += struct.pack(">I", 1)                # number of records
    tag += struct.pack(">I", 12)               # record size
    tag += b"en"                               # language
    tag += b"US"                               # country
    tag += struct.pack(">I", len(encoded))     # string length in bytes
    tag += struct.pack(">I", str_offset)       # string offset from tag start
    tag += encoded
    return pad4(tag)


def build_xyz(x: float, y: float, z: float) -> bytes:
    """Build an XYZType tag."""
    tag = b"XYZ "
    tag += b"\x00" * 4  # reserved
    tag += struct.pack(">i", int(round(x * 65536)))
    tag += struct.pack(">i", int(round(y * 65536)))
    tag += struct.pack(">i", int(round(z * 65536)))
    return tag  # always 20 bytes, already aligned


def build_chad(matrix_9: list) -> bytes:
    """Build a chromatic adaptation tag (s15Fixed16ArrayType)."""
    tag = b"sf32"
    tag += b"\x00" * 4
    for v in matrix_9:
        tag += struct.pack(">i", int(round(v * 65536)))
    return tag  # 44 bytes, aligned


def build_cicp(cp: int, tc: int, mc: int, vr: int) -> bytes:
    """Build a CICP tag."""
    tag = b"cicp"
    tag += b"\x00" * 4
    tag += struct.pack("BBBB", cp, tc, mc, vr)
    return tag  # 12 bytes, aligned


def build_tech(sig: bytes) -> bytes:
    """Build a technology tag (signatureType)."""
    tag = b"sig "
    tag += b"\x00" * 4
    tag += sig
    return tag  # 12 bytes, aligned


def build_lumi(cd_m2: float) -> bytes:
    """Build a luminance tag (XYZType) — only Y is meaningful."""
    tag = b"XYZ "
    tag += b"\x00" * 4
    tag += struct.pack(">i", 0)                             # X = 0
    tag += struct.pack(">i", int(round(cd_m2 * 65536)))     # Y = luminance
    tag += struct.pack(">i", 0)                             # Z = 0
    return tag  # 20 bytes, aligned


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
    # Load reference profile for LUT data
    with open(REFERENCE_PROFILE, "rb") as f:
        ref_data = f.read()

    # ── Build individual tag data ────────────────────────────────────────
    desc_data = build_mluc(DESCRIPTION)
    cprt_data = build_mluc(COPYRIGHT)
    wtpt_data = build_xyz(0.964203125, 1.0, 0.824905396)  # D65 from reference
    chad_data = build_chad([
        1.047882080078125, 0.022918701171875, -0.0502166748046875,
        0.0295867919921875, 0.990478515625, -0.0170745849609375,
        -0.009246826171875, 0.01507568359375, 0.751678466796875,
    ])

    # Extract A2B and B2A LUT data from reference (these encode PQ TF + BT.2020 matrix)
    a2b0_data = extract_lut_data(ref_data, "A2B0")
    b2a0_data = extract_lut_data(ref_data, "B2A0")

    cicp_data = build_cicp(9, 16, 0, 0)
    tech_data = build_tech(b"vidm")
    lumi_data = build_lumi(PEAK_LUMINANCE_CD_M2)

    # ── Tag table ────────────────────────────────────────────────────────
    # 11 tags, but A2B0==A2B1 and B2A0==B2A1 share data (same offset)
    tags_unique = [
        (b"desc", desc_data),
        (b"cprt", cprt_data),
        (b"wtpt", wtpt_data),
        (b"chad", chad_data),
        (b"A2B0", a2b0_data),   # A2B1 will share this offset
        (b"B2A0", b2a0_data),   # B2A1 will share this offset
        (b"cicp", cicp_data),
        (b"tech", tech_data),
        (b"lumi", lumi_data),
    ]

    tag_count = 11  # desc, cprt, wtpt, chad, A2B0, A2B1, B2A0, B2A1, cicp, tech, lumi
    header_size = 128
    tag_table_size = 4 + tag_count * 12  # count(4) + entries(11*12)

    # Calculate data offsets
    data_start = header_size + tag_table_size
    # Pad data_start to 4 bytes
    if data_start % 4:
        data_start += 4 - (data_start % 4)

    # Build tag directory entries and concatenate data
    tag_data_blob = b""
    tag_entries = []  # (sig, offset, size)

    for sig, data in tags_unique:
        offset = data_start + len(tag_data_blob)
        actual_size = len(data)  # padded size
        # Find unpadded size: strip trailing zeros from padding
        # For correctness, store the actual data size before padding
        # We need original size for the tag table
        # Since pad4 may add 0-3 bytes, compute original:
        # Actually all our builders already pad, and the reference sizes
        # include padding. Let's use padded size as tag size (matches reference behavior).
        tag_entries.append((sig, offset, actual_size))

        # Add aliases (A2B1 -> A2B0, B2A1 -> B2A0)
        if sig == b"A2B0":
            tag_entries.append((b"A2B1", offset, actual_size))
        elif sig == b"B2A0":
            tag_entries.append((b"B2A1", offset, actual_size))

        tag_data_blob += data

    # ── Build tag table ──────────────────────────────────────────────────
    tag_table = struct.pack(">I", tag_count)
    for sig, offset, size in tag_entries:
        tag_table += sig
        tag_table += struct.pack(">I", offset)
        tag_table += struct.pack(">I", size)

    # ── Build header ─────────────────────────────────────────────────────
    profile_size = data_start + len(tag_data_blob)

    header = b""
    header += struct.pack(">I", profile_size)    # 0: profile size
    header += b"ADBE"                             # 4: preferred CMM (Adobe)
    header += bytes([4, 64, 0, 0])                # 8: version 4.4.0.0
    header += b"mntr"                             # 12: profile class (monitor)
    header += b"RGB "                             # 16: color space
    header += b"XYZ "                             # 20: PCS
    # 24-35: date/time (2024-01-01 00:00:00)
    header += struct.pack(">HHHHHh", 2024, 1, 1, 0, 0, 0)
    header += b"acsp"                             # 36: file signature
    header += b"APPL"                             # 40: primary platform (Apple)
    header += struct.pack(">I", 0)                # 44: profile flags
    header += b"\x00" * 4                         # 48: device manufacturer
    header += b"\x00" * 4                         # 52: device model
    header += b"\x00" * 8                         # 56: device attributes
    header += struct.pack(">I", 0)                # 64: rendering intent (perceptual)
    # 68: PCS illuminant (D50: X=0.9642, Y=1.0, Z=0.8249)
    header += struct.pack(">i", int(round(0.964203125 * 65536)))
    header += struct.pack(">i", int(round(1.0 * 65536)))
    header += struct.pack(">i", int(round(0.824905396 * 65536)))
    header += b"ADBE"                             # 80: creator
    header += b"\x00" * 16                        # 84: profile ID (filled later)
    header += b"\x00" * 28                        # 100: reserved

    assert len(header) == 128, f"Header is {len(header)} bytes, expected 128"

    # ── Assemble profile ─────────────────────────────────────────────────
    # Pad between tag table and data if needed
    padding = data_start - header_size - len(tag_table)
    profile = header + tag_table + (b"\x00" * padding) + tag_data_blob

    assert len(profile) == profile_size, f"Profile is {len(profile)} bytes, expected {profile_size}"

    # ── Compute MD5 profile ID ───────────────────────────────────────────
    # Per ICC spec: zero out bytes 44-47 (flags), 64-67 (rendering intent),
    # and 84-99 (profile ID) before computing MD5
    id_data = bytearray(profile)
    id_data[44:48] = b"\x00" * 4
    id_data[64:68] = b"\x00" * 4
    id_data[84:100] = b"\x00" * 16
    profile_id = hashlib.md5(bytes(id_data)).digest()

    # Write profile ID back
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
