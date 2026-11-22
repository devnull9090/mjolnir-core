/**
 * Keyword search over the docs, run in the browser.
 *
 * `scripts/sync-docs.mjs` cuts every published doc into chunks, one per
 * heading's own text, and writes them to `public/docs-search.json`. The search
 * palette fetches that file on first use and ranks it here, so typing costs no
 * request and search works with no Worker bindings at all. The semantic index
 * (src/lib/api/docs-search.ts) embeds the same chunks; `fuse` merges its hits
 * into these.
 *
 * Keyword search carries the docs' vocabulary, which is mostly identifiers:
 * console functions, tag fields, file names, chunk numbers. An embedding ranks
 * `mjolnir_auto` no better than any other rare string, so this is the
 * foundation and the semantic index is the layer over it, never the reverse.
 *
 * No DOM and no Next imports: `scripts/test-docs-search.mts` runs it in Node.
 */

/** `public/docs-search.json`, as sync-docs.mjs writes it. */
export type SearchIndexFile = {
  /** Names this exact content; the semantic index records the build it holds. */
  build: string;
  /** [slug, guide or note, title, section title] */
  docs: Array<[string, "g" | "n", string, string]>;
  /** [doc index, heading anchor, heading trail, text] */
  chunks: Array<[number, string, string, string]>;
};

export type DocHit = {
  /** Index into `SearchIndexFile.chunks`. */
  chunk: number;
  score: number;
  /** The index terms the query matched, for highlighting. */
  terms: string[];
  /** Found by meaning only: the keyword search did not return it. */
  semanticOnly?: boolean;
};

/**
 * Each chunk's key, `slug#anchor#part`: what names a chunk across builds. The
 * semantic index stores keys, not positions, because for the minutes between a
 * deploy and its sync it still holds the build before.
 */
export function chunkKeys(file: SearchIndexFile): string[] {
  /** How many chunks of one doc share an anchor so far: the key's last part. */
  const seen = new Map<string, number>();
  return file.chunks.map(([doc, anchor]) => {
    const base = `${file.docs[doc][0]}#${anchor}`;
    const part = seen.get(base) ?? 0;
    seen.set(base, part + 1);
    return `${base}#${part}`;
  });
}

const WORD = /[A-Za-z0-9_]+/g;
const CAMEL = /[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+/g;

/** Words that say nothing about which page is wanted. Dropped from a query that has others. */
const STOPWORDS = new Set(
  "a an and are as at be by can do does for from how i in is it my of on or that the this to what when where which with".split(
    " ",
  ),
);

/**
 * The terms a piece of text is indexed under. An identifier counts as itself
 * and as its parts: `cheat_all_weapons` is found by `weapons`, `MJOLNIRLobby`
 * by `lobby`.
 */
export function indexTerms(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.match(WORD) ?? []) {
    if (raw.length < 2) continue;
    const whole = raw.toLowerCase();
    out.push(whole);
    const parts = raw.match(CAMEL) ?? [];
    if (parts.length > 1) {
      for (const part of parts) if (part.length > 1) out.push(part.toLowerCase());
    }
  }
  return out;
}

/** A query's terms: each word once, whole. */
export function queryTerms(query: string): string[] {
  const words = [...new Set((query.match(WORD) ?? []).map((word) => word.toLowerCase()))].filter(
    (word) => word.length > 1,
  );
  const meaningful = words.filter((word) => !STOPWORDS.has(word));
  return meaningful.length > 0 ? meaningful : words;
}

/** Whether `a` and `b` are one edit apart (a typo). Both are short. */
function oneEditApart(a: string, b: string): boolean {
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0;
  let j = 0;
  let edits = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      i += 1;
      j += 1;
      continue;
    }
    edits += 1;
    if (edits > 1) return false;
    if (a.length > b.length) i += 1;
    else if (b.length > a.length) j += 1;
    else {
      // A swap of two neighbours reads as one typo, not two.
      if (a[i] === b[j + 1] && a[i + 1] === b[j]) {
        i += 2;
        j += 2;
      } else {
        i += 1;
        j += 1;
      }
    }
  }
  return edits + (a.length - i) + (b.length - j) <= 1;
}

