/** Pack-owned runtime packages, checked by identity without decompressing UCAS. */
import type { ForgePack } from "./forge";

export function requiredForgePackages(pack: ForgePack): string[] {
  const names = new Set<string>();
  const root = `/Game/MJOLNIR/Forge/${pack.id}`;
  for (const block of pack.blocks) {
    for (const surface of block.surfaces ?? []) {
      if (surface.profile === "glass_cyan") names.add(`${root}/Materials/M_ForgeGlassCyan`);
      if (surface.profile === "teleporter_green") {
        names.add(`${root}/Materials/M_ForgePortalGreen`);
        names.add(`${root}/Textures/T_PortalDust`);
        names.add(`${root}/Textures/T_PortalMask`);
        names.add(`${root}/Materials/T_CE_BlackCube`);
      }
    }
  }
  return [...names].sort();
}

/** UE FPackageId: the >64-byte CityHash64 branch from ue-iostore/src/city.rs.
 * All names emitted above are ASCII and at least 66 UTF-16LE bytes long.
 * Refuse shorter/foreign inputs so this deliberately bounded port cannot be
 * mistaken for a general CityHash implementation. No Node APIs are required. */
export function forgePackageId(name: string): bigint {
  if (!/^\/Game\/MJOLNIR\/Forge\/[\x20-\x7e]+$/.test(name)) {
    throw new Error("not a namespaced Forge runtime package");
  }
  const lowered = name.toLowerCase();
  const bytes = new Uint8Array(lowered.length * 2);
  for (let i = 0; i < lowered.length; i++) bytes[i * 2] = lowered.charCodeAt(i);
  if (bytes.length <= 64) throw new Error("Forge package name is too short for the bounded hash");
  const view = new DataView(bytes.buffer);
  const u = (n: bigint) => BigInt.asUintN(64, n);
  const k1 = BigInt("0xb492b66fbe98f273"), mul = BigInt("0x9ddfea08eb382d69");
  const fetch = (i: number) => view.getBigUint64(i, true);
  const rotate = (v: bigint, shift: number) => { const n = BigInt(shift); v = u(v); return u((v >> n) | (v << (BigInt(64) - n))); };
  const mix = (v: bigint) => { v = u(v); return v ^ (v >> BigInt(47)); };
  const hash16 = (a: bigint, b: bigint) => {
    a = mix(u((u(a) ^ u(b)) * mul));
    return u(mix(u((u(b) ^ a) * mul)) * mul);
  };
  const weak = (i: number, a: bigint, b: bigint): [bigint, bigint] => {
    const w = fetch(i), x = fetch(i + 8), y = fetch(i + 16), z = fetch(i + 24);
    a = u(a + w); b = rotate(b + a + z, 21);
    const c = a;
    a = u(a + x + y); b = u(b + rotate(a, 44));
    return [u(a + z), u(b + c)];
  };
  const len = bytes.length;
  let x = fetch(len - 40), y = u(fetch(len - 16) + fetch(len - 56));
  let z = hash16(fetch(len - 48) + BigInt(len), fetch(len - 24));
  let v = weak(len - 64, BigInt(len), z), w = weak(len - 32, y + k1, x);
  x = u(x * k1 + fetch(0));
  for (let i = 0, remaining = (len - 1) & ~63; remaining; i += 64, remaining -= 64) {
    x = u(rotate(x + y + v[0] + fetch(i + 8), 37) * k1);
    y = u(rotate(y + v[1] + fetch(i + 48), 42) * k1);
    x ^= w[1]; y = u(y + v[0] + fetch(i + 40));
    z = u(rotate(z + w[0], 33) * k1);
    v = weak(i, u(v[1] * k1), x + w[0]);
    w = weak(i + 32, z + w[1], y + fetch(i + 16));
    [z, x] = [x, z];
  }
  return hash16(hash16(v[0], w[0]) + mix(y) * k1 + z, hash16(v[1], w[1]) + x);
}
