/**
 * Wwise banks a map pack carries.
 *
 * An archive never holds a `.pak`: one can hold any file in the game. A
 * vehicle's sounds travel as bare `content/<container>/<id>.bnk` members and
 * the launcher builds the `.pak` itself, so a bank can only land where the game
 * reads banks. These are the rules of crates/ue-iostore/src/bank.rs, which the
 * launcher applies again before it writes anything; change the two together.
 *
 * A shipped bank's id is refused because a map pack must not change the sound
 * of a stock vehicle on every other map. See docs/map_distribution.md.
 */
import shippedBanks from "../../generated/shipped-banks.json";

/** Far above a vehicle's bank (an engine's four loops are 2.3 MB), to stop a
 *  member being a way to carry something else. */
export const MAX_BANK_BYTES = 16 * 1024 * 1024;
/** How many banks one release may carry. */
export const MAX_BANKS = 32;
/** All of one release's banks: the scan holds them in memory to read them. */
export const MAX_ALL_BANKS_BYTES = 48 * 1024 * 1024;

/** The bank format this game reads. */
const BANK_VERSION = 150;
const SHIPPED = new Set<number>(shippedBanks);

export function isShippedBank(id: number): boolean {
  return SHIPPED.has(id);
}

/** A bank member's container and id. The container is a plain name and the id
 *  a number as it writes itself, so a path can't climb out of the launcher's
 *  cache and two members can't be the same bank. */
export function bankMember(path: string): { container: string; id: number } | null {
  const found = /^content\/([A-Za-z0-9_-]+)\/(0|[1-9][0-9]*)\.bnk$/.exec(path);
  if (!found) return null;
  const id = Number(found[2]);
  return id <= 0xffffffff ? { container: found[1], id } : null;
}

/** Why `bank` isn't a bank of ours, or null: every section in bounds and of a
 *  known kind, the header's id `id`, every media entry inside DATA, every HIRC
 *  record inside HIRC. This keeps a member to being a bank; it is not a proof
 *  that Wwise will read one safely, which is why BANK_UPLOADS exists. */
export function checkBank(id: number, bank: Uint8Array): string | null {
  if (isShippedBank(id)) return `bank ${id} is one the game ships`;
  const view = new DataView(bank.buffer, bank.byteOffset, bank.byteLength);
  const u32 = (at: number) => (at + 4 <= bank.length ? view.getUint32(at, true) : null);
  let at = 0;
  let data: number | null = null;
  let index: { body: number; size: number } | null = null;
  let hirc: { body: number; end: number } | null = null;
  while (at < bank.length) {
    const size = u32(at + 4);
    if (size === null) return "a section is cut short";
    const body = at + 8;
    const end = body + size;
    if (end > bank.length) return "a section runs past the end";
    const magic = String.fromCharCode(...bank.subarray(at, at + 4));
    if (magic === "BKHD" && at === 0) {
      if (size < 8 || u32(body) !== BANK_VERSION) return "not a version 150 bank";
      if (u32(body + 4) !== id) return `the header's id is not ${id}`;
    } else if (magic === "DIDX" && !index) {
      index = { body, size };
    } else if (magic === "DATA" && data === null) {
      data = size;
    } else if (magic === "HIRC" && !hirc) {
      hirc = { body, end };
    } else {
      return "a section of a kind banks here don't have, or a second one";
    }
    at = end;
  }
  if (bank[0] !== 0x42 || bank[1] !== 0x4b || bank[2] !== 0x48 || bank[3] !== 0x44) return "no BKHD";
  if (index) {
    if (index.size % 12 !== 0) return "DIDX is not whole entries";
    if (data === null) return "DIDX with no DATA";
    for (let i = 0; i < index.size / 12; i++) {
      const offset = u32(index.body + 12 * i + 4);
      const length = u32(index.body + 12 * i + 8);
      if (offset === null || length === null) return "DIDX is cut short";
      if (offset + length > data) return "a media entry runs past DATA";
    }
  }
  if (!hirc) return "no HIRC";
  const count = u32(hirc.body);
  if (count === null) return "HIRC is cut short";
  at = hirc.body + 4;
  for (let i = 0; i < count; i++) {
    const size = u32(at + 1);
    if (size === null) return "a HIRC record is cut short";
    at += 5 + size;
    if (at > hirc.end) return "a HIRC record runs past HIRC";
  }
  return at === hirc.end ? null : "HIRC has bytes past its records";
}

/** Whether an account may publish a release that carries banks, by the
 *  BANK_UPLOADS switch. Unset or misspelt means the narrowest: moderators and
 *  admins. "trusted" adds the authors who skip the map queue; "anyone" leaves it
 *  to the scan and the queue. */
export function mayPublishBanks(
  policy: string | undefined,
  user: { role: string; trust_level?: number },
  trustedLevel: number,
): boolean {
  if (policy === "anyone") return true;
  if (user.role !== "user") return true;
  return policy === "trusted" && (user.trust_level ?? 0) >= trustedLevel;
}