const HEADING_WEIGHT = 3;
const TITLE_WEIGHT = 2;
/** BM25's usual constants. */
const K1 = 1.2;
const B = 0.75;
/** How much a query made of a doc's title, or a section's heading, lifts it. */
const TITLE_BONUS = 2;
const HEADING_BONUS = 0.8;
/**
 * How the semantic side weighs against the keyword side when the two are
 * merged (DocsIndex.fuse). A strong match by meaning outranks the best keyword
 * hit, which for a question is often a page that merely shares its words.
 */
const SEMANTIC_WEIGHT = 1.25;
/** The place in the semantic list at which a hit counts for half. */
const SEMANTIC_HALF_RANK = 6;
/** The least relevance at which a chunk the keywords did not find is shown at all. */
const SEMANTIC_ALONE = 0.3;
/** A guide is the page most searches want; a tie goes to it. */
const GUIDE_BOOST = 1.15;
const MAX_PER_DOC = 3;

type Posting = { chunks: number[]; weights: number[] };

export class DocsIndex {
  readonly file: SearchIndexFile;
  private readonly postings = new Map<string, Posting>();
  /** Every indexed term, sorted, for prefix lookups. */
  private readonly vocabulary: string[];
  private readonly lengths: number[];
  private readonly averageLength: number;
  private readonly lowered: string[];
  private readonly keys: string[];
  private readonly byKey = new Map<string, number>();
  private readonly titleTerms: Array<Set<string>>;

  constructor(file: SearchIndexFile) {
    this.file = file;
    this.titleTerms = file.docs.map(([, , title]) => new Set(indexTerms(title)));
    this.lengths = new Array(file.chunks.length);
    this.lowered = new Array(file.chunks.length);
    this.keys = chunkKeys(file);
    this.keys.forEach((key, chunk) => this.byKey.set(key, chunk));

    const counts = new Map<string, number>();
    let total = 0;

    file.chunks.forEach(([doc, , heading, text], chunk) => {
      const title = file.docs[doc][2];
      this.lowered[chunk] = `${heading}\n${text}`.toLowerCase();

      counts.clear();
      const body = indexTerms(text);
      for (const term of body) counts.set(term, (counts.get(term) ?? 0) + 1);
      for (const term of indexTerms(heading)) {
        counts.set(term, (counts.get(term) ?? 0) + HEADING_WEIGHT);
      }
      for (const term of indexTerms(title)) {
        counts.set(term, (counts.get(term) ?? 0) + TITLE_WEIGHT);
      }
      this.lengths[chunk] = body.length;
      total += body.length;

      for (const [term, weight] of counts) {
        let posting = this.postings.get(term);
        if (!posting) {
          posting = { chunks: [], weights: [] };
          this.postings.set(term, posting);
        }
        posting.chunks.push(chunk);
        posting.weights.push(weight);
      }
    });

    this.averageLength = total / Math.max(1, file.chunks.length);
    this.vocabulary = [...this.postings.keys()].sort();
  }

  /** The chunk's key (chunkKeys). */
  keyOf(chunk: number): string {
    return this.keys[chunk];
  }

  chunkOfKey(key: string): number | undefined {
    return this.byKey.get(key);
  }

  /**
   * The index terms a query word stands for, with how much each counts: the
   * word itself in full, a word it begins (`vehicle` for `vehicles`) for less,
   * and when neither exists a word one typo away.
   */
  private expand(word: string): Array<[string, number]> {
    const out: Array<[string, number]> = [];
    if (this.postings.has(word)) out.push([word, 1]);
    if (word.length >= 3) {
      let low = 0;
      let high = this.vocabulary.length;
      while (low < high) {
        const mid = (low + high) >> 1;
        if (this.vocabulary[mid] < word) low = mid + 1;
        else high = mid;
      }
      for (let i = low; i < this.vocabulary.length && out.length < 40; i += 1) {
        const term = this.vocabulary[i];
        if (!term.startsWith(word)) break;
        if (term !== word) out.push([term, term.length - word.length <= 2 ? 0.7 : 0.4]);
      }
    }
    if (out.length === 0 && word.length >= 4) {
      for (const term of this.vocabulary) {
        if (term[0] === word[0] && oneEditApart(word, term)) out.push([term, 0.4]);
        if (out.length >= 12) break;
      }
    }
    return out;
  }

