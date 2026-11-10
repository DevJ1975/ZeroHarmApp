/** Links to the OSHA standard behind a citation, so anyone can read the actual rule. */
export type RegLink = { section: string; label: string; url: string };

const SECTION = /\b(19(?:10|04|26)\.\d+[a-z]?)(?=\b|\()/g;

/** OSHA's page for a section, e.g. 1910.147 -> osha.gov/laws-regs/regulations/standardnumber/1910/1910.147 */
export const regUrl = (section: string) =>
  `https://www.osha.gov/laws-regs/regulations/standardnumber/${section.split('.')[0]}/${section}`;

/** Every 29 CFR section mentioned in the texts, once each, in order: "1910.147(d)" -> 29 CFR 1910.147. */
export function regLinks(...texts: (string | null | undefined)[]): RegLink[] {
  const seen = new Set<string>();
  const out: RegLink[] = [];
  for (const text of texts) {
    for (const match of (text ?? '').matchAll(SECTION)) {
      const section = match[1];
      if (seen.has(section)) continue;
      seen.add(section);
      out.push({ section, label: `29 CFR ${section}`, url: regUrl(section) });
    }
  }
  return out;
}
