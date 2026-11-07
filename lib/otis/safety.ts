/**
 * A hard rule outside the AI: if a message sounds like someone is hurt or in danger right now,
 * the app shows "Call 911" before OTIS says anything. Small on-device models can be wrong; this can't be.
 */
const URGENT = [
  /\b(not breathing|can'?t breathe|unconscious|passed out|unresponsive|collapsed|seizure)\b/i,
  /\b(bleeding|blood everywhere|amputat|crushed|trapped|pinned|caught in)\b/i,
  /\b(electrocut|being shocked|getting shocked|stuck to|can'?t let go)\b/i,
  /\b(fire|smoke|explosion|gas leak|chemical (in|on) (my|his|her|their) (eyes?|face|skin))\b/i,
  /\b(chest pain|heart attack|stroke|heat ?stroke|overdose|fell from|fell off|fall from)\b/i,
  /\b(no respira|inconsciente|sangr|atrapad|electrocut|incendio|fuego|desmay|dolor de pecho|se cay[oó])/i,
  /\b(emergency|emergencia|911|right now|ahora mismo|help me|ay[uú]da)\b/i,
];

export const looksUrgent = (text: string) => URGENT.some((r) => r.test(text));