  search(query: string, limit = 12): DocHit[] {
    const words = queryTerms(query);
    if (words.length === 0) return [];

    const total = this.file.chunks.length;
    const scores = new Map<number, number>();
    const covered = new Map<number, number>();
    const matched = new Map<number, Set<string>>();

    for (const word of words) {
      /** A chunk's best score for this word: two forms of it do not count twice. */
      const best = new Map<number, [number, string]>();
      for (const [term, weight] of this.expand(word)) {
        const posting = this.postings.get(term);
        if (!posting) continue;
        const idf = Math.log(1 + (total - posting.chunks.length + 0.5) / (posting.chunks.length + 0.5));
        for (let i = 0; i < posting.chunks.length; i += 1) {
          const chunk = posting.chunks[i];
          const tf = posting.weights[i];
          const norm = 1 - B + B * (this.lengths[chunk] / this.averageLength);
          const score = weight * idf * ((tf * (K1 + 1)) / (tf + K1 * norm));
          const before = best.get(chunk);
          if (!before || score > before[0]) best.set(chunk, [score, term]);
        }
      }
      for (const [chunk, [score, term]] of best) {
        scores.set(chunk, (scores.get(chunk) ?? 0) + score);
        covered.set(chunk, (covered.get(chunk) ?? 0) + 1);
        let terms = matched.get(chunk);
        if (!terms) {
          terms = new Set();
          matched.set(chunk, terms);
        }
        terms.add(term);
      }
    }

    const phrase = words.length > 1 ? query.trim().toLowerCase().replace(/\s+/g, " ") : "";
    const ranked: DocHit[] = [];
    for (const [chunk, raw] of scores) {
      // A chunk with every word beats one with most of them said often.
      const coverage = (covered.get(chunk) ?? 0) / words.length;
      let score = raw * coverage * coverage;
      if (phrase && this.lowered[chunk].includes(phrase)) score *= 1.6;
      const [doc, , heading] = this.file.chunks[chunk];
      // A query that names a page or a section is asking for it: "sound
      // mixer" wants the Sound mixer page over a page that mentions one.
      score *= 1 + TITLE_BONUS * named(words, this.titleTerms[doc]);
      score *= 1 + HEADING_BONUS * named(words, new Set(indexTerms(heading)));
      if (this.file.docs[doc][1] === "g") score *= GUIDE_BOOST;
      ranked.push({ chunk, score, terms: [...(matched.get(chunk) ?? [])] });
    }
    ranked.sort((a, b) => b.score - a.score || a.chunk - b.chunk);
    return spread(ranked, this.file, limit);
  }

  /**
   * Keyword hits and semantic hits as one list.
   *
   * Each side is first put on its own 0-to-1 scale. A keyword hit's is its
   * score against the best keyword hit. A semantic hit's is its `relevance`,
   * which the server sets from how near the chunk is to the query in absolute
   * terms, fading with its place in the list: the nearest chunk to a question
   * the docs do not answer is still the nearest, and must not rank as a find.
   * A chunk both searches found gets both.
   *
   * Ranks alone (reciprocal rank fusion) were tried first and failed on real
   * questions: with thirty keyword hits, the best chunk found only by meaning
   * landed below all of them, and two chunks deep in both lists beat the page
   * the question named.
   */
  fuse(
    lexical: DocHit[],
    semantic: Array<{ key: string; relevance: number }>,
    limit = 12,
  ): DocHit[] {
    const best = lexical[0]?.score ?? 0;
    const merged = new Map<number, DocHit>();
    for (const hit of lexical) {
      merged.set(hit.chunk, { ...hit, score: best > 0 ? hit.score / best : 0 });
    }
    let rank = 0;
    for (const { key, relevance } of semantic) {
      // A key this build does not have is a chunk the semantic index still
      // holds from the build before: skipped, and gone at its next sync.
      const chunk = this.byKey.get(key);
      if (chunk === undefined) continue;
      const score = (SEMANTIC_WEIGHT * relevance) / (1 + rank / SEMANTIC_HALF_RANK);
      rank += 1;
      const hit = merged.get(chunk);
      if (hit) hit.score += score;
      else if (relevance >= SEMANTIC_ALONE) {
        merged.set(chunk, { chunk, score, terms: [], semanticOnly: true });
      }
    }
    const ranked = [...merged.values()].sort((a, b) => b.score - a.score || a.chunk - b.chunk);
    return spread(ranked, this.file, limit);
  }
}

/** The share of the query's words that `terms` has, a word cut short counting as the word it begins. */
function named(words: string[], terms: Set<string>): number {
  let found = 0;
  for (const word of words) {
    if (terms.has(word)) found += 1;
    else if (word.length >= 3) {
      for (const term of terms) {
        if (term.startsWith(word)) {
          found += 0.7;
          break;
        }
      }
    }
  }
  return found / words.length;
}

/** The first `limit` hits, with no doc taking more than its share of them. */
function spread(ranked: DocHit[], file: SearchIndexFile, limit: number): DocHit[] {
  const perDoc = new Map<number, number>();
  const out: DocHit[] = [];
  for (const hit of ranked) {
    const doc = file.chunks[hit.chunk][0];
    const used = perDoc.get(doc) ?? 0;
    if (used >= MAX_PER_DOC) continue;
    perDoc.set(doc, used + 1);
    out.push(hit);
    if (out.length >= limit) break;
  }
  return out;
}

export type SnippetPart = { text: string; hit: boolean };

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** `text` cut into runs, the runs that are one of `terms` marked. */
export function highlight(text: string, terms: string[]): SnippetPart[] {
  const usable = terms.filter(Boolean).sort((a, b) => b.length - a.length);
  if (usable.length === 0) return [{ text, hit: false }];
  // A term starts a word or follows an underscore: `weapons` lights up in
  // `cheat_all_weapons`, `in` does not light up inside `rain`.
  const pattern = new RegExp(`(^|[^A-Za-z0-9])(${usable.map(escapeRegExp).join("|")})`, "gi");
  const parts: SnippetPart[] = [];
  let last = 0;
  for (let match = pattern.exec(text); match; match = pattern.exec(text)) {
    const start = match.index + match[1].length;
    if (start > last) parts.push({ text: text.slice(last, start), hit: false });
    parts.push({ text: match[2], hit: true });
    last = start + match[2].length;
    // The character before a term may also be the one before the next.
    pattern.lastIndex = last;
  }
  if (last < text.length) parts.push({ text: text.slice(last), hit: false });
  return parts;
}

/** About `width` characters of `text` around the first matched term. */
export function snippet(text: string, terms: string[], width = 190): SnippetPart[] {
  let at = -1;
  const lowered = text.toLowerCase();
  for (const term of terms) {
    const found = lowered.indexOf(term);
    if (found >= 0 && (at < 0 || found < at)) at = found;
  }
  let start = Math.max(0, at - 50);
  if (start > 0) {
    const space = text.indexOf(" ", start);
    start = space >= 0 && space < at ? space + 1 : start;
  }
  let end = Math.min(text.length, start + width);
  if (end < text.length) {
    const space = text.lastIndexOf(" ", end);
    if (space > start + width / 2) end = space;
  }
  const parts = highlight(text.slice(start, end), terms);
  if (start > 0) parts.unshift({ text: "… ", hit: false });
  if (end < text.length) parts.push({ text: " …", hit: false });
  return parts;
}
