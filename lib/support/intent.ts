/**
 * Rules, not AI, that tell "something is wrong with the app" apart from a safety question. When this says yes, OTIS
 * shows a tech-support entry word for word and offers to file a report. It never changes the 911 rail in
 * lib/otis/safety.ts: that rail runs first, on every message, and when it fires no support path is taken at all.
 *
 * A miss here is cheap (the person can still tap "Report a problem", and a clear support entry is still found by
 * lib/support/answer.ts). A false alarm is not: it takes a real safety question away from the safety answers. So the
 * rule is narrow. A message counts only when it NAMES THE APP outright: the app, OTIS, the Zero Harm app, my phone,
 * this screen, la app, la aplicación del teléfono. Then it must join that name to a failure word (crashed, froze,
 * stuck, not working, won't load, no funciona, se cierra) with nothing but small words in between, or ask for help
 * with it ("problem with the app", "can't open OTIS").
 *
 * Words that also have a floor or paperwork meaning never count on their own: screen, sheet, sign in, notification,
 * download, ticket, glitch, buggy, lagging, report a problem, support. A gas monitor has a screen, a confined space has
 * a sign-in sheet, lockout requires notification, pipe has lagging, a concrete buggy is a cart.
 * "The app says the guard is broken" does not count either: "says" and "guard" sit between "app" and "broken".
 *
 * mentionsSafety() is the other half: a message that names a hazard, a machine, a chemical, PPE, lockout or a permit is
 * answered from the safety entries even when it also names the app.
 *
 * Neither of those decides on its own. The support paths also need onlyAboutTheApp() (the pure-app gate, further down):
 * every word of the message must be one of the app's words, so "the app froze and mike is not moving" gets the safety
 * answer although no hazard word is in it. mentionsSafety() stays as a second check; the gate does not depend on it.
 *
 * The text is put in lower case with accents taken off before matching, so every pattern below is plain a-z and
 * works for "aplicación" and "aplicacion" alike. Patterns allow phone typing: no apostrophes ("cant", "wont").
 * No pattern here carries the /g flag except the strip list, which is only ever used with replace().
 */

/** Lower case, no accents, straight apostrophes, single spaces. "La aplicación se cerró" becomes "la aplicacion se cerro". */
function plain(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[‘’´`]/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Look-alikes that are not this app. They are taken out of a copy of the message before the rules run, the way the
 * 911 rail strips "fire extinguisher". Otis is also an elevator maker, "OTIS, the guard is stuck" is a person talking
 * to OTIS, not about it, other apps on site are not this one, and the phone on the wall is not the person's phone.
 */
const NOT_THE_APP = [
  /^(hey|hi|hello|ok|okay|yo|hola|oye|buenas|buenos dias)[ ,]+otis\b[ ,:.!-]*|^otis\s*[,:!-]+\s*|,\s*otis\s*[?.!]*$/g,
  /\botis (elevators?|escalators?|lifts?)\b|\b(elevador(es)?|ascensor(es)?) otis\b/g,
  /\b(emergency|mass|fire|alarm|evacuation) notifications?( systems?)?\b/g,
  /\b(sistemas? de )?notificacion(es)? de (emergencias?|incendios?|evacuacion)\b/g,
  /\b(permit|gas monitor|monitor|detector|crane|forklift|scale|timekeeping|time ?clock|payroll|company|vendor|maintenance|work ?order|cmms|loto|lockout|badge|scheduling|hr|other|another|different) apps?\b/g,
  /\bapps? (de|del|para) (permisos?|bloqueo|mantenimiento|la empresa|la compania|nomina)\b/g,
  /\b(emergency|break ?room|wall|desk|office|land ?line|courtesy|call ?box|radio) phones?\b|\btelefonos? de (emergencia|la oficina|la pared)\b/g,
];

const strip = (text: string) => NOT_THE_APP.reduce((left, phrase) => left.replace(phrase, ' '), plain(text));

// ---- The pieces the patterns are built from ---------------------------------------------------------

/** Not, can't, won't and the rest, with or without the apostrophe. */
const NOT =
  "(?:not|never|no longer|won'?t|will not|doesn'?t|does not|didn'?t|did not|isn'?t|is not|aren'?t|are not|wasn'?t|can'?t|cannot|can not|couldn'?t|could not|wouldn'?t|unable to|refuses? to|fail(?:s|ed|ing)? to|stopped|quit)";

/** Can't, won't, "won't let me": the app is stopping the person. Narrower than NOT, so "never sign in for a coworker" stays a safety question. */
const CANT =
  "(?:can'?t|cannot|can not|couldn'?t|could not|won'?t|will not|wouldn'?t|unable to|not able to|(?:won'?t|doesn'?t|does not|didn'?t|not|isn'?t) let(?:ting)? me|fail(?:s|ed|ing)? to)";

/** A, the, my and friends, in English and Spanish. */
const DET = '(?:(?:the|this|that|my|your|our|a|an|any|la|el|las|los|esta|este|mi|tu|su|una|un)\\s+)?';

/**
 * The app itself, named outright. Not "notification", "download", "sign-in sheet" or "zero harm" on their own: those
 * are also lockout, permit and safety-program words. "La aplicación del bloqueo" and "the application of the lock"
 * are about how a lock is applied, so "aplicacion de/del ..." and "application of ..." do not count.
 */
const APP_NOT_OTIS =
  '(?:(?:zero ?harm\\s+|zeroharm\\s+|trainovate\\s+)?apps?|zeroharm|' +
  'aplicacion(?:es)?(?!\\s+(?:de|del)\\s+(?!(?:zero ?harm|otis|trainovate|telefono|celular)\\b))|' +
  '(?:the|this|my|your|zero ?harm|mobile|phone)\\s+application(?!\\s+of\\b)|chat ?bot|' +
  'otis (?:app|download|update|model|chat|setup)|(?:my|this) (?:phone|cell ?phone|cell|iphone|android)|(?:mi|este) (?:telefono|celular|cel))';
const APP = `(?:${APP_NOT_OTIS}|otis)`;

/** The app named anywhere in the message. The parts below ("screen", "video", "sheet") count only with it. */
const NAMES_APP = new RegExp(`\\b(?:${APP_NOT_OTIS}|(?:in|on|inside|from|en|con|de) otis)\\b`);

/** Words that only ask, after a name: "OTIS is it safe to ...", "OTIS does the guard ...". Those are questions to OTIS. */
const ASKING = '(?!\\s+(?:it|that|this|there|these|those|the|a|an|my|your|our|his|her|he|she|they|we|i|you)\\b)';

/**
 * People talk to OTIS by name ("OTIS my harness is broken"), so "OTIS" followed by a failure word only counts when the
 * very next word is a helper or the failure itself: "OTIS is stuck", "OTIS won't answer", "OTIS no responde". A helper
 * that starts a question ("OTIS is that valve dangerous", "OTIS is it still broken if I tape the cord") does not count.
 */
const OTIS_THEN =
  "otis(?=\\s+(?:(?:is|isn'?t|was|has|had|will|would|does|did|can)" + ASKING + "|keeps?|kept|just|still|always|never|got|gets|won'?t|doesn'?t|didn'?t|can'?t|cannot|couldn'?t|" +
  'stopped|stops|quit|not|crash\\w*|fr(?:o|e|ee|ea)z(?:e|es|ed|en|ing|in|n)?\\b|hang\\w*|hung|died|lag\\w*|fail\\w*|glitch\\w*|takes|took|went|goes|shuts?|closes|closed|' +
  'no|se|esta|sigue|anda|ya|quedo|falla|truena|trono|marca|da|tiene)\\b)';

/** Parts of the app that share a name with things on the floor. These need a failure only software has. */
const PART =
  '(?:screens?|pages?|videos?|episodes?|talks?|links?|settings|keyboard|signatures?|sheets?|pdfs?|handouts?|pantallas?|paginas?|episodios?|platicas?|charlas?|enlaces?|ajustes|firmas?)';

/** "Keeps crashing", typed fast too: "keeps crashin", "keeps kickin me out", "kept frezing". */
const KEEPS_FAILING =
  '(?:keeps?|kept) (?:on )?(?:crash(?:ing|in)|clos(?:ing|in)|fre?e?z(?:ing|in)|load(?:ing|in)|spin(?:ning|nin|in)|stop(?:ping|pin)|restart(?:ing|in)|' +
  "quit(?:ting|tin)|fail(?:ing|in)|shut(?:ting|tin) (?:down|off)|buffer(?:ing|in)|glitch(?:ing|in)|lag(?:ging|gin)|(?:logg|kick|sign|boot)(?:ing|in) me out|saying|asking)";

/** What a broken app does, in English. Each of these needs the app named next to it. */
const FAIL_EN =
  '(?:crash\\w*|fr(?:o|e|ee|ea)z(?:e|es|ed|en|ing|in|n)?\\b|stuck|brok(?:e|en)|busted|glitch\\w*|bugg?(?:y|ed|ing|s)?|lag(?:s|gy|ging|ged)?|slow|hang(?:s|ing)?|hung|dead|died|down|' +
  'blew up|messed up|acting (?:up|weird|funny|strange)|trippin\\w*|tripping|wildin\\w*|unusable|useless|unresponsive|spinning|buffering|blank|missing|gone|disappear\\w*|vanish\\w*|' +
  'fail(?:s|ed|ing|ure)?|errors?|problems?|issues?|trouble|sucks|wrong|(?:in|on) the wrong language|too (?:much|small|big|slow|tiny)|' +
  'no (?:connection|signal|internet)|offline|says? (?:update|no connection|offline|error|update needed|i need to update)|' +
  `${NOT}\\s+(?:even\\s+|be\\s+|been\\s+)?(?:work\\w*|load\\w*|open\\w*|start\\w*|play\\w*|send\\w*|sav\\w*|download\\w*|install\\w*|updat\\w*|sync\\w*|respond\\w*|answer\\w*|show\\w*|clos\\w*|scroll\\w*|let\\w*|com\\w+ (?:up|on|through)|turn\\w* on|connect\\w*|finish\\w*|run\\w*|launch\\w*|display\\w*|refresh\\w*|appear\\w*|arriv\\w*|go\\w* through|type|typing)|` +
  KEEPS_FAILING + '|' +
  'clos(?:es|ed|ing)|shuts? (?:down|off)|force[- ]?clos\\w*|(?:don\'?t|do not) (?:work\\w*|load\\w*|open\\w*|play\\w*)|' +
  '(?:went|goes|gone|going|turned|turns) (?:blank|black|white|dark|gr[ae]y)|tak(?:es|ing) forever|timed? out|loading forever|stopped|stops|quits?)';

/** The same, in Spanish, with the accents already off. */
const FAIL_ES =
  '(?:no (?:me |se |nos )?(?:funciona|sirve|abre|carga|jala|responde|contesta|prende|inicia|arranca|deja|descarga|aparecen?|llegan?|guarda|envia|reproduce|ve|oye|actualiza|sincroniza|conecta|entra|muestra|permite)|' +
  'se (?:me )?(?:cierra|cerro|cayo|traba|trabo|congela|congelo|cuelga|colgo|sale|salio|apaga|apago|reinicia|bloquea|bloqueo|borro|queda (?:pegada|trabada|congelada|cargando|en blanco|colgada)|quedo (?:pegada|trabada|congelada|cargando|en blanco|colgada))|' +
  '(?:esta|anda|va|sigue|quedo)\\s+(?:muy\\s+|bien\\s+|super\\s+|tan\\s+)?(?:lent[ao]|bugue\\w*|bugead[oa]|trabad[ao]|congelad[ao]|pegad[ao]|descompuest[ao]|rot[ao]|fallando|mal|caid[ao]|colgad[ao]|bloquead[ao]|en blanco|muert[ao])|' +
  'se (?:me )?ve (?:bien |muy |super |toda )?(?:rar[ao]|diferente|extran[ao]|mal)|se (?:me )?(?:queda|quedo) pensando|se (?:me )?(?:pone|puso) (?:en blanco|negra|gris)|' +
  'fall(?:a|as|o|ando)|errores|problemas?|truena|trono|crashe\\w*|bugue\\w*|bugead[oa]|(?:sigue|esta|sale|aparece) en ingles|(?:marca|da|sale|tiene)\\s+(?:un\\s+|una\\s+)?(?:error|problema|falla|bug))';

const FAIL = `(?:${FAIL_EN}|${FAIL_ES})`;

/** Failures only software has. Safe to pair with "screen", "video" or "talk". */
const SOFT_FAIL =
  `(?:${NOT}\\s+(?:even\\s+)?(?:load\\w*|open\\w*|play\\w*|scroll\\w*|download\\w*|show\\w*|display\\w*|sav\\w*|send\\w*|sync\\w*|refresh\\w*|respond\\w*)|` +
  'fr(?:o|e|ee|ea)z(?:e|es|ed|en|ing|in|n)?\\b|crash\\w*|glitch\\w*|blank|buffering|loading forever|' + KEEPS_FAILING + '|' +
  '(?:went|goes|gone|going|turned|turns) (?:blank|black|white|dark|gr[ae]y)|' +
  'no (?:me |se )?(?:carga|abre|ve|reproduce|guarda|aparece|muestra|responde)|se (?:me )?(?:congel\\w+|trab\\w+|cuelga|colgo|quedo? (?:congelada|trabada|pegada|en blanco|negra|cargando))|en blanco|congelad[ao]|trabad[ao])';

/**
 * The small words allowed between the app and its failure: "the app [on my phone just keeps] crashing". No word that
 * names a thing is in here, so "the app says the guard is broken" does not join "app" to "broken".
 */
const SMALL =
  "(?:is|isn'?t|are|aren'?t|was|were|has|have|had|been|be|being|it|it'?s|its|that|just|still|always|now|again|also|really|so|totally|completely|constantly|" +
  'suddenly|randomly|sometimes|often|and|on|in|my|the|phone|tablet|iphone|ipad|android|for|me|us|today|since|after|update|itself|' +
  'get|gets|got|getting|to|will|would|did|does|do|even|' +
  'weekly|nomas|bien|' +
  'se|me|ya|siempre|todavia|aun|otra|vez|de|del|nuevo|y|en|mi|telefono|celular|cel|muy|solo|sola|nunca|casi|veces|ahora|hoy|desde|ayer)';
const GAP = `(?:[\\s,.;:!-]+${SMALL}){0,5}[\\s,.;:!-]+`;

/** "Problem with the app", "bug in OTIS", "ayuda con la aplicación". */
const TROUBLE = "(?:problems?|issues?|trouble|errors?|bugs?|glitch(?:es)?|difficulty|something(?:'?s| is)? (?:wrong|off|up|not right)|help|problemas?|error(?:es)?|fallas?|fallos?|ayuda|broncas?)";
const WITH = '(?:with|in|on|using|about|inside|opening|loading|downloading|logging into|signing into|con|en|de|del|al usar|usando|para usar)';

/** "Can't open the app", "not getting notifications", "no puedo abrir la app". */
const CANT_DO =
  `(?:${NOT}\\s+(?:even\\s+)?(?:open|load|use|start|download|install|update|get into|get in to|log into|log in to|sign into|sign in to|access|find|see|close|launch|run|get|getting|receive|receiving|turn on|turn off)|` +
  '(?:get|getting|got|receive|receiving|have|see) no|' +
  'no (?:puedo|pude|podemos|me deja|me dejo|deja|logro) (?:abrir|usar|entrar a|entrar en|descargar|instalar|actualizar|iniciar|ver|encontrar|cerrar|acceder a)|' +
  'no (?:me |nos )?(?:llegan?|aparecen?|salen?|suenan?))';

/** "Crashes when I open the app", "se cierra cuando abro la app". */
const WHEN = '(?:when|whenever|every time|each time|as soon as|after|while|if|cuando|cada vez que|siempre que|despues de|al)';

// ---- The rules --------------------------------------------------------------------------------------

/**
 * A request for support that names the app: "report a bug in the app", "contact app support", "ticket for OTIS".
 * A bare "report a problem", "file a ticket" or "contact support" is not here: plants file maintenance tickets and
 * report problems to supervisors. lib/support/answer.ts still shows the "How to report a problem" entry for those
 * when the message holds nothing about a hazard.
 */
const ASKS_FOR_SUPPORT = [
  /\b(report|reporting|reported|file|filing|submit|log|send|sending)\s+(a |an |this |that |the |my |another )?app (problem|issue|error|crash|bug)\b/,
  new RegExp(`\\bticket\\s+(?:for|on|about|with)\\s+${DET}${APP}\\b`),
  /\b(app|zero ?harm|otis|trainovate) (tech |technical |customer )?support\b|\bsupport (for|with|from) (the |this |your )?(zero ?harm |otis |trainovate )?app\b/,
  /\b(contact|contacting|call|email|reach|talk to|speak to|speak with|message|write to)\s+trainovate\b/,
  /\bsoporte (tecnico )?(de|para|con) (la app|la aplicacion|otis|zero ?harm)\b|\bsoporte de trainovate\b/,
];

/** Things only the app or the phone does, said with the app or the phone named. */
const ONLY_AN_APP = [
  /\b(my |this |the )?phone (is |gets |got |runs |feels )?(so |really |very |too |burning )?(hot|warm)\b|\b(my |this |the )?phone (is )?overheat\w*/,
  /\b(mi |el |este )?(telefono|celular|cel) (se )?(calienta|esta (muy )?caliente)\b/,
  /\botis\b.{0,30}\b(wrong|incorrect|bad|false|dangerous|unsafe|outdated) (answers?|info|information|advice|response|reply)\b/,
  /\b(wrong|incorrect|bad|false) (answers?|info|information|advice) (from|by) otis\b/,
  /\botis (is|was|got it|got this|got that|seems|sounds) (wrong|incorrect|confused|lying|making (things|stuff|it) up)\b/,
  /\botis\b.{0,30}\b(respuesta|informacion) (incorrecta|equivocada|mala|falsa|erronea)\b|\botis (se equivoco|esta mal|esta equivocado|invento)\b/,
];

/** The app joined to a failure word, in either order. */
const APP_AND_FAILURE = [
  new RegExp(`\\b(?:${APP_NOT_OTIS}|${OTIS_THEN})${GAP}${FAIL}`),
  new RegExp(`\\b${TROUBLE}\\s+${WITH}\\s+${DET}${APP}\\b`),
  new RegExp(`\\b${CANT_DO}\\s+(?:(?:to|into|in to|on|any|more|new|the new)\\s+)?${DET}${APP}\\b`),
  new RegExp(`\\b${FAIL}\\s+${WHEN}\\s+(?:(?:i|we|you|yo)\\s+)?(?:\\w+\\s+){0,2}?${DET}${APP}\\b`),
  new RegExp(`\\b${FAIL}\\s+(?:on|in|at|during|from|inside|en|con)\\s+${DET}${APP}\\b`),
  // Spanish puts the failure first: "no funciona la app", "se cierra la aplicación", "no me llegan los avisos de la app".
  new RegExp(`\\b${FAIL_ES}\\s+${DET}${APP}\\b`),
  new RegExp(`\\b(?:${FAIL_ES}|${CANT_DO})\\s+(?:\\w+\\s+){1,3}?(?:de|del|en)\\s+${DET}${APP}\\b`),
  new RegExp(`\\b(?:broken|buggy|slow|laggy|glitchy|crashing|frozen|stuck|failed|dead)\\s+${APP}\\b`),
  // "Zero Harm" is also a safety goal ("zero harm is not working at our plant"), so on its own name it needs a
  // failure only software has.
  new RegExp(`\\bzero ?harm${GAP}${SOFT_FAIL}`),
  // "This screen" or "this page" is the one the person is looking at: the app's.
  new RegExp(`\\b(?:this|esta)\\s+(?:screen|page|pantalla|pagina)${GAP}${FAIL}`),
];

/**
 * Parts of the app that share a name with things on the floor: a gas monitor has a screen, a permit is a sheet, a
 * fire door has a fusible link. These count only when the app is also named ("the talk video in the app won't play").
 */
const NEEDS_THE_APP = [
  new RegExp(`\\b${PART}${GAP}${SOFT_FAIL}`),
  new RegExp(`\\b${NOT}\\s+(?:even\\s+)?(?:load|open|play|scroll|see|close|share|save|send|download|find|get out of|get off|leave|exit)\\s+${DET}${PART}\\b`),
  new RegExp(`\\b${CANT}\\s+(?:even\\s+)?(?:log ?in|log me in|sign ?in|sign me in|log ?out|download|sync)\\b`),
  /\b(blank|white|black|gr[ae]y) screen\b|\bpantalla (en blanco|negra|blanca|congelada|trabada)\b/,
  /\b(stuck|frozen|hung) (on|at) (the )?(download\w*|loading(?! (dock|bay|area|zone|ramp|door))|splash|setup|starting)\b/,
  /\bglitch\w*|\bbuggy\b|\blagg(y|ing)\b|\bforce[- ]?clos\w*|\bloading forever\b/,
  /\b(logs?|logged|signs?|signed|kicks?|kicked|boots?|booted) me out\b/,
  /\b(burning|eating|ate|drains?|draining|uses?|using) (up )?(all |too much |a lot of )?(of )?(my )?(data|battery)\b/,
];

const PROBLEM: readonly RegExp[] = [...ASKS_FOR_SUPPORT, ...ONLY_AN_APP, ...APP_AND_FAILURE];

/**
 * True when the message names the app and says it is going wrong, or asks for the app's support by name. Rules only,
 * English and Spanish. It says nothing about emergencies: run looksUrgent first, and when it fires take no support path.
 */
export function looksLikeAppProblem(text: string): boolean {
  const rest = strip(text);
  return PROBLEM.some((rule) => rule.test(rest)) || (NAMES_APP.test(rest) && NEEDS_THE_APP.some((rule) => rule.test(rest)));
}

/** How-to questions that name the app itself. Kept narrow: "what does OTIS say about ladders" is a safety question. */
const ABOUT_THE_APP: readonly RegExp[] = [
  /\b(in|on|inside|with|using|use|open|install|update|set ?up|share|delete|uninstall|download)\s+(the |this |your |my )?(zero ?harm )?app\b/,
  /\b(en|con|usar|uso|usa|abrir|instalar|actualizar|compartir|borrar|descargar)\s+(la |esta |mi )?(app|aplicacion)\b/,
  /\bwhat('?s| is) (otis|zero ?harm|this app|the app)\b|\bwhat (does|can) (otis|zero ?harm|this app|the app) do\b|\bwho (is|made|makes|built) (otis|zero ?harm|this app|the app)\b/,
  /\bhow (does|do) (otis|zero ?harm|this app|the app) work\b|\bhow do (i|we) (use|set ?up|start|update|turn (on|off)) (otis|zero ?harm|this app|the app)\b/,
  /\b(is|does) (otis|zero ?harm|this app|the app) (free|private|safe|offline|an ai|a person|a robot|real|cost|work offline|work without|need (signal|wi-?fi|internet)|use (data|my data)|send|share|save|keep)\b/,
  /\bque es (otis|zero ?harm|esta app|la app|esta aplicacion|la aplicacion)\b|\bquien es otis\b|\bcomo (funciona|se usa|uso|usar) (otis|zero ?harm|esta app|la app|esta aplicacion|la aplicacion)\b/,
  /\b(otis|zero ?harm|la app|la aplicacion) (es|esta) (gratis|privad[ao]|segur[ao])\b/,
];

/**
 * True for a plain question about the app itself ("what is OTIS", "how do I share a sheet in the app"). OTIS answers
 * these from a support entry, word for word, when one matches. It is not a problem report.
 */
export function asksAboutApp(text: string): boolean {
  const rest = strip(text);
  return ABOUT_THE_APP.some((rule) => rule.test(rest));
}


/**
 * Hazards, machines, chemicals, PPE, lockout, permits, injuries and the rules about them, in English and Spanish. A
 * message with any of these is answered from the safety entries, even when it also names the app or reads like a
 * complaint: "the app froze, is it ok to enter the tank", "I need to report a problem, the guard on the saw is
 * missing". Lean wide: a safety answer to an app question costs a tap on "Report a problem"; the other way round
 * costs a safety answer.
 */
const SAFETY: readonly RegExp[] = [
  // vehicles, loads, docks, lifting
  /\b(fork ?lifts?|fork ?trucks?|pallet jacks?|pallets?|racks?|racking|loading docks?|docks?|dock (plates?|boards?|locks?|levell?ers?)|trailers?|trucks?|cranes?|hoists?|slings?|rigging|lifts?|heavy loads?|load (limits?|capacity|charts?)|chocks?|scissor lifts?|aerial lifts?|man ?lifts?|boom lifts?|concrete|elevators?|escalators?|elevador(es)?|ascensor(es)?)\b/,
  // machines and guarding
  /\b(guards?|guarding|guard ?rails?|e-? ?stops?|emergency stops?|light curtains?|interlocks?|presses|press brakes?|brakes?|saws?|blades?|grinders?|lathes?|drills?|mixers?|conveyors?|augers?|balers?|compactors?|shredders?|crushers?|hoppers?|chutes?|robots?|robotic|machines?|machinery|equipment|hmi|plc|rollers?|gears?|belts?|chains?|pinch points?|moving parts|vibrating screens?)\b/,
  /\b(the|a|that|this|punch|hydraulic|power|drill|brake|printing) press\b|\bpress (cycled|came|operator|brake)\b|\b(the|a) die\b|\bdie (sets?|blocks?|change)\b|\breach (in|into|inside)\b/,
  // stop buttons and kill switches ("the stop button doesn't work")
  /\b(stop buttons?|kill switch(es)?|botone?s? de paro|paro de emergencia)\b/,
  // heights
  /\b(ladders?|scaffold\w*|harness\w*|lanyards?|lifelines?|fall protection|fall arrest|falls?|fell|roofs?|mezzanines?|skylights?|floor holes?|leading edge|heights?|anchors?)\b/,
  // spaces and permits
  /\b(tanks?|vessels?|silos?|bins?|pits?|trench\w*|excavat\w*|manholes?|vaults?|sewers?|confined|permits?|hot work|attendant|entrant)\b/,
  // lockout and energy
  /\b(lockout|lock ?out|lock (it|them) out|locked out(?! of (the |my |this )?(app|account|otis|zero ?harm))|tag ?out|loto|padlocks?|tags?|(a|the|my|his|her|their|your|our|that|this|each|personal|own) locks?|locks? (on|off))\b/,
  /\b(energ\w*|de-?energ\w*|re-?energ\w*|stored energy|isolat\w*|breakers?|panels?|wires?|wiring|cords?|extension cords?|outlets?|volts?|voltage|electric\w*|arc flash|busbars?|bus bars?|live parts?|gfci|grounding)\b/,
  // chemicals and air
  /\b(chemicals?|sds|msds|data sheets?|acids?|caustic|bleach|ammonia|chlorine|solvents?|degreasers?|acetone|toluene|xylene|propane|gas|gases|fumes?|vapou?rs?|dust|silica|asbestos|lead (paint|dust|exposure)|mold|spills?|spilled|leak\w*|hazcom|hazard communication|labels? on|corrosive|flammable|combustible|toxic|exposure)\b/,
  /\b(gas|air|oxygen|o2|h2s|co|multi-?gas|4-?gas|four gas) (monitors?|meters?|detectors?|tests?|readings?)\b|\bdetectors?\b|\bbump tests?\b|\bcalibrat\w*/,
  /\b(data|spec|safety|product|chemical) sheets?\b|\bsheets? (for|on) (?!(the |my |our |this |today'?s? )?(crew|talk|toolbox|meeting|sign|team|group|week|monday|day|today|records?|app|phone|otis|ipad)\b)\w+/,
  // PPE
  /\b(ppe|gloves?|goggles|safety glasses|glasses|face shields?|hard hats?|helmets?|respirators?|masks?|ear ?plugs?|hearing protection|safety vests?|hi-? ?vis|safety (shoes|boots)|steel ?toes?|work boots)\b/,
  // harm, rules and rights
  /\b(hazards?|hazardous|unsafe|danger\w*|injur\w*|hurt|accidents?|incidents?|near miss(es)?|fatal\w*|osha|violations?|citations?|first aid|cpr|aed|eye ?wash|fire|fires|smoke|extinguishers?|evacuat\w*|emergenc\w*|heat (stress|stroke|illness|exhaustion|rash|cramps)|cold stress|noise|hearing|weld\w*|grind\w*|torch\w*|cutting|burns?|steam|boilers?|pressure|hydraulic\w*|pneumatic|compressed air|valves?|pipes?|piping|(?:the|pipe|steam|insulation|asbestos) lagging|lagging (?:on|off|is falling|insulation)|pinch\w*|crush\w*|amputat\w*|jsa|jha|inspect\w*|maintenance|work orders?|unsafe work|refus\w* to work|stop work|my rights|retaliat\w*|whistle ?blow\w*|safety (complaints?|concerns?|issues?|problems?|violations?|rules?|officer|manager|lead|committee|meeting|training|data|switch|valve|guard|program))\b/,
  // Spanish
  /\b(montacargas|patin|tarimas?|muelles?|rampas?|camion(es)?|gruas?|polipastos?|eslingas?|cadenas?|cargas? pesadas|escaleras?|andamios?|arnes|linea de vida|barandal(es)?|(la|las|una|sin|de|esta|sus?) guardas?|guardas? de seguridad|paro de emergencia|cortina de luz|prensas?|frenos?|sierras?|cuchillas?|esmeril\w*|torno|taladros?|mezcladoras?|banda transportadora|bandas?|maquinas?|maquinaria|rodillos?|engranes?)\b/,
  /\b(tanques?|silos?|fosas?|zanjas?|excavacion\w*|espacios? confinados?|permisos? de (trabajo|entrada)|bloqueo|candados?|etiquet\w*|energia|electric\w*|cables?|voltaje|quimic\w*|hojas? de (datos|seguridad)|acidos?|cloro|amoniaco|gas|vapores|polvo|silice|asbesto|derrames?|fugas?|epp|guantes|lentes|gafas|careta|casco|respirador|mascarilla|tapones|chaleco|botas|peligr\w*|insegur\w*|herid\w*|lesion\w*|lastim\w*|accidentes?|incidentes?|casi accidente|violacion|primeros auxilios|rcp|lavaojos|fuego|incendios?|humo|extintor\w*|evacua\w*|golpe de calor|ruido|sold\w*|caidas?|techos?|alturas?|valvulas?|tuberias?|vapor|presion|hidraulic\w*|mantenimiento|inspecc\w*|seguridad)\b/,  // A lock, or unlocking one: "who can take off a coworker's lock", "can I unlock it", "is it locked". Not a talk or
  // the app being locked, and not the phone's lock screen.
  /\bunlock\w*\b(?!\s+(?:the |a |this |that |next |new |more |all )?(?:talks?|episodes?|videos?|charlas?|platicas?|content|app|account|phone|screen|otis|features?)\b)|\blocks?\b(?!\s*screen)|^\W*(?:is (?:it|this|that) |it'?s |its |who )?locked(?: it)?\W*$|\bwho locked\b/,
  // The body: illness, pain and heat or cold on a person ("my chest hurts", "he is dizzy", "she is throwing up").
  /\b(chest|breath\w*|dizz\w*|light-? ?headed|faint\w*|pass(?:es|ed|ing)? out|black(?:ed|ing)? out|vomit\w*|throw(?:ing|s)? up|threw up|puk(?:e|ed|ing)|nause\w*|sweat\w*|clammy|numb(?:ness)?|tingl\w*|shak(?:ing|y)|shiver\w*|disoriented|drooping|slurr\w*|seizures?|sick(?! of)|pain\w*|hurts?|hurting|aches?|aching|bleed\w*|blood\w*|bruis\w*|swell\w*|swollen|sting\w*|stung|bites?|biting|bitten|bit by|asthma|allerg\w*|diabet\w*|insulin|overdos\w*|panic\w*|dehydrat\w*|frostbite|hypotherm\w*|unconscious)\b/,
  /\b(he|she|they|he'?s|she'?s|they'?re|hes|shes|seems?|looks?|getting|got|acting) (so |really |very |all )?confused\b/,
  /\b(his|her|their|my|your|our|\w+'s)\s+(fingers?|thumbs?|hands?|toes?|foot|feet|arms?|legs?|eyes?|head|ears?|neck|face|skin)\b|\bred everywhere\b/,
  // Violence, threats and weather ("there is a bomb threat", "tornado warning"). "Kill the app" is closing it.
  /\b(knife|knives|guns?|gunshots?|shooter|weapons?|bombs?|threat\w*|ending it|end it all|suicid\w*|self-? ?harm|tornado\w*|earthquakes?|lightning|thunder\w*|floods?|flooding|hurricanes?|storms?|wildfires?|lockdown|shelter in place)\b|\bkill\w*\b(?!\s+(?:the |this |my )?(?:app|otis|application)\b)/,
  // Heat, cold, ovens, smells, batteries. "Heat card" is the app's weather card.
  /\bheat\b(?!(?: index)? card)|\bhot (work|surfaces?|weather|days?|environments?|conditions|equipment|pipes?|oil|water|liquids?|metal|grease)\b|\b(too|very|really|so|extremely) hot (out|outside|in here|to work|today|on the (floor|line|dock|roof))\b|\bit'?s (too |so |very |really )?hot( out| outside| in here)?\W*$/,
  /\b(cold|freezers?|fre+z+e?rs?|freezr|walk-? ?ins?|coolers?|temperatures?|wind ?chill|furnaces?|ovens?|kilns?|fryers?|smell\w*|odou?rs?|stinks?|lithium|sparks?|sparking|smoldering)\b|\bbatter(y|ies)\b.{0,20}\b(smok|spark|swell|swoll|leak|burn|hiss)\w*/,
  /\b(not enough|no|more) (room|space) (to|for) (work|move|walk|stand|get|breathe)\b|\bno hay espacio para (trabajar|moverse|caminar)\b|\b(storage|supply|boiler|electrical|mechanical|server|locker|chemical|tool|cold|walk-? ?in) rooms?\b/,
  // Weather outside, and whether something is allowed: rules, laws, what is required, "is it safe to keep working".
  /\b(snow\w*|ice|icy|rain\w*|wind|windy|hail|fog\w*|sun|sunburn|uv|outdoors?|outside)\b|\bsafe (for (me|us|him|her|them|you) )?to\b/,
  /\b(rules?|regulations?|laws?|legal|illegal|allowed|required|requirements?|standards?|osha|damage\w*)\b|\b(training|osha|injury|illness|300|inspection|exposure|medical) (records?|logs?)\b/,
  // The job itself: the boss, pay, hours ("I want to talk to a human about my job").
  /\b(my|our|his|her|their) (job|boss|supervisor|manager|foreman|employer|pay|paycheck|wages?|hours|shift|overtime)\b|\bjefe\b|\bmi (trabajo|supervisor|empleador|sueldo|pago|turno|horario)\b/,
  // Bites: "a bug bit me"
  /\bbit (me|him|her|them|us|my|his)\b/,
  // Signing for another person, and records that are not true ("can you sign my name", "but I wasn't there")
  /\bsign\w* (your|his|her|their|someone'?s|somebody'?s) name\b|\b(can|could|will|would) you sign (my|me|it|for)\b|\bsign\w* (in |my name |it )?for (you|me)\b|\bbut i (wasn'?t|was not|didn'?t|did not|never)\b/,
  // Rights and people at work: harassment, someone signing for another person, HR.
  /\b(harass\w*|bully\w*|discriminat\w*|human resources|hr|at work|on the job|(signed|forged|faked|signing) (my|his|her|their|someone'?s|somebody'?s|a coworker'?s) (name|signature|initials)|sign(ed|ing)? (in )?for (someone|somebody|a coworker|another (person|worker)|him|her|them)|without (asking|permission|my permission))\b/,
  // Spanish: the body, violence, weather, heat and cold, rights.
  /\b(marea\w*|mareo|vomit\w*|nause\w*|pecho|duele\w*|dolor\w*|desmay\w*|sangr\w*|calor|frio|temperatura\w*|hielo|horno\w*|olor\w*|huele|apesta|cuchill\w*|pistola\w*|armas?|bombas?|amenaz\w*|tornado\w*|temblor\w*|terremoto\w*|inundac\w*|tormenta\w*|rayos?|acoso|acosa\w*|hostiga\w*|recursos humanos|en el trabajo|picad\w*|mordid\w*|piquete|alergi\w*|asma|diabet\w*|convuls\w*|temblando|sudando|sudor|confundid[oa]|desorientad[oa]|enferm[oa]|me siento mal|se siente mal)\b/,
];

/**
 * Words that are a safety or rights question on their own ("do I get a break", "the lights went out", "can I leave",
 * "necesito un permiso") but also fit an app entry ("OTIS is taking a short break", "why are there christmas lights",
 * "la app no tiene permiso para la cámara"). They count only when the app is not named and `unless` does not match.
 */
const SAFETY_UNLESS_APP: readonly { hit: RegExp; unless?: RegExp }[] = [
  { hit: /\b(?:a|my|our|the|any|lunch|rest|water|bathroom|restroom|meal|cool-? ?down|paid|unpaid|short|smoke|\d+|ten|fifteen|thirty)(?: minute| min)? breaks?\b|\bbreaks? (?:time|room|area|rules?|laws?)\b|^\W*breaks?\W*$|\bdescans\w*/ },
  { hit: /\blights?\b|\bluz\b|\bluces\b/, unless: /\b(?:christmas|holiday|xmas|string|fairy|twinkle|festive|party|navidad\w*|navidenas?) lights?\b|\bluces (?:de navidad|navidenas?)\b/ },
  { hit: /\b(?:can|may|could|should|do|must) (?:i|we|they|he|she) (?:leave|go home|walk off)\b|\bleave (?:work|early|the (?:site|job|floor|plant|area|building|line))\b|^\W*(?:can i )?leave\W*$|\b(?:me quiero|puedo|podemos|me puedo) (?:ir|salir|irme|retirar)\w*/ },
  { hit: /\bpermisos?\b/, unless: /\b(?:camaras?|notificacion\w*|ubicacion|fotos?|microfono)\b/ },
  { hit: /\bsafety\b|\bshifts?\b|^\W*(?:i )?(?:quit|quitting|salir)\W*$|\b(?:can|should|may) i quit\b|\bquit (?:my|this|the) job\b/ },
];

/** The app named outright, or OTIS: then the words above are about the app. */
const APP_OR_OTIS = new RegExp(`\\b(?:${APP_NOT_OTIS}|otis)\\b`);

/**
 * Another person named as the subject of a second clause, after a comma, "and" or "but": "the app crashed and he is dizzy", "this
 * screen froze and the guy next to me is not okay", "la app no funciona y mi compañero está mareado". Such a message
 * is not only about the app, so it goes to the safety answers. "It crashes on my coworker's phone too" does not count.
 */
const SOMEONE_ELSE = new RegExp(
  '(?:[,;.!?]|\\band\\b|\\bbut\\b|\\bwhile\\b|\\by\\b|\\bpero\\b|\\bmientras\\b)\\s*(?:(?:my|the|a|our|this|that|mi|el|la|un|una|nuestro)\\s+)?' +
    '(?:he|she|they|coworker|co-worker|buddy|partner|someone|somebody|guy|man|woman|worker|operator|driver|friend|companer[oa]|alguien|ella|trabajador[a]?|senor[a]?)\\b' +
    "(?:\\s+[\\w']+){0,3}?\\s+(?:is|are|was|were|got|gets|has|had|have|feels?|felt|looks?|seems?|can'?t|cannot|won'?t|isn'?t|is not|just|keeps?|started|stopped|fell|collapsed|threatened|esta|tiene|se|no puede|anda|le)\\b",
);

/**
 * "Él" (he) is "el" once the accent is off, the same as the article. An article is never followed by a verb or a
 * pronoun, so "el" right before one is a person: "la app se cerró y él no sale", "y el se quedó pegado".
 */
const EL_IS_HE =
  /(?:^|[,;.!?]|\by\b|\bpero\b|\bmientras\b|\bque\b)\s*el\s+(?:no|ya|se|me|te|le|lo|nos|va|sigue|esta|estaba|anda|tiene|queda|quedo|sale|salio|entro|aparece|ve|puede|es|era|fue|dice|dijo|grita)\b/;

/**
 * A number standing for people: "the app is stuck and so is 1 of mine", "my phone froze and 1 is gone", "otis 2 are
 * down", "y 1 no sale". Not "error 404" or "version 2 is out": those never follow "and", "y", a comma or "otis".
 */
const A_NUMBER_IS_SOMEONE = /(?:^|\band\b|\by\b|\bbut\b|\bpero\b|\bso is\b|[,;.!?]|\botis)\s*\d+\s+(?:is|are|was|were|got|of|esta|estan|no|se|has|have|cant|wont|isnt|arent|still|just|down|missing)\b/;

/** True when the message names the app itself or OTIS ("the app", "otis", "my phone", "la aplicación"), not only a part of it. */
export function namesTheApp(text: string): boolean {
  return APP_OR_OTIS.test(strip(withoutCalling(text)));
}

/**
 * What only software does, said with no subject: "it keeps crashing", "se cierra sola", "wont load", "no carga". Used
 * by the report flow, where the app is already the topic, to take such a description without asking twice. "Stuck",
 * "down", "running" and "mal" are not here: a person or a machine is those too.
 */
const SOFTWARE_FAILS =
  /\b(?:crash\w*|fr(?:e|ee|ea)z(?:e|es|ing|in)|froze|frozen|glitch\w*|lagg\w*|buffer\w*|(?:wont|doesnt|didnt|not|never|cant|wouldnt) (?:even )?(?:load|open|play|save|send|sync|download|update|install|work|show|respond|scroll|refresh)\w*|clos(?:es|ed|ing) (?:by itself|on its own|itself|every time|when|whenever)|keeps? (?:closing|crashing|freezing|loading|spinning|restarting)|se (?:me )?(?:cierra|cerro|traba|trabo|congela|congelo|cuelga|colgo|reinicia)|no (?:me |se )?(?:carga|abre|funciona|sirve|descarga|guarda|jala|actualiza|reproduce))\b/;

/** True for a description that says only what software does wrong (see SOFTWARE_FAILS). */
export function saysSoftwareFails(text: string): boolean {
  return SOFTWARE_FAILS.test(words(text));
}

/** True when the message names another person as the subject of a clause (see SOMEONE_ELSE). */
export function aboutSomeoneElse(text: string): boolean {
  const rest = plain(text);
  return SOMEONE_ELSE.test(rest) || EL_IS_HE.test(rest) || A_NUMBER_IS_SOMEONE.test(rest);
}

/**
 * True when a description typed for a report is not only about the app (onlyAppWords), holds a hazard, or names
 * someone else, so it must not be filed as an app report: "the app froze and the forklift has no brakes", "the app
 * froze and the floor is slippery", "the app crashed when I opened the lockout talk" ("lockout" is not one of the
 * app's words; the person can still send it as written after Go on).
 */
export function hazardInReport(text: string): boolean {
  return !onlyAppWords(text) || aboutSomeoneElse(text) || mentionsSafety(text);
}

/**
 * True when the message names a hazard, a machine, a chemical, PPE, lockout, a permit, an injury or a safety rule.
 * Such a message goes to the safety answers even when it also names the app; OTIS adds a small "Report a problem"
 * link under the answer so a real app problem can still be reported.
 */
export function mentionsSafety(text: string): boolean {
  const rest = plain(text);
  if (SAFETY.some((rule) => rule.test(rest))) return true;
  if (APP_OR_OTIS.test(strip(text))) return false;
  return SAFETY_UNLESS_APP.some(({ hit, unless }) => hit.test(rest) && !(unless && unless.test(rest)));
}

// ---- The pure-app gate ------------------------------------------------------------------------------

/**
 * The tech-support paths (the report offer, a help entry shown in place of the safety answer) run only for a message
 * that is about the app AND NOTHING ELSE. That is checked with a closed list of words, not a list of hazards: after
 * lower case, accents and punctuation are taken off, every word left must be one of the app's words below. One word
 * that is not ("mike", "floor", "slippery", "tobillo", "bleding", "hours") and the message is not only about the app,
 * so it gets the safety answer, with the small "Report a problem" link under it when it also names the app.
 *
 * A list of hazards can never be complete: "the app froze and mike is not moving" has no hazard word in it at all.
 * A list of the app's own words can be, because the app is small. So the vocabulary below holds only the app's
 * names, its screens and features, the words for what goes wrong with software, and the small words of a question.
 * It holds no people (he, she, coworker, guy, names), no body, no place, no equipment, no chemical, no weather, no
 * time or pay words, and not fire, smoke, hot, cold, water, floor, break or lock. A few of those appear only inside
 * a fixed app phrase ("heat card", "christmas lights", "the talk is locked", "OTIS is taking a short break").
 *
 * A word that also means something on the floor is taken only inside an app phrase, never on its own: sign (a stop
 * sign), button (an e-stop), sheet (a safety data sheet), support (a brace), load (a crane load), card, link, switch,
 * Monday and Christmas (days of work), la cámara (a walk-in cold room), un aviso (a notice on the wall). No phrase
 * holds a wildcard, so a phrase never lets an unknown word through ("the X talks" is not a talk title: "my dude talks
 * funny"). A few sayings are made only of app words but are about a person, a machine or a right ("im not ok", "so
 * am i", "it wont stop", "before i go in", "can you sign my name", "i had contact with it", "do i have to work"):
 * those are listed in NOT_ABOUT_THE_APP and keep the message from the support paths too.
 *
 * The small words that carry an event or a person in a hazard sentence are not app words on their own either: on, off,
 * out, get, got, let, went, came, coming, shut, take, close, saw, and Spanish "el" (also "él", he, once the accent is
 * off). Neither are the app's parts that are also things on the floor or at work: screen, video, settings, ajustes,
 * pantalla, signature, firma, report, reportar, contacto, records. Each is taken only inside a fixed app phrase (JOINERS
 * and APP_PHRASES below: "on my phone", "logs me out", "got the notification", "the video won't play", "app settings",
 * "my signature won't save", "report a problem"), so "it shut on me", "get me out", "it got me", "la app se cerró y él
 * no sale", "can I take the screen off" and "do I need a signature to start" are not about the app.
 *
 * Typos are forgiven only for the app's own long words ("crashd", "frezing", "notificaton"): one letter left out,
 * added or swapped with its neighbour, and in its longest names one letter changed ("aplicasion"). A hazard word is
 * never matched loosely, and "freezer", "frezer" and "freezr" are not "freezing".
 */

/**
 * The app's nouns, for the small words below that are taken only right before one: "on my phone", "el video",
 * "got the notification". The noun itself is still checked on its own rules afterwards ("screen", "sheet" and "video"
 * need their own app phrase), so a joiner never lets a word through.
 */
const APP_NOUN =
  '(?:app|apps|application|otis|zero ?harm|zeroharm|trainovate|phone|phones|iphone|android|ipad|tablet|cell|cellphone|celular|cel|telefono|movil|device|' +
  'screen|screens|page|pages|tab|tabs|menu|settings|setting|sheet|sheets|talk|talks|video|videos|episode|episodes|crew|group|monday|toolbox|weekly|' +
  'wifi|wi|data|account|profile|button|link|loading|login|log|sign|signin|update|updates|download|downloads|downloading|setup|splash|home|' +
  'notifications?|notifs?|reminders?|pdf|photo|camera|keyboard|chat|internet|signal|storage|email|password|idioma|minuto|correo|boton|enlace|' +
  'nombre|perfil|mensaje|error|problema|lunes|episodio|contenido|texto|teclado|numero|codigo|espanol|ingles|historial|reporte|tema|icono|modo|chatbot)';
const DETS = '(?:(?:my|the|this|your|a|an|his|her|our|that|every|each|any|all|all my|no|new|those|these|more|today|todays|first|last|next|main|same|el|la|mi|tu|su|un|una) )*';

/**
 * Small words that also carry an event or a person in a hazard sentence ("it shut on me", "get me out", "it got me",
 * "something went off", "won't let go", "la app se cerró y él no sale"). None of them is an app word on its own any
 * more; each is taken only inside one of these fixed app phrases, which are cut before the app phrases below.
 */
const JOINERS: readonly RegExp[] = [
  // Round 6: "get" only before what the app sends ("i didnt get the sign in email", "never got the code")
  /\b(?:get|got|getting|gotten|receive|received|receiving)(?= (?:the |a |my |an |any |no )?(?:sign in |signin |login |log in |magic |verification |confirmation |new )?(?:email|emails|link|links|code|codes|text|texts|notification|notifications|notifs?|reminder|reminders|update|updates)\b)/g,
  // "on my phone", "stuck on the loading screen", "tap on", "turn on notifications". Never "on me", "on it", "still on".
  new RegExp(`\\bon(?= ${DETS}${APP_NOUN}\\b)`, 'g'),
  /\b(?:tap|tapped|tapping|taps|click|clicked|clicking|clicks|log|logged|logging|logs|keep|keeps|kept) on\b|\b(?:on and off|off and on)\b/g,
  // "turn off crash reports", "turn on notifications". Not "turn it off": that is a machine as often as the phone.
  new RegExp(`\\b(?:turn|turns|turned|turning|switch|switched|switching) (?:on|off)(?= ${DETS}(?:(?:monday|push|app|otis|crash|toolbox|weekly) )*(?:notifications?|notifs?|reminders?|sounds?|alerts?|reports?|dark|feedback|updates?|wifi|wi|data|otis|app|location|camera|spanish|english|include)\\b)`, 'g'),
  /\b(?:turned|switched) (?:my phone|the phone|the app|otis) off and (?:back )?on(?: again)?\b|\bturned it off and (?:back )?on again\b/g,
  // "off the app", "kicks me off", "log off", "the app shuts off"
  new RegExp(`\\boff(?= (?:of )?${DETS}(?:app|otis|phone|account|wifi|data|notifications?|notifs?|reminders?)\\b)`, 'g'),
  /\b(?:log|logs|logged|logging|kick|kicks|kicked|kicking|kickin|boot|boots|booted|booting|throws|threw)(?: me| us| you)? off\b|\b(?:shut|shuts|shutting) (?:down|off)\b/g,
  // "logs me out", "kicked out of my account", "out of space", "figure out"
  /\b(?:log|logs|logged|logging|kick|kicks|kicked|kicking|kickin|boot|boots|booted|booting|time|times|timed|timing|throws|threw)(?: me| us| you)? out\b/g,
  /\bout of (?:space|storage|memory|date|sync)\b|\b(?:find|found|figure|figured|fill|filled|filling|zoom|zoomed|print|printed|grayed|greyed) out\b/g,
  new RegExp(`\\bout(?= of ${DETS}(?:app|account|otis|talk|video|chat|sheet|screen|page)\\b)`, 'g'),
  // "got the Monday notification", "get otis", "gets stuck", "get it to load". Never "get me out", "it got me".
  new RegExp(`\\b(?:get|gets|got|getting|gotten)(?= ${DETS}(?:(?:monday|toolbox|weekly|talk|push|app|otis|new|crash) )*(?:notifications?|notifs?|reminders?|emails?|updates?|codes?|links?|alerts?|messages?|answers?|replies|reply|spanish|english|app|otis|weather|talks?|videos?|episodes?|data|info|account|pdf|copy|signal|wifi|internet|storage|space|errors?|reports?|sheet|sheets)\\b)`, 'g'),
  /\b(?:get|gets|got|getting|gotten)(?= (?:stuck|frozen|deleted|erased|lost|removed|wiped|logged|kicked|signed|booted|past|into|in to|updated|an error|a error|this error|the error|error|to (?:the |my )?(?:settings|menu|page|tab|screen|app|talk|profile|account|sheet)|it to (?:load|work|open|download|play|save|sign|show|update))\b)/g,
  // "won't let me sign in", "lets me save". Never "let me out", "let me in", "won't let go".
  /\b(?:let|lets|letting) (?:me|us)(?= (?:log|save|send|download|share|print|type|use|see|change|update|pick|choose|add|edit|delete|finish|start|watch|play|scroll|tap|click|open|enter my|select|reset|install|upload|join|switch|turn|into the app|in to the app|into otis)\b)/g,
  // "went to settings", "went black". Never "went in", "went off".
  new RegExp(`\\bwent(?= (?:to|into|in to) ${DETS}(?:settings|menu|page|tab|screen|app|profile|account|talk|talks|video|home|sheet|crew|otis)\\b)`, 'g'),
  /\bwent (?:blank|black|white|dark|gr[ae]y|away|missing|wrong|weird|crazy|haywire)\b/g,
  /\b(?:comes|came|coming|come|comin) up(?= (?:blank|empty|white|black|with|as|in english|in spanish|again|every|when|an error|error)\b)/g,
  // "takes forever", "taking too long"
  /\b(?:takes?|took|taking|takin)(?: (?:so|too|a|really|way|like|super))* (?:forever|long|ages|a while|minutes|a long time|a minute|so long)\b/g,
  // Closing, only the app's or OTIS's ("the app keeps closing", "close the app"); a door that closes is not the app
  new RegExp(`\\bclose(?: out of)?(?= ${DETS}(?:app|otis|talk|video|chat|screen|page|tab|menu|window|aplicacion)\\b)`, 'g'),
  /\b(?:crash\w*|fr(?:o|e|ee|ea)z\w*|glitch\w*|freezes) (?:and|or|then) clos(?:es|ed|ing)\b|\bit(?: (?:just|keeps|kept|always|randomly|suddenly|then|still|also|sometimes|constantly))* clos(?:es|ed|ing|in)\b/g,
  // "the app is buggy", never "the buggy" (a concrete cart)
  /(?<=\b(?:is|so|really|super|very|too|kinda|real|app|otis|its|getting|being|more|been|was|are) )buggy\b|\bbuggy(?= (?:app|otis|application)\b)/g,
  // Spinning, only a loading wheel ("it keeps spinning", "spinning forever"), never "it's spinning" on its own
  /(?<=\b(?:keeps?|kept|just|still|loading|wheel|circle|icon|otis|app|is) )spin(?:s|ning|nin|in)?\b|\bspin(?:s|ning|nin|in)?(?= (?:forever|wheel|circle|nonstop)\b)/g,
  // log in, battery drain, "el video", "esa info"
  /\blogs?(?= (?:in|into|in to|me|back)\b)/g,
  /\bdrain(?:s|ed|ing)?(?= (?:(?:my|the|all|all my|so much|a lot of|too much) )*(?:battery|data|phone)\b)|\bbattery drain\w*/g,
  new RegExp(`\\bel(?= ${APP_NOUN}\\b)`, 'g'),
  /\b(?:esa|ese|esta|este)(?= (?:info|informacion|respuesta|charla|pagina|opcion|pregunta|app|aplicacion|video|boton|error|mensaje|pantalla|seccion|hoja)\b)/g,
  /\b(?:se esta|sigue|esta|se queda|se quedo|lleva|no termina de|tarda en|tarda mucho en) descarg(?:ando|ar)\b/g,
  // "no descarga", "no se descarga": the verb, never "una descarga" (an electric shock) or "la descarga no para"
  /\b(?:no|ya no|nunca|todavia no|aun no) (?:se |me |nos )?descargan?\b/g,
];

/**
 * App phrases that hold a word the gate does not take on its own. Each is removed before the words are checked, and
 * each names a part of the app, so it also counts as the message naming the app (see onlyAboutTheApp). Used only
 * with replace(), so the /g flag is safe here.
 *
 * Words with a second meaning on the floor are taken only inside one of these: a sign is also a stop sign, a button
 * an e-stop, a sheet a safety data sheet or a permit, support a beam or a brace, a load a load on a crane, Monday or
 * Christmas a day of work. "The sign is missing", "the stop button doesn't work", "where is the sheet", "the support
 * is broken", "the load is hanging" and "do I have to work Monday" are not about the app.
 */
const APP_PHRASES: readonly RegExp[] = [
  // A screen, only the app's or the phone's: "the screen goes white", "stuck on the loading screen", "this screen froze".
  // Never "the screen" on its own: a guard, a sieve and a face shield have one ("can I take the screen off").
  /\b(?:(?:the|this|my|that|a|an) )?(?:(?:home|lock|login|log in|sign in|signin|loading|splash|start|starting|main|first|next|last|setup|welcome|crew sign in|same|otis|app|phone|download|downloading|update|error) )+screens?\b|\b(?:this|my) screens?\b/g,
  /\b(?:(?:the|my|that|a) )?screens?(?= (?:(?:is|are|was|were|just|keeps|kept|still|always|goes|went|turns|turned|stays|stayed|gets|got|go|going|keep|randomly|suddenly) )*(?:fr(?:o|e|ee|ea)z\w*|blank|black|white|gr[ae]y|dark|stuck|glitch\w*|flicker\w*|lag\w*|crash\w*|loading|spinning|unresponsive|(?:not|wont|doesnt|isnt) (?:loading|load|responding|respond|working|work|changing|change|moving|move|scrolling|scroll|showing|show|open|opening))\b)/g,
  /\b(?:la|esta|mi|una|en la|de la) pantallas?\b/g,
  // A video, only the talk's: "the video won't play", "watch the talk video". Never "take a video of it".
  /\b(?:notifications?|notifs?|reminders?|emails?|alerts?|talks?|updates?|videos?|episodes?|codes?|links?|replies|reply|answers?|monday minutes?)(?: (?:are|is|arent|isnt|not|dont|doesnt|didnt|never|stopped|wont|still|keep|keeps|kept|just|no longer|even|ever|always|usually))* (?:coming|comin|come|came|comes)(?: (?:up|through|thru|in))?\b/g,
  /\b(?:(?:the|this|that|a|my|talk|monday|toolbox|episode|el|un|los|las) )*videos?(?= (?:(?:is|are|was|were|keeps|kept|still|just|wont|will not|doesnt|does not|didnt|did not|isnt|is not|arent|not|never|always|no|se|me|ya|sigue|esta) )*(?:play\w*|load\w*|buffer\w*|fr(?:o|e|ee|ea)z\w*|stuck|start\w*|open\w*|show\w*|work\w*|stop\w*|black|blank|lag\w*|glitch\w*|crash\w*|sound|audio|skip\w*|paus\w*|restart\w*|carga|abre|reproduce|traba|trabo|congela|congelo|funciona|sirve|ve|oye|aparece|sale)\b)/g,
  /\b(?:play|plays|playing|watch|watching|watched|open|opening|opened|load|loading|find|download|downloading|pause|replay|rewatch|skip|ver|abrir|abro|descargar|reproducir) (?:the |a |this |that |my |el |un |los |the talk |talk )?videos?\b/g,
  /\b(?:talk|monday|toolbox|episode|app|otis) videos?\b|\bvideos? (?:in|on|from|for|of) (?:the |this |my |la |el )?(?:app|otis|talk|talks|monday|episode|charla|aplicacion)\b|\bvideos? (?:de|del) (?:la )?(?:app|aplicacion|charla|otis)\b/g,
  // Settings, only the app's or the phone's: "app settings", "in settings", "settings in the app". Never "change the
  // settings" on its own: a machine has settings too.
  /\b(?:app|phone|otis|notification|notifications|privacy|language|account|feedback|sound|zero ?harm|iphone|android) settings?\b|\bsettings? (?:in|on|of|for) (?:the |my |this )?(?:app|phone|otis|iphone|android)\b/g,
  /\b(?:in|open|opened|opening|go to|went to|went into|go into|goto|tap|tapped|under|from|through|via|find) (?:the |my )?settings\b|\bsettings (?:page|menu|tab|screen|button|icon|gear|app)\b|\bsetting up\b/g,
  /\b(?:los )?ajustes (?:de|del) (?:la app|la aplicacion|otis|telefono|celular|cel)\b|\ben (?:los )?ajustes\b|\b(?:abr\w*|ir a|ve a|voy a|entr\w* a|busc\w*) (?:los )?ajustes\b/g,
  // A signature, only on the sheet in the app: "my signature won't save", "signatures disappear", "la firma no se
  // guarda". Never "do I need a signature to start" or "puedo entrar sin firma".
  /\b(?:(?:my|the|a|your|all|all the|our|crew|every|his|her) )?(?:signatures?|sigs)(?= (?:(?:keep|keeps|kept|are|is|was|were|got|get|just|still|wont|will not|doesnt|does not|didnt|did not|isnt|is not|arent|not|never|always|all) )*(?:disappear\w*|vanish\w*|deleted|erased|sav\w*|show\w*|load\w*|send\w*|sync\w*|clear\w*|stick|stay|stays|upload\w*)\b)(?: (?:(?:keep|keeps|kept|are|is|was|were|got|get|just|still|wont|will not|doesnt|does not|didnt|did not|isnt|is not|arent|not|never|always|all) )*(?:disappear\w*|vanish\w*|deleted|erased|lost|gone|missing) (?:from|on|in|off) the sheets?\b)?/g,
  /\b(?:lost|lose|losing|deleted|erased|cleared|redo|clear|add|draw|save|saved|change|fix|delete|erase) (?:my |the |a |all my |all the |all |our )?(?:signatures?|sigs)\b|\b(?:signatures?|sigs) (?:box|pad|field|line|on the sheet|in the app)\b/g,
  /\b(?:la |mi |las |mis |su |sus )?firmas?(?= (?:no )?(?:se )?(?:me )?(?:guard\w*|borr\w*|desaparec\w*|perd\w*|sale|aparece|carga|envia|queda|quedo|pierde|ve)\b)|\bse (?:me |nos |le )?(?:borr\w*|perdi\w*|desaparec\w*|guard\w*) (?:la |las |mi |mis )?firmas?\b|\b(?:guardar|guarda|guardo|perdi) (?:la |las |mi |mis )?firmas?\b/g,
  // Reporting, only a problem with the app ("report a problem", "report a bug", "crash reports", "my reports"). Never
  // "how can I report", "i reported and nothing happened", "a quién reporto", "tengo que reportar".
  /\breport(?:ing|ed)? (?:a |an |the |this |that |another )?(?:app |otis )?(?:problem|bug|issue|glitch|crash|error)s?\b|\bcrash reports?\b|\breports? (?:tab|screen|page|button|link)\b|\bmy reports\b|\breport (?:this|that|the) answer\b|\b(?:reply|replied|answer|answered|response) (?:to )?my report\b/g,
  /\breport(?:ar|o|e) (?:un|el|este|una) (?:problema|bug|error|falla|fallo)(?: (?:de|con|en) (?:la app|la aplicacion|otis))?\b|\bmis reportes\b|\breportes? de (?:fallas?|errores|cierre|la app)\b|\b(?:apag\w*|desactiv\w*|activ\w*) (?:los |las )?reportes\b|\breportar esta respuesta\b/g,
  // Contact details, never "hay contacto" (touching a chemical)
  /\b(?:informacion|info|datos) de contacto\b/g,
  // Closing and going down, only the app's or OTIS's
  /\b(?:the )?(?:app|otis|phone|application|aplicacion|zero ?harm)(?: (?:just|keeps|kept|always|randomly|suddenly|then|still|keeps on|will|would|also|sometimes|constantly|now|itself))* (?:clos(?:es|ed|ing|in)|force clos\w*)\b/g,
  /\b(?:app|otis|zero ?harm|server|servers|site|website) (?:just |has |had )?went down\b/g,
  // A talk not out yet, notifications turned off, taking the group photo
  /\b(?:talk|talks|episode|episodes|video|videos|update|version|monday minute|minute|issue|weekly)(?: (?:is|isnt|is not|arent|are not|not|wasnt|still not|aint))? out yet\b/g,
  /\b(?:notifications?|notifs?|reminders?|sounds?|alerts?|otis|crash reports?)(?: (?:is|are|was|were|got|keep|keeps|still|all)(?: turned| switched)?| turned| switched) (?:on|off)\b(?! or (?:taking|on)\b)/g,
  /\b(?:turn|turns|turned|turning|switch|switched) (?:the |my |all |all the |those |these )?(?:monday |push |app |otis )?(?:notifications?|notifs?|reminders?|crash reports?|sounds?|alerts?) (?:on|off)\b/g,
  /\b(?:take|takes|taking|takin|took)(?: (?:a|the))? group photos?\b|\bgroup photos?(?: (?:wont|will not|doesnt|does not|didnt|did not|isnt|not|never))? (?:take|takes|taking|took)\b/g,
  // Names and features. Monday and the holiday only as the app's own ("the Monday Minute", "the holiday look").
  /\bzero ?harm weekly\b|\bregulatory alerts\b|\bmonday minutes?\b|\bminuto del lunes\b|\bzero hour\b|\bzero ?harm\b|\btoolbox talks?\b|\bholiday (look|theme|lights?)\b/g,
  /\bmonday (?:talks?|notifications?|notifs?|videos?|episodes?|reminders?)\b|\b(?:charlas?|platicas?|notificacion(?:es)?|avisos?|videos?) del lunes\b/g,
  /\b(heat|heat index|weather|weather and heat|weather and the heat) cards?\b|\btarjeta del? (clima|calor)\b|\b(christmas|xmas|holiday|festive|string) lights\b|\bluces (de navidad|navidenas)\b/g,
  /\bknowledge base\b|\b(?:crew|worker|team|group) sign ?in\b|\bkill(?:s|ed|ing)? (?:the |this |my )?(?:app|otis|application)\b|\bsign ?in sheets?\b|\bhojas? de asistencia\b|\bgroup photo(?: buttons?)?\b|\bfoto (del|de) grupo\b/g,
  // "The sign in link", "the sign up page": the app's, said with "the"
  /\b(?:the|a|this|that|my|no) sign ?(?:in|up) (?:links?|pages?|screens?|buttons?|codes?|emails?|forms?)\b/g,
  // "La charla de hoy sigue bloqueada"
  /\b(?:la |las |esta )?(?:charlas?|platicas?) (?:de hoy|del lunes|de la semana|nueva) (?:esta |sigue |siguen |estan )?bloquead[ao]s?\b/g,
  // Signing in, never a sign on the wall: "sign in", "sign out", "signs me out", "sign back in"
  /(?<!\b(?:the|a|no|that|this|any|stop|warning|exit|caution|those|these|street|road|danger|safety) )\bsign(?:ed|ing|s)? ?(?:in|out|up)(?: links?)?\b(?! (?:there|here|top|front|by|on|over|ahead)\b)|\b(?:the|a|no|that|this|any) sign ?(?:in|up)(?= (?:sheets?|links?|pages?|screens?|buttons?|forms?|codes?|emails?|is|isnt|wont|doesnt|keeps|kept|wasnt|not|never|will|failed|fails|broken|broke|stuck)\b)|\bsign(?:ed|ing|s)? (?:me |you )?back in\b|\bsigns? me (?:out|off)\b/g,
  // A sheet, only the app's: the crew sheet, Save sheet, a sheet that will not save or send
  /\b(?:crew|save|saved|saving|group|team) sheets?(?: (?:to|in) (?:my )?records)?\b|\bsheets? (?:to|in) (?:my )?records\b/g,
  /\b(?:save|send|share|print|saving|sending|sharing|printing) (?:the |my |a |this |that |our |all the |all )?(?:crew |sign in |signin )?sheets?\b/g,
  /\bsheets? (?:is |was |are |were |still |just )?(?:not |wont |will not |doesnt |does not |didnt |did not |never |isnt |wasnt |cant )?(?:saving|save|saved|sending|send|sent|syncing|sync|synced|uploading|upload|uploaded|printing|print|sharing|share|shared)\b/g,
  /\bse guardan? (?:la |las )?hojas?\b|\blas hojas (?:no )?se guardan\b/g,
  // The app's support, never a support beam: "tech support", "contact support", "soporte técnico"
  /\b(?:tech|technical|app|customer|otis|trainovate|zero ?harm) support\b|\bsupport (?:team|ticket|tickets|email|line|number|chat|desk|staff|page)\b/g,
  /\b(?:contact|contacting|call|calling|email|emailing|reach|reaching|message|chat with|talk to|number for|email for) support\b/g,
  /\bsoporte (?:tecnico|de (?:la app|la aplicacion|otis|trainovate|zero ?harm))\b|\b(?:contact\w*|llam\w*|escrib\w*|hablar con|habla con|mensaje a|correo de|numero de|telefono de) (?:a |al |con )?soporte\b/g,
  // Buttons, only the app's: "the share button", "a button in the app", never the stop button
  /\b(?:share|save|send|back|report|sign in|signin|next|submit|print|menu|play|done|skip|download|update|photo|camera|settings|app|otis) buttons?\b|\bbuttons? (?:in|on) (?:the |this |my )?(?:app|screen|page|otis|phone)\b/g,
  /\bboton(?:es)? (?:de|para) (?:compartir|guardar|enviar|reportar|descargar|imprimir|atras|firmar)\b|\bboton(?:es)? (?:de|en) la (?:app|aplicacion|pantalla)\b/g,
  // Links, only the app's or an email's, never a chain link or a fusible link
  /\b(?:email|sign in|signin|login|log in|magic|download|app|otis|text) links?\b|\blinks? (?:in|on|from) (?:the |my |your |this |an |that )?(?:app|email|text|otis|message)\b|\b(?:tap|tapped|tapping|click|clicked|clicking|open|opened|opening) (?:the |a |this |that |on the )?links?\b/g,
  // The phone, never a work cell or a gas monitor: "my cell", "cell phone", "this device"
  /\bcell ?phones?\b|\b(?:my|your) cell\b|\bcell (?:service|signal|data)\b|\b(?:my|this|your) device\b/g,
  // Notifications in Spanish, never "un aviso" on the wall: "no me llegan los avisos", "apagar los avisos"
  /\b(?:no (?:me |nos )?llegan?|ya no (?:me )?llegan?|apag(?:o|ar|ue|a)|activ(?:o|ar|e|a)|desactiv(?:o|ar|e|a)|silenci(?:o|ar|e|a)) (?:los |las |el |la )?avisos?\b|\bavisos? (?:de la app|de la aplicacion|de otis|del celular|del telefono)\b/g,
  // Signatures gone from the sheet in the app
  /\b(?:sigs|signatures?|firmas?) (?:keep |keeps |are |is |were |was |got |get |just )?(?:disappearing|disappeared|gone|missing|deleted|erased|lost) (?:from|on|in|off) the sheets?\b/g,
  // Switching the language, never a switch on a panel
  /\bswitch (?:the |my )?(?:app |otis |language |languages |it )?(?:to|into) (?:spanish|english|espanol|ingles)\b|\bswitch (?:the )?languages?\b/g,
  // Saving on the sheet: "my signature won't save on the sheet"
  /\b(?:save|saving|saved|saves|send|sending|sent|show|showing|shows) (?:on|in|to|from) the sheets?\b/g,
  // Push notifications, never "push the button"
  /\bpush (?:notifs?|notifications?|alerts?)\b/g,
  // The phone's camera, never a walk-in cold room ("la cámara" is both)
  /\bcamaras? (?:de|del) (?:la app|la aplicacion|celular|telefono|cel)\b|\bpermisos? (?:de|para) (?:la )?camara\b|\bcamara (?:para|de) (?:la )?fotos?\b/g,
  // Spanish: the app will not let me do something only the app does
  /\bno (?:me |nos )?(?:deja|dejo|permite) (?:firmar|guardar|enviar|descargar|iniciar sesion|actualizar|compartir|imprimir)(?: (?:la|las|mi|mis|el|los) (?:hojas?|firmas?|fotos?|charlas?|pdf))?\b/g,
  /\bla descarga (?:no (?:avanza|termina|empieza|carga)|se (?:detuvo|quedo|queda|trabo|congelo)|esta (?:trabada|detenida|lenta)|de la app|de otis)\b/g,
  // "The weather is not showing", "no aparece el clima": the weather card, said without "card"
  /\bweather(?= (?:is |isnt |is not |not |wont |doesnt |does not |didnt |still |no longer |never )*(?:showing|show|shows|load|loading|loads|missing|gone|updating|update|appear\w*)\b)/g,
  /\b(?:no (?:me )?(?:aparece|carga|sale|se ve|muestra|actualiza)|ya no (?:aparece|sale)) el clima\b|\bel clima (?:no|ya no) (?:aparece|carga|sale|se ve|se actualiza)\b/g,
  // Break and lock, only about OTIS or a talk
  /\botis (?:is |was |says it is |says its )?(?:taking|on|having|in) (?:a )?(?:short |little |quick )?break\b/g,
  /\botis (?:says?|said|tells me|told me)(?: (?:that|its|it is|he is|hes|it s))* (?:on|taking|having|in) (?:a )?(?:short |little |quick )?break\b/g,
  // The crew sheet in Spanish: "la hoja de la cuadrilla", "mi firma de la hoja", "no se me guarda la hoja"
  /\bhojas? de (?:la )?cuadrilla\b|\bfirmas? (?:de|en) (?:la|las|mi) hojas?\b|\b(?:se|me) (?:guarda|guardan|guardo|borro|borra|borraron) en (?:la|mi) hoja\b|\b(?:no )?se (?:me |nos )?(?:guarda|guardan|guardo|borro|borra|envia|manda) (?:la|las|mi|mis) hojas?\b/g,
  /\botis (?:is |was )?(?:switched|turned) off or (?:taking|on) (?:a )?break\b/g,
  /\b(?:talks?|episodes?|videos?|charlas?|platicas?|content) (?:is |are |esta |estan |sigue |siguen |still |says |shows )*(?:locked|bloquead[ao]s?)\b|\blocked (?:talks?|episodes?|videos?)\b|\blocked out of (?:the |my )?(?:app|account|otis)\b/g,
  // Data, only the phone's ("uses too much data", "borrar mis datos"), never a safety data sheet
  /\b(?:my|your|mobile|cell|cellular|phone) data\b|\bdata (?:plan|usage)\b|\b(?:uses?|using|eating|eats|ate|drains?|draining|burns?|burning) (?:up )?(?:all |too much |a lot of )?(?:of )?(?:my )?data\b/g,
  // Round 6: a box to type in, and flagging an answer, name nothing but the app: "cant type in the chat box", "how do i
  // flag that answer"
  /\b(?:text|search|message|chat|input|typing|comment) ?box(?:es)?\b|\bflag (?:that |the |this |an |a |otis |its |his )?(?:wrong |bad )?(?:answer|reply|response)s?\b/g,
  // "dark mode", "error 503", "error code 12", "talk 3", "step 3 of 5", "the text is too small", "make the font bigger",
  // "the screen is zoomed in". A machine's error code or a procedure's step comes with the machine's own words.
  /\b(?:dark|light|night) mode\b|\b(?:error|err) (?:code )?\d+\b|\berror codes?\b|\bcodigo de error\b|\b(?:step|page|talk|episode|question|video|chapter|paso|pagina|charla|episodio|pregunta|platica) \d+(?: (?:of|out of|de) \d+)?\b/g,
  /\b(?:the |my |this )?(?:text|letters|words|writing|letra|letras)(?= (?:is |are |looks |seems |es |esta |estan |se ve )?(?:too |so |really |super |muy |bien |tan )?(?:small|tiny|big|large|blurry|pequena|pequenas|chiquita|chiquitas|grande|grandes)\b)|\bmake (?:the )?(?:text|font|letters|words|writing) (?:bigger|smaller|larger)\b/g,
  /\b(?:the |my |this )?screens?(?= (?:is |are |looks |got |keeps |getting |all |stays |stuck )*(?:zoomed|zooming|sideways|upside down|rotated|flipped)\b)/g,
  /\b(?:mis|sus|tus|los) datos\b|\bdarme de baja\b|\bdar(?:me)? de baja (?:de|del) (?:la app|la aplicacion|otis|las notificaciones|los avisos|los correos|notificaciones|avisos|correos)\b/g,
];

/** Phrases taken as small words. They do not name the app. Each holds a word that is not an app word on its own. */
const SMALL_PHRASES: readonly RegExp[] = [
  /\b(every|each|what|first|this|one|that) (?:single )?time\b|\b(this|last|next) weeks?\b|\b(a cada|cada) rato\b|\bthe day\b|\bevery ?day\b|\beach day\b/g,
  // Back, only as a direction in the app ("went back", "sign back in"), never the body
  /\b(?:went|go|going|goes|gone|sign|signed|log|logged|get|got|came|come|comes|tap|tapped|swipe|swiped|scroll|scrolled|turn|turned|bring|brought) back\b|\bback (?:button|arrow|in)\b/g,
  // Save, in Spanish, without "guarda" (a machine guard)
  /\bse (?:me )?guardan?\b|\bno (?:me )?guarda\b/g,
  // "A little bit", never "a bug bit me"
  /\ba (?:little |tiny |lil )?bit\b/g,
  // Space on the phone, never a confined space
  /\b(?:not enough|no|out of|more|free|free up|enough|storage|any|disk|some) space\b|\bspace (?:on (?:my|the) phone|left|available|to download)\b/g,
  /\b(?:no tengo|tengo|sin|poco|falta|mas|liberar|libera|suficiente|no hay) espacio\b|\bespacio (?:en (?:el|mi) (?:cel|celular|telefono)|libre|suficiente|para (?:otis|la app|la aplicacion|descargar))\b/g,
  // Loading, never a load on a hook: "won't load", "never loads", "no carga"
  /\b(?:wont|will not|doesnt|does not|didnt|did not|dont|do not|cant|cannot|can not|not|never|to|still|hasnt|has not|havent|wasnt|isnt|aint|wouldnt|couldnt)(?: even| fully| ever| properly| all the way)? loads?\b/g,
  /\bloads? (?:forever|slow|slowly|really slow|so slow|so long|halfway|blank)\b|\b(?:not|never|hasnt|has not|wasnt|isnt|didnt|did not) (?:fully )?loaded\b/g,
  /\b(?:no|ya no|nunca|todavia no|aun no)(?: me| se| nos)? cargan?\b|\bcargan? (?:muy |bien |super )?lent[oa]s?\b|\btardan? (?:mucho )?en cargar\b/g,
  // Doing something to a sheet ("sign the sheet", "firmar la hoja"). The app is not named by it: a permit is a sheet.
  /\b(?:sign|signing|open|opening|find|delete|deleted|lost|lose|losing|edit|fill out|fill in) (?:the |my |a |this |that |our |all the |all )?(?:crew |sign in |signin )?sheets?\b|\blet me sign(?: (?:the |my |a |this )?(?:crew |sign in )?sheets?)?\b|\bse (?:me )?borr(?:o|aron)\b/g,
  // "la app ocupa mucho espacio", "lagging bad": a word taken only right after the app's own
  /\bocupa (?:mucho|demasiado|bastante) espacio\b|\b(?:lagging|lags|laggy|glitching|glitchy|crashing|freezing|slow|buggy) (?:so |real |really )?bad\b/g,
  /\b(?:guardar|guardo|enviar|envio|compartir|comparte|imprimir|firmar|firmo|abrir|borrar|borro) (?:la |las |mi |mis |una )?hojas?\b/g,
  // "There" only as "is there" / "there is", never a place ("in there", "up there", "stuck up there")
  /\b(?:is|are|was|were|isnt|arent|wasnt|werent) there\b(?! (?:now|yet|today|right now)\W*$)|(?<!\b(?:in|up|out|down|over|back|under|inside|from|into|get|go|went|stuck|still|right|sign|guy|man|one|someone|somebody) )\bthere(?: is| are| was| were| isnt| arent| wasnt| s)\b|\btheres\b/g,
  // "Up" only as part of a verb the app does ("set up", "pops up", "shows up", "comes up blank"), never a place ("up
  // there", "up top"). Not "fire up", "light up", "lock up", "hang up", "blow up", "pick up", "go up": those are events.
  /\b(?:set|sets|setting|pop|pops|popped|popping|show|shows|showed|showing|come|comes|came|coming|start|starts|started|starting|boot|boots|booted|booting|load|loads|loaded|open|opens|opened|opening|back|backed|backing|speed|sped|clear|cleared|free|freed|freeing|clean|cleaned|look|looked|mess|messed|messing|act|acts|acted|acting|fill|fills|filled|wake|wakes|woke|scroll|scrolled|scrolling|swipe|swiped|bring|brings|brought|turn|turned|sync|synced|use|uses|using|used|log|logs|logged|link|linked|showin|comin|poppin|loadin) up\b/g,
  // Numbers only as the app's: a percent, a size, an error or version number, "stuck at 40". A bare number is a person
  // ("otis 1 is down", "2 of mine"), a reading ("its 108 today") or a count of anything, so it is not an app word.
  // "N of M" only as the app counts: "step 3 of 5", "downloading 2 of 4", "3 of 5 talks". Never on its own: "the sheet
  // says 5 of 6" and "4 de 5" are a head count, and the one not counted may be a person still inside.
  /\b(?:step|page|talk|episode|part|question|video|chapter|downloading|downloaded|loading|updating|paso|pagina|charla|episodio|parte|pregunta|descargando) \d+ (?:of|out of|de) \d+\b|\b\d+ (?:of|out of|de) \d+ (?:talks|episodes|videos|pages|steps|questions|mb|gb|charlas|episodios|paginas|pasos|preguntas)\b/g,
  /\b\d+ (?:percent|mb|gb|kb|megs?|gigs?|min|mins|minutes|seconds|secs|times)\b|\b(?:error|code|version|step|page|ios|android|iphone|galaxy|pixel|v|episode|talk|week|level|option|chapter|part|codigo|pagina|paso|version|episodio|charla) \d+(?: \d+)*\b/g,
  /\b(?:stuck|frozen|paused|stopped|sitting|loading|downloading|updating|stays|stay|staying) at \d+(?: percent)?\b|\b(?:se queda|se quedo|sigue|va|at|en|al) (?:en )?\d+ percent\b/g,
  // A connection, only the phone's: "no connection", "lost connection", "connection error". Never "lost connection with 2"
  /\b(?:no|bad|poor|weak|slow|internet|wifi|wi fi|data|network|cell|lost|lose|losing|loses|lost the|lost my|my|the|a|any|good|check|without|keeps losing|keep losing) connection\b(?! with\b)|\bconnection (?:error|issue|problem|lost|failed|timed out|is bad|keeps)\b/g,
  // Data, asked about the app: "how much data does the app use"
  /\bhow much data\b/g,
  // "The talk is not there yet", the app's own words for a talk that is not out
  /\b(?:not|isnt|arent|aint) there yet\b/g,
  // Spanish phone talk: "donde le cambio el idioma", "le pico al boton", "no se reproduce", "ni madres"
  /\ble (?:cambio|pico|pique|doy|di|muevo|movi)\b|\b(?:no )?se reproduce\b|\bni madres\b/g,
  // Round 5, for reach. Each holds a word with a floor meaning, so it is taken only in the phrase: "hit save" (never "got
  // hit"), "eats my battery", "for good", "without wifi", "the text box", "the play store", "at 3am"
  /\bhit (?:save|send|submit|share|done|next|enter|print|refresh|the (?:save|send|share|submit|done|next) button)\b|\b(?:eats?|eating|ate|kills?|killing) (?:up )?(?:all )?(?:of )?(?:my |the )?(?:battery|data|storage)\b/g,
  /\bfor good\b|\bwithout (?:wifi|wi fi|internet|signal|data|service|a connection|connection|an account|email|signing in|logging in)\b|\b(?:text|search|check|message|chat|input|typing|comment) ?box(?:es)?\b|\b(?:play|app|google play|apple app) store\b|\b\d{1,2} ?(?:am|pm)\b/g,
  /\bkeyboard (?:covers|blocks|hides|is covering|is blocking)\b|\b(?:volume|sound|audio|brightness) (?:is |is too |is so |is really |too |so )?low\b|\blow (?:volume|brightness)\b/g,
  // Round 6, for reach, each with a word that has a floor meaning: "get rid of my account", "vanishing off the crew
  // sheet", "notifs aint comin thru", "wont take the photo", "make it bigger", "hard to read", "every couple days",
  // "zoomed in". Never "came off", "take it off", "hard to see" or "hard to breathe".
  /\bget rid of\b|\b(?:vanish\w*|disappear\w*|gone|missing|deleted|removed|wiped|erased) off\b|\b(?:comin|coming|come|came) (?:thru|through)\b/g,
  /\btake (?:the |a |my |our |any )?(?:group )?(?:photo|photos|picture|pictures|pic|pics|selfie|foto|fotos)\b|\bmake (?:it|this|the (?:text|font|letters|words|writing|screen)) (?:bigger|smaller|larger|easier to read)\b|\bhard to read\b/g,
  /\bevery (?:couple|few|other|two|2|3|three|couple of|few) ?(?:days|weeks)\b|\bzoomed (?:in|out)\b|\bzoom (?:in|out)\b/g,
  /\b(?:crash\w*|freez\w*|froze|frozen|clos\w*|quit\w*|dies|died|dying|lag\w*|glitch\w*|acting up|logs? out|logging out|kicks? out) on (?:me|us|my phone)\b|\bhow much (?:storage )?space\b|\btakes? (?:up )?(?:on|in) (?:my|the) phone\b/g,
  /\b(?:wont|doesnt|didnt|will not|does not|did not) let (?:me |us |the app |otis |it )?(?:update|download|install|sign|log|open|save|share|send|change|type)\b|\bswitch (?:to|the language|languages|it to|back to|over to|accounts?)\b/g,
  /\bplease wait\b|\bnot (?:on |in )?(?:the |a |my |any )?crew\b|\bjoin (?:the |a |my )?crew\b|\b(?:wont|doesnt|didnt|will not|does not|did not) let me\b(?! (?:go|out|leave|loose|free|stop|move|breathe|get|pull|through|off|down|up)\b)|\bvolume (?:is )?(?:all the way |turned |)up\b|\bturn(?:ed)? (?:the )?volume up\b|\bshare (?:it |the talk |this |the sheet |the video )?(?:with|to) (?:my |the )?crew\b/g,
];

const wordSet = (list: string) => new Set(list.split(/\s+/).filter(Boolean));

/**
 * Words that name the app or a part of it: the app, the phone, a screen, a talk, a signature, an account, an update.
 * A message must hold at least one of these (or an app phrase above) to be about the app: "im stuck", "its
 * freezing", "it crashed" and "the battery is dead" name nothing of the app, so they are not taken as app questions.
 */
const APP_THINGS = wordSet(
  // the app and the phone
  'app apps application aplicacion aplicaciones otis zeroharm trainovate phone phones cellphone iphone android ipad tablet ' +
    'telefono celular cel movil ' +
    // its parts and features
    'page pages tab tabs menu icon keyboard font ' +
    'episode episodes talk talks topic topics content theme decorations ' +
    'signin signout signup photo photos picture pictures camera pdf pdfs print printing printed ' +
    'printer share sharing shared save saved saves saving send sending sent ' +
    'ticket contact email emails mail correo password passcode contrasena account cuenta profile name nombre info information ' +
    'login logout logged logging reminder reminders update updates updated updating upgrade version unsubscribe ' +
    'download downloads storage wifi internet dl ' +
    'language english spanish espanol ingles idioma ' +
    'pagina enlace configuracion recordatorio charla charlas platica platicas episodio ' +
    'foto fotos almacenamiento sesion imprimir compartir historial server servers servidor',
);

/**
 * Every other word the gate takes: what goes wrong with software, and the small words of a question in English and
 * Spanish. None of these names the app on its own.
 */
const APP_SMALL_WORDS = wordSet(
  // what goes wrong with software
  'stuck froze frozen broke broken busted error errors blank black white gray grey dark slow slower laggy down dead died dies ' +
    'quit quits quitting stops stopped stopping hang hangs hanging hung missing gone problem problems issue issues code codes codigo nothin ' +
    'changing finding flag flagged left arriving arrive arrived middle switched removing offered sends suggesting happening happens ' +
    'happened enough lost trouble wrong sucks useless unresponsive responding respond responds ' +
    'play plays playing played timed timeout forever keeps keep kept acting messed weird ' +
    'strange funny different same nothing help bug bugs delete deleted ' +
    'deleting remove removed memory signal offline online battery model answer answers answered answering reply ' +
    'replies response chat question questions message messages feature option options list history past search results look looks size ' +
    'text install installed installing reinstall uninstall ' +
    'trash trippin mad wtf af smh rn idk thru showin saying todays put colors colours telling mid ' +
    // round 5, for reach: words with no floor meaning
    'type typing typed audio volume quiet loud sideways landscape portrait zoomed expired expire expires asking sentence reason couple ' +
    'fine mode makes anywhere ' +
    // round 6, for reach: more words with no floor meaning
    'empty days weeks morning mornings fr cuadrilla toda todo todos todas le les pongo traban trabaron gives giving like session sessions invalid intente intento intentado intentar ' +
    'lenta lento rara raro diferente mal pegada pegado blanco blanca negra negro jala sirve truena trono responde contesta aparece aparecen funsiona mucho pa solita ratito ' +
    'llega llegan muestra cuelga colgo colgada apaga apago apagar reinicia termina terminar memoria senal respuesta pregunta mensaje ' +
    'cierra cerro cerrar cerrando cerrandose traba trabo trabada trabado trabando trabandose problema problemas error errores falla fallas fallo ' +
    'cargar cargando abre abrir abro abri entrar entro funciona funcionar funcionando funciono enviar envia ' +
    'igual mismo sin servir pasando arreglo arreglarse arreglado dice dijo mandar borrar borro cambiar cambio cambia iniciar guardar guardado ' +
    'sale salio deja dejo disponible sabe pide nomas olvide olvido pon poner pone queda quedo pensando eso esto ocupa seguido firmar ' +
    // the small words of a question, in English
    'i im ive id my me you your youre it its itself this that these those the a an any some all every each ' +
    'yes yeah yep yup nope nah si claro dale is are was were be been being am has have had do does did done will would can could ' +
    'should to of in at for with from by into about after before during since until as so if when whenever while ' +
    'then than but and or n also too just still again always never ever now already yet even only really very super totally ' +
    'completely constantly suddenly randomly sometimes often anymore more keeps how what whats why where wheres which who whos ' +
    'not no cant cannot wont dont doesnt didnt isnt arent wasnt couldnt wouldnt shouldnt havent hasnt aint unable able ' +
    'please pls plz thanks thank thx ok okay hey hi hello yo lol ugh need needs needed want wants wanted ' +
    'go goes going see seen show shows showing shown find found use using used ' +
    'try tried trying tap tapped tapping click clicked swipe say says said tell ask asks asked know sure way thing things something ' +
    'anything everything new old first next other another less much many lot lots little big bigger small smaller tiny today ' +
    'yesterday percent number numbers fix fixed change changed turn turns turned turning run runs running started starts start ' +
    'open opens opened opening loading work works worked working crash crashes ' +
    'crashed crashing gave give suggest ' +
    // and in Spanish
    'la los las lo un una unos unas de del al a en con para por que y o pero cuando cada vez veces siempre nunca ya aun todavia ' +
    'otra otro nuevo nueva mas muy bien super tan solo sola mi mis tu su sus me se yo no si nada como donde cual quien porque ' +
    'es esta estan era fue sigue anda va hay tengo tiene tienen puedo puede pude podemos quiero necesito hacer hago ver ve veo ' +
    'desde ayer hoy ahora favor porfa gracias hola oye',
);

/** Word families that name a part of the app: "notifs", "redownload", "updating", "descargando". Whole words only. */
const APP_THING_STEMS: readonly RegExp[] = [
  // "notifs", "notifications", never "notify" (lockout requires that you notify people)
  /^notif(?:s|ication|ications|icacion|icaciones)$/, /^(?:re)?download\w*$/,
  // "descargar", "descargando", never "una descarga" (an electric shock)
  /^descarg(?:ar|o|ue|ues|ada|ado|ados|adas|arla|arlo)$/, /^updat\w*$/, /^actualiz\w*$/, /^actualic\w*$/, /^sync\w*$/,
  /^reboot\w*$/, /^buffer\w*$/,
];

/** Word families of what goes wrong: "crashing", "crashea", "freezin", "bugueada". Whole words only. */
const APP_SMALL_STEMS: readonly RegExp[] = [
  // "freezing", "frezing", "freezin", never "freezer", "frezer" or "freezr"
  /^crash\w*$/, /^fr(?:e|ee|ea)z(?:e|es|ed|ing|in|n)?$/, /^glitch\w*$/, /^bug(?:s|ged|ging|ue\w*|ead[oa]s?)?$/, /^lag(?:s|gy|ging|gin|ged)?$/,
  // "loading", never a bare "load" (a load on a hook): "won't load" is a phrase above
  /^load(?:ing|in)$/, /^open(?:s|ed|ing|in)$/, /^work(?:s|ed|ing|in)$/, /^disappear\w*$/,
  /^vanish\w*$/, /^refresh\w*$/, /^restart\w*$/, /^launch\w*$/, /^scroll\w*$/, /^fail(?:s|ed|ing|ure)?$/, /^fall(?:a|as|o|ando)$/,
  /^congel(?:a|o|ada|ado|ando|andose)$/, /^funcion\w*$/, /^(?:re|un)?instal\w*$/,
];

/**
 * The app's long words, for the small typo allowance: one letter left out, added, or swapped with the next one, and
 * for the longest of the words that name the app one letter changed ("aplicasion"). The first ones name a part of
 * the app; the rest are what goes wrong. No hazard word is ever matched loosely.
 */
const TYPO_THINGS = [
  'notification', 'notifications', 'aplicacion', 'application', 'password', 'download', 'downloading',
  'update', 'updating', 'account', 'keyboard', 'episode', 'camera', 'iphone', 'android',
  'celular', 'telefono', 'pantalla', 'descargar', 'actualizar', 'unsubscribe',
];
const TYPO_SMALL = [
  'crashing', 'crashed', 'freezing', 'frozen', 'loading', 'working', 'opening', 'funciona', 'glitching', 'logging',
  'kicking', 'spinning', 'stopped', 'unresponsive', 'storage',
];
/** Real words a typo rule would let through. None of them is the app. */
const NOT_TYPOS = new Set(['cashing', 'cashed', 'lading', 'screem', 'frozer', 'frozed', 'descarga', 'descargas']);

/** One letter left out, added, or swapped with its neighbour; with `change`, also one letter changed (not the first two). */
function oneTypoFrom(word: string, target: string, change: boolean): boolean {
  if (word[0] !== target[0] || Math.abs(word.length - target.length) > 1) return false;
  if (word.length === target.length) {
    const at = [...word].findIndex((c, i) => c !== target[i]);
    if (at < 0) return false;
    // two letters swapped
    if (at < word.length - 1 && word[at] === target[at + 1] && word[at + 1] === target[at] && word.slice(at + 2) === target.slice(at + 2)) return true;
    // one letter changed
    return change && at >= 2 && word.slice(at + 1) === target.slice(at + 1);
  }
  const [long, short] = word.length > target.length ? [word, target] : [target, word];
  for (let i = 0; i < long.length; i++) if (long.slice(0, i) + long.slice(i + 1) === short) return true;
  return false;
}

/** The app word a typo stands for: "crashd" is "crashed", "aplicasion" is "aplicacion". Undefined for anything else. */
function typoTarget(word: string, targets: readonly string[]): string | undefined {
  if (word.length < 5 || NOT_TYPOS.has(word)) return undefined;
  return targets.find((target) => oneTypoFrom(word, target, targets === TYPO_THINGS && target.length >= 8));
}
const typoOf = (word: string, targets: readonly string[]) => typoTarget(word, targets) !== undefined;

/** A word that names a part of the app. */
const appThing = (word: string) => APP_THINGS.has(word) || APP_THING_STEMS.some((stem) => stem.test(word)) || typoOf(word, TYPO_THINGS);

/** A word the gate takes at all. */
const appWord = (word: string) =>
  appThing(word) || APP_SMALL_WORDS.has(word) || APP_SMALL_STEMS.some((stem) => stem.test(word)) || typoOf(word, TYPO_SMALL);

/** Lower case, no accents, no apostrophes ("won't" is "wont"), no punctuation. */
const words = (text: string) =>
  plain(text)
    .replace(/(\d)\s*%/g, '$1 percent ')
    .replace(/'/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

const cut = (text: string, phrases: readonly RegExp[]) => phrases.reduce((left, phrase) => left.replace(phrase, ' '), text);

/** The words left once app phrases are taken out, and whether any app phrase was there. */
function appSplit(text: string): { left: string[]; phrase: boolean } {
  const squash = (line: string) => line.replace(/\s+/g, ' ').trim();
  const joined = squash(cut(words(text), JOINERS));
  const named = cut(joined, APP_PHRASES);
  const left = cut(named, SMALL_PHRASES).split(' ').filter(Boolean);
  return { left, phrase: squash(named) !== joined };
}

/**
 * Words for how a thing is that are also how a person is: down, missing, gone, lost, stuck, hanging, dead, black,
 * white, blank, answering, and Spanish mal, pegado, contesta, aparece, sale, queda. "The app is down" and "1 is down",
 * "the talk is missing" and "3 are missing", "otis isnt answering" and "1 is not answering", "la app no contesta" and
 * "y no contesta". Each is taken only right after a part of the app as its subject, with nothing but small helper
 * words in between ("the app on my phone is down", "the download is stuck", "otis stopped answering", "la app se
 * queda pegada"), or in a few fixed phrases ("stuck on the loading screen", "lost my signatures", "no aparece la
 * charla", "black screen"). "And" or "y" ends the subject, so "la app no sirve y esta pegado" is not about the app.
 * "It" is never the subject: "it all went black", "its gone", "it got stuck" are said of a machine or a person too.
 */
const STATE_WORDS = new Set(
  (
    'down missing gone lost stuck hanging hangs hang hung dead died dies answering black white blank dark gray grey ' +
    'mal pegado pegada contesta contestan aparece aparecen sale salen salio queda quedo'
  ).split(' '),
);
const STATE_SUBJECT =
  '(?:app|apps|application|aplicacion|otis|zero harm|zeroharm|trainovate|phone|phones|iphone|android|ipad|tablet|cell|cellphone|celular|cel|telefono|movil|device|' +
  'screen|screens|page|pages|tab|tabs|menu|talk|talks|video|videos|episode|episodes|sheet|sheets|signature|signatures|sigs|history|historial|button|buttons|' +
  'link|links|icon|option|options|feature|features|account|profile|cuenta|perfil|notifications?|notifs?|reminders?|update|updates|download|downloads|downloading|' +
  'wifi|wi fi|internet|signal|data|battery|bateria|server|servers|site|website|system|chat|answer|answers|reply|replies|response|respuesta|weather|clima|' +
  'card|cards|language|spanish|english|espanol|ingles|photo|photos|picture|pictures|camera|camara|pdf|pdfs|text|font|keyboard|content|pantalla|charla|charlas|' +
  'platica|platicas|pagina|hoja|hojas|foto|fotos|enlace|boton|login|setup|loading|search|results|actualizacion|descarga|contenido|aviso|avisos|minute|minuto)';
const STATE_HELPER =
  '(?: (?:is|isnt|was|wasnt|are|arent|were|werent|has|hasnt|have|havent|had|been|be|being|just|still|always|keeps|keep|kept|got|gets|getting|seems|seem|' +
  'looks|look|went|goes|go|going|gone|turns|turned|turning|stays|stayed|totally|completely|all|so|really|now|again|randomly|suddenly|sometimes|also|not|never|' +
  'no longer|stopped|quit|wont|doesnt|didnt|aint|cant|comes up|came up|come up|coming up|on my phone|on the phone|for me|today|on me|se|esta|estan|sigue|siguen|anda|ya|' +
  'me|nos|no|queda|quedo|bien|muy|super|toda|todo|siempre|nomas|de nuevo|otra vez|completamente|todavia|aun|(?:del|de la|de los|de las|de) [a-z]+))*';
const STATE_OK: readonly RegExp[] = [
  // Round 6: "otis se queda pensando y no contesta" (before the line below takes "se queda" on its own)
  /\bse queda pensando y (?:no|nunca|ya no) (?:contesta|responde)\b/g,
  new RegExp(`\\b${STATE_SUBJECT}${STATE_HELPER} (?:${[...STATE_WORDS].join('|')})\\b`, 'g'),
  // Spanish puts the verb first: "no aparece la charla", "no me contesta otis", "salio una actualizacion"
  new RegExp(`\\b(?:no |ya no |todavia no |aun no |nunca )?(?:me |se |nos |le )?(?:aparecen?|salen?|salio|contestan?|queda)(?= (?:el |la |los |las |mi |mis |tu |su |una |un )?${STATE_SUBJECT}\\b)`, 'g'),
  // Fixed phrases with no subject: "stuck on the loading screen", "stuck loading", "lost my signatures", "black screen"
  new RegExp(`\\bstuck(?= (?:on|at|in) (?:the |a |my |this )?(?:${STATE_SUBJECT}|loading|setting up|downloading|updating|splash|sign in|signin)\\b)|\\bstuck(?= (?:loading|downloading|updating|spinning|thinking|buffering|syncing|on setting up)\\b)`, 'g'),
  new RegExp(`\\b(?:lost|missing|gone)(?= (?:my |the |a |some |all my |all the |all |our |his |her |every )?(?:${STATE_SUBJECT})\\b)`, 'g'),
  /\b(?:black|white|blank|gray|grey|dark)(?= (?:screen|screens|page|pantalla|mode|theme|text|background)\b)|\bgone from (?:my |the )?(?:phone|app|list|menu)\b/g,
  /\b(?:scroll|scrolled|scrolling|swipe|swiped|shut|shuts|shutting|slow|slows|slowed|slowing|drop|dropdown) down\b|\b(?:se |me )?qued[ao] (?=cargando|pensando|en blanco|trabada|congelada|colgada|descargando|pegada)|\bno queda espacio\b/g,
  // Round 6: "page 2 of 5 is blank", "otis se queda pensando y no contesta"
  new RegExp(`\\b(?:page|step|talk|episode|video|part|question|chapter|pagina|paso|charla|episodio) \\d+(?: (?:of|out of|de) \\d+)?${STATE_HELPER} (?:${[...STATE_WORDS].join('|')})\\b`, 'g'),
  /\b(?:me |nos |le )?sale (?=(?:un |una |el |la )?(?:error|mensaje|aviso|en ingles|en blanco|que|otra vez)\b)|\b(?:aparece|sale) (?=en (?:ingles|blanco)\b)|\bmal (?=(?:con|en) (?:la app|la aplicacion|otis|el celular|el telefono|mi celular)\b)/g,
];

/**
 * The words of the message that are STATE_WORDS with no part of the app as their subject. A comma, a stop, "!", "?"
 * or ";" is kept as a break, so a state word is never taken for the state of a subject in another clause: in "no
 * signal, lost, phone at 4 percent" it is the person who is lost, not the signal.
 */
function strayState(text: string): string[] {
  const broken = plain(text).replace(/[,;!?]|\.(?=\s|$)/g, ' qqbreak ');
  const left = STATE_OK.reduce((line, rule) => line.replace(rule, ' '), words(broken));
  return left.split(' ').filter((word) => STATE_WORDS.has(word));
}

/**
 * People talk to OTIS by name: "otis 1 is down", "otis its frozen and im in there", "otis can i run it now", "otis
 * what do i do". A leading "otis" names the app only when OTIS is the subject of what follows: "otis is slow", "otis
 * wont download", "otis keeps crashing", "otis gave me a wrong answer", "otis no descarga". When the next word starts
 * a question to OTIS (it, i, can, do, what, who, where, now, all, a number), "otis" is only the person calling it, and
 * the rest must name the app on its own.
 */
const OTIS_DOES = new Set(
  ('is isnt was wasnt are has hasnt had will wont would wouldnt does doesnt did didnt can cant cannot could couldnt keeps keep kept just always never ' +
    'still not aint stopped stops stop quit quits says said gave gives give told tells answers answered takes took taking seems sounds shows showed gets got ' +
    'asks asked needs thinks randomly suddenly sometimes also only download downloads update updates app chat model setup voice ' +
    'no ya se esta sigue anda dice dijo pide tarda siempre nunca solo nomas me lento lenta responde contesta descarga funciona sirve carga abre va da marca tiene').split(' '),
);
const OTIS_AUX = new Set('is was are has had will would does did can could'.split(' '));
const ASKS_OTIS = new Set('it its that this there theres these those the a an my your our his her he she they we i im you ok okay safe alright fine possible'.split(' '));

/** True when a leading "otis" is only the person calling OTIS by name (see OTIS_DOES). */
function callingOtis(all: string): boolean {
  const [first, next = '', after = ''] = all.split(' ');
  if (first !== 'otis' || !next) return false;
  if (/^\d/.test(next)) return true;
  if (OTIS_AUX.has(next)) return ASKS_OTIS.has(after) || /^\d/.test(after);
  // "otis so slow today", "otis super laggy": OTIS is the subject
  if (/^(?:so|super|really|too|real|hella|mad)$/.test(next) && /^(?:slow|laggy|buggy|glitchy|broken|useless|trash)$/.test(after)) return false;
  return !(OTIS_DOES.has(next) || /^(?:crash|freez|frez|froze|glitch|lag|fail|hang|hung|stuck|frozen|shut|clos|load|spin|bug)/.test(next));
}

/**
 * Words before a last "otis" that make it part of what is said ("i cant open otis", "no tengo espacio para otis").
 * After any other word a last "otis" only calls OTIS by name: "what is happening to me otis", "is it ok now otis".
 */
const TAKES_OTIS = new Set(
  ('is about use using open update install download of for to with in on from called the my delete uninstall reinstall fix reset ' +
    'restart get does did can cant wont turn off para de del con en a al sin y o la el').split(' '),
);

/** The words of the message, without a leading or a last "otis" that only calls OTIS by name. */
const withoutCalling = (text: string) => {
  let all = words(text);
  if (callingOtis(all)) all = all.slice(5);
  const each = all.split(' ');
  if (each.length > 1 && each[each.length - 1] === 'otis' && !TAKES_OTIS.has(each[each.length - 2])) all = each.slice(0, -1).join(' ');
  return all;
};

/**
 * The person, not the app, in a failure word: "im stuck", "i am frozen", "i got stuck", "we are lost". Every word of
 * these is an app word, but they say how a person is, so the message is not only about the app.
 */
const PERSON_STATE =
  /\b(?:(?:im|i am|i m|i got|i get|i was|i been|i keep getting|ive been|i have been|we are|were|we got|we were|we been)\s+(?:so |really |very |still |just |all |kind of |getting |gotten )?(?:stuck|frozen|freezing|froze|dead|dying|down|lost|gone|hanging|hung|broke|broken|done|blank|black|dark|slow|weird|unresponsive)|i (?:froze|freeze|stuck))\b/;

/** Round 6: the pieces of the "and i did too" rule below. */
const R6_JOIN = '(?:and|y|n|but|pero|then|so|now|plus|as|while|tho|though)';
const R6_ME = '(?:i|im|i m|ive|me|myself|we|were|us)';
const R6_HELPER =
  '(?:am|m|is|are|was|were|be|been|being|have|has|had|ve|did|do|does|keep|keeps|kept|just|also|now|then|still|really|totally|all|getting|got|gotten|' +
  'started|start|feel|feeling|felt|acting|act|going|gonna|kinda|kind of|super|so|probably|think|literally|pretty|completely|seem|seems|look|looks|went|go|too)';
const R6_END =
  '(?:froze|frozen|freez\\w*|crash\\w*|stuck|down|spin\\w*|hang\\w*|hung|broke\\w*|dead|dying|died|lost|gone|weird|funny|different|odd|off|blank|black|dark|slow|' +
  'done|did|do|does|have|has|had|am|was|is|are|were|been|the same(?: way| thing)?|same(?: way)?|just the same|glitch\\w*|lag\\w*|still|too|to|also|as well|aswell|' +
  'not|not ok|not okay|not good|not fine|no good|messed up|locked up|froze up|frozen up|out|quit|stopped|shut down|went down|go down|went black|went dark|' +
  'blacked out|passed out|with it|tambien|igual|tampoco|mal|pegad[oa]s?|trabad[oa]s?)';
const R6_TAIL =
  '(?:too|to|also|as well|aswell|now|again|up|out|lol|here|rn|right now|since [a-z0-9]+|for \\d+ ?[a-z]*|for a while|for a bit|with it|today|tambien|igual|ya|ahora)';
/** Round 6: what makes a saying ("the app says ...") app talk, not a go-ahead. */
const R6_APP_TALK = [
  'updat\\w*', 'upgrad\\w*', 'actuali\\w*', 'version', 'download\\w*', 'descarg\\w*', '(?:re|un)?install\\w*', 'instal\\w*', 'locked', 'lock out',
  'bloquead\\w*', 'storage', 'space', 'espacio', 'memory', 'memoria', 'error\\w*', 'errores', '\\d{3}', 'code', 'codigo', 'went wrong',
  'something (?:is |went )?wrong', 'wrong (?:password|code|email|answer|answers|info|thing|things|language|number|account|link)', 'no tiene',
  'doesnt have', 'does not have', 'dont have', 'do not have', 'knowledge', 'on a break', 'break', 'descanso', 'sign ?in', 'signed in', 'sign ?out',
  'log ?in', 'logged', 'log ?out', 'login', 'logout', 'sesion', 'password', 'contrasena', 'email', 'correo', 'link', 'enlace', 'type', 'offline',
  'online', 'internet', 'wifi', 'wi fi', 'connection', 'conexion', 'signal', 'senal', 'service', 'loading', 'cargando', 'try again', 'retry',
  'expired', 'expir\\w*', 'venci\\w*', 'account', 'cuenta', 'not on (?:the |a |my )?crew', 'no crew', 'crew (?:sheet|sign ?in|list|code)',
  'not available', 'unavailable', 'no disponible', 'not offered', 'spanish', 'english', 'espanol', 'ingles', 'language', 'idioma', 'settings',
  'ajustes', 'configuracion', 'permission', 'permiso', 'notification\\w*', 'notificacion\\w*', 'camera', 'camara', 'microphone', 'blank',
  'en blanco', 'cant answer', 'cannot answer', 'only answer', 'safety questions?', 'not found', 'server', 'servidor', 'session', 'wrong answer',
  'bad answer', 'no talk', 'no talks', 'no hay charla', 'talks?', 'charlas?', 'videos?', 'episodes?', 'sheets?', 'hojas?', 'photos?', 'fotos?',
  'connect\\w*', 'please wait', 'espere', 'results?', 'resultados', 'supported', 'compatible', 'attempts', 'intentos', 'invalid\\w*', 'no valid[oa]',
  'not valid', 'access', 'acceso', 'denied', '(?:weird|strange|bad|wrong|incorrect|odd|dumb|same|old|different|random) (?:answer|answers|reply|replies|response|thing|things)',
  'no (?:answer|answers|reply|response)', 'over and over', 'again and again', 'repeat\\w*', 'restart (?:the )?(?:app|otis|phone)', 'reopen', 'close (?:the )?app', 'cerrar la app',
].join('|');

/**
 * Sayings made only of app words that are not about the app: a person, a machine, a rule or a right. Each is a whole
 * phrase, never a single word, so a real app question around it is not lost. Checked on the words of the message
 * (lower case, no accents, no apostrophes, no punctuation).
 */
const NOT_ABOUT_THE_APP: readonly RegExp[] = [
  PERSON_STATE,
  // Stuck in a place, anywhere in the message: "stuck in the frezer", "my phone is stuck in there and i cant get it out"
  /\bstuck (?:in|inside|under|between|on top of)\b(?! (?:the |a |this |that )?(?:app|loop|sign|login|loading|update|download|screen|page|otis|setup|menu|settings)\b)|\b(?:cant|cannot|couldnt|cant even) get (?:it|him|her|them|my \w+) (?:out|loose|free|off)\b/,
  // How a person is: "im not ok", "i cant see anything", "so am i", "i crashed too", "i had an episode", "save me"
  /\b(?:im|i am|i m|i feel|i dont feel|i do not feel|i aint|i was|we are|we were|we arent|i felt) (?:not |so |really |kinda |just )?(?:ok|okay|alright|good|well|right|great|fine)\b/,
  /\b(?:i|we) (?:cant|cannot|can not|couldnt|could not|cnt) see(?: anything| nothing| at all| good| well| right| straight| clearly| out of| a thing)?$|\b(?:cant|cannot) see (?:anything|nothing|at all|straight|clearly|good|well)\b/,
  /\bno (?:puedo|puede|pude|podemos|veo) (?:ver )?(?:nada|bien|claro)\b|\bno (?:puedo|puede|pude|podemos) ver$|\b(?:ya )?no (?:veo|ve|vemos)$/,
  /\bso (?:am|did|was|do|is|are|have|has) (?:i|we|everything|everyone|everybody|he|she|they)\b/,
  /\b(?:i|we) (?:crashed|crash|blacked|black|passed|pass|went down|go down|froze up)\b(?! (?:the|my|it|this|that|otis|app|application|phone)\b)/,
  /\b(?:i|he|she|we|they)(?: just)? (?:had|have|having|has|is having|am having|was having|keep having) an? episodes?\b/,
  /\bsave (?:me|us|him|her|them)\b(?! (?:a |the |some |my |time|space|data))/,
  /\beverything(?: is| was| keeps| started| just| went| goes| going)* (?:spinning|black|dark|blurry|white|fuzzy|moving|double)\b|\b(?:room|my head|head) (?:is |keeps )?spinning\b/,
  // A machine that will not stop: "it wont stop", "keeps running", "keeps going"
  /\b(?:wont|will not|doesnt|does not|didnt|did not|cant|cannot|not|never|couldnt) stop\b/,
  /\b(?:keeps?|kept|still) (?:going|running|moving|turning)\b(?! (?:back|to|slow|slowly|in the background)\b)/,
  // Something coming down or starting by itself, a tap, the dark: "its coming down", "it started by itself"
  /\b(?:coming|comin|came|falling|come|comes) (?:down|apart|loose|off|undone)\b/,
  // Started by itself ("it restarted by itself"), unless it is the app or the phone that did
  /(?<!\b(?:app|otis|phone|application|aplicacion) (?:just |keeps |kept |always |randomly |sometimes )?)\b(?:(?:re)?(?:start|starts|started|starting)|turned on|turns on|came on|comes on|kicked on|kicks on)(?: up)? (?:by itself|on its own|itself)\b/,
  /\bits (?:still )?running\b|\bit (?:came|comes|kicked|kicks|turned|turns) on\b|\b(?:its|it is|getting|got) (?:so |really |too |pretty )?dark\b(?! (?:mode|theme))|\b(?:the|a|that|this|water|sink) tap\b/,
  // A person kicked, "él" doing something ("y el esta pegado"), a machine still on
  /\b(?:i|he|she|we|they|me|him|her) (?:got|get|was|been|just got) kicked\b(?! (?:out|off|me|from|back to))/,
  /\bel (?:esta|estaba|estuvo|sigue|anda|tiene|no|ya|se|me|te|le|lo|nos|va|queda|quedo|sale|salio|entro|aparece|ve|puede|es|era|fue)\b/,
  /\b(?:its|it is|its still|it is still|still) (?:still )?(?:on|live|going)\b(?! (?:the |my )?(?:app|screen|phone|loading|page)\b| (?:a |its )?(?:short |little |quick )?break\b)/,
  // A cry made only of app words: "it shut on me", "get me out", "it got me", "something went off", "won't let go"
  /\b(?:shut|shuts|closed|closes|slammed|clamped)(?: back)? (?:on|onto|over) (?:me|him|her|them|us|my|his|their)\b|\b(?:its|it is|its still) on (?:me|him|her|my|his)\b/,
  /\b(?:get|let|help) (?:me|us|him|her|them) out\b(?! of (?:the |this |my )?(?:app|talk|screen|page|video|chat|otis|account|menu|loop|sheet)\b)|\bcome get (?:me|us|him|her)\b|\bget (?:it|this|that|them) off (?:me|him|her|us)\b/,
  /\b(?:wont|doesnt|cant|cannot|will not|does not) let go\b|\b(?:it|something|somethin|a bug|bugs|bees?|wasps?|a snake|a dog|the dog|the machine|the belt|that thing) (?:got|grabbed|caught|bit|stung|took) (?:me|him|her|us)\b(?! (?:logged|kicked|signed|booted|confused|thinking|wondering|out of))/,
  /\bwent in\b.{0,25}\b(?:aint|isnt|not|hasnt|never|wont|didnt) (?:coming|come|came|comin)(?: back)? out\b|\b(?:something|somethin|it|stuff) (?:just )?went off\b|\bentro\b.{0,25}\bno (?:ha )?sal(?:e|ido|io)\b/,
  // A crash that is not the app's: "there was a crash", "big crash"
  /\b(?:there was|theres been|there has been|there is|theres|we had|just had|heard|was|had) (?:a |an )?(?:big |bad |loud |huge |real )?crash\b(?! reports?\b)|\b(?:big|bad|huge|loud|terrible|serious|major|massive|car|truck|forklift) crash\b(?! reports?\b)/,
  // Reporting at work: "i reported and nothing happened", "a quién reporto", "tengo que reportar", "si reporto"
  /\b(?:i|we|already|ya) report(?:ed|e)\b|\b(?:tengo|hay|tienes|tiene) que reportar\b|\ba quien (?:le )?report\w*|\bsi report\w*|\b(?:how|where|can|should|do) (?:can |do |should )?(?:i|we) report\W*$/,
  // A signature, a machine's settings, a phone on the floor, a near miss, the weather: "do I need a signature to
  // start", "can I change the settings with it on", "can I take my phone in there", "that was close", "freezing out"
  /\bneeds? (?:a |the )?(?:signature|firma)s?\b|\bsin (?:la |una )?firmas?\b|\bto (?:start|begin|enter)$/,
  /\bturn (?:it|this|that) off to\b|\b(?:with|while) (?:it|its) (?:still )?(?:on|running|going)\b|\bsin apagar\b/,
  /\b(?:take|bring|use|be on|have|carry) (?:my |a |the |your )?(?:phone|cell|celular|cellphone) (?:in|into|while|near|on the|out there|in there)\b|\bwhile (?:working|im working|i work|on the job|driving|operating)\b|\bkeep working\b/,
  /\b(?:that|it|this) was (?:so |too |real |really |pretty )?close\b|\btoo close\b|\bfreezing (?:out|outside|cold|in here)\b/,
  // A card's reading is a question about the heat, not about the app: "heat card says 108 what do i do"
  /\b(?:card|tarjeta) (?:says|dice|shows|reads|muestra|marca) (?:its |it is |es |que |de )?\d+/,
  // Going in somewhere, and who to talk to: "do i have to sign in to go in there", "who do i talk to"
  /\b(?:go|get|climb|walk|crawl) (?:in|into|inside|down|up) (?:there|here)\b|\bwho (?:do|can|should|would) (?:i|we) talk to\b/,
  // A person, said with app words: "something is wrong with me", "i quit", "is it ok to open", "y ya no sale"
  /\bwrong with (?:me|him|her|us|them|my (?!phone|app|account|screen)\w+)\b|\bi (?:quit|am quitting|m quitting|im quitting)\b(?! (?:the |using )?(?:app|otis)\b)|\by (?:ya )?no (?:sale|salio|ha salido)$/,
  /\bis it (?:ok|okay|alright|fine) (?:to|if)\b(?! (?:i )?(?:delete|uninstall|update|reinstall|download|close|log out|sign out) (?:the |my )?(?:app|otis|account)\b)/,
  // "what do I do", on its own: an emergency as often as anything
  /^(?:otis )?(?:que hago|que hacemos|what do i do|what do we do|what should i do|what now|ahora que)$/,
  // Signing for someone else, and records that are not true
  /\b(?:can|could|will|would|should) (?:you|he|she|they|someone|somebody) sign\b|\bsign\w* (?:your|his|her|their|someones|somebodys|a coworkers|my coworkers) (?:name|initials|signature)\b/,
  /\bsign\w*(?: in| my name| it| the sheet)? for (?:you|me|him|her|them|someone|somebody|a coworker|my coworker|another)\b|\b(?:but|and|y) i (?:wasnt|was not|didnt|did not|never|aint)\b|\bi (?:wasnt|was not) (?:even )?there\b/,
  /\bfirm\w* (?:por|para) (?:el|ella|ellos|ellas|otro|otra|alguien|usted|ti|mi compa\w*)\b|\bfirm\w* (?:el|su) nombre\b|\bpero (?:yo )?no (?:estaba|estuve|firme)\b/,
  // Going in, starting work: "before i go in", "can i start if", "entrar al espacio"
  /\b(?:before|until|if|when|once) (?:i|we|you|he|she|they) (?:go|get|went|come|climb) (?:in|inside|down|up there|out there|back in)\b|\bgo in$/,
  /\b(?:before|until|if) (?:i|we|you|he|she|they) (?:start|enter|begin)\b(?! (?:the |a |my |this )?(?:talk|video|app|otis|crew|sign|download|update|episode)\b)/,
  /\b(?:can|may|should|do|could) (?:i|we) (?:start|begin|go|keep going|go ahead|continue)\b(?! (?:the|a|my|this|over|again|back|to the app)\b)/,
  /\bentrar (?:al|a la|a el|en el|en la|ahi|alli|aqui)\b(?! (?:app|aplicacion|cuenta|otis|sesion|sistema|perfil)\b)|\b(?:antes|despues) de entrar\b/,
  // Work time: "do i have to work monday", "do i get the holiday off"
  /\b(?:have|has|got|need|needs|supposed|make me|make us|making me|making us|gotta|got to|have to|has to|want me to) (?:to )?work\b(?! (?:on|in|with) (?:the |my |this )?(?:app|otis|phone)\b)/,
  /\b(?:day|days|holiday|holidays|monday|christmas|weekend|time|tiempo|dia) (?:off|libre)\b|\b(?:get|got|have) (?:the |a )?(?:day|holiday|weekend) off\b/,
  // Contact with something: "i had contact with it"
  /\b(?:had|made|came into|come into|got|get|in|skin|eye|direct|close) contact\b|\bcontact with (?:it|this|that|them|the stuff)\b/,
  // Reporting at work, and what comes after it: "who do i report it to", "can i get in trouble for reporting"
  /\b(?:get|got|getting|be|been|in|into|gets) (?:in |into )?trouble\b|\b(?:kicked|written|wrote|let go|fired|punished|yelled at|sent home)\b(?: \w+){0,3} for report\w*/,
  /\breported (?:it|this|that|him|her|them|a problem|the problem|an issue|the issue|a hazard)\b|\breport(?:ing)? (?:it|this|that|him|her|them)\b|\b(?:have|need|supposed) to report\b/,
  /\bwho (?:do|should|can|would|will|must|am) (?:i|we) (?:have to |supposed to |need to )?(?:report|notify|tell|call|go to)\b/,
  // Talking to a person: "i need to talk", "talk to someone"
  /\b(?:need|needs|want|wants|have|got|gotta|wanna|would like|like) (?:to )?talk\b(?! (?:about )?(?:the |this |a )?(?:app|otis|talk)\b)|\btalk(?:s|ing|in)? (?:to|with) (?:me|someone|somebody|anyone|you|nobody|no one|people)\b/,
  // Someone not answering a phone: "no contesta el celular"
  /\bno contesta (?:el|su|mi) (?:celular|telefono|cel)\b|\b(?:isnt|is not|not|aint|wont|didnt|stopped) (?:answering|picking up) (?:his|her|their|the|my) (?:phone|cell|celular)\b/,
  // Round 4. Something coming down, up high, out of touch: "it all crashed down", "stuck up there", "lost contact with 2"
  /(?<!\b(?:notifications?|notifs?|reminders?|emails?|messages?|texts?|updates?|alerts?|talks?|videos?) (?:only |all |just |still |always |keep |keeps )?)\b(?:crash\w*|came|coming|come|falling|fell|caving|caved) (?:down|in)\b(?! (?:the |a )?(?:middle|background|landscape|portrait|dark mode|light mode)\b)|\bstuck up (?:there|top|here|high)\b|\blost (?:contact|track|sight)\b|\blost (?:connection|signal) (?:with|of) (?!(?:the )?(?:app|server|internet|wifi)\b)/,
  /\bno (?:lo|la|los|las|le) (?:veo|vemos|encuentro|oigo|escucho)\b/,
  // Using the phone at work is a rule, not the app: "can i be on my phone at all", "otis puedo ver el celular"
  /\b(?:can|may|should|could) (?:i|we) (?:be on|use|look at|check|have|bring|carry|get on|text on) (?:my |the |a |our )?(?:phone|phones|cell|celular|cellphone)\b(?! (?:to|for) (?:the |a )?(?:app|otis|talk|sheet|crew sheet)\b)|\b(?:puedo|podemos|se puede) (?:ver|usar|traer|sacar|checar|revisar) (?:el|mi|su) (?:celular|telefono|cel)\b/,
  /\b(?:esta|estaba|sigue|se queda|se quedo|quedo) (?:bien |muy )?pegado\b|\b(?:esta|anda|se ve|va) (?:muy|bien|super) mal\b|\b(?:no )?se ve (?:muy )?(?:mal|bien)\W*$/,
  // "What do I do", anywhere: an emergency as often as anything ("otis what do i do its stuck", "now what do i do")
  /\b(?:what|que) (?:do|should|can|shall) (?:i|we) do\b(?! (?:if|when|to|about|with|in) (?:the |my )?(?:app|otis|it crashes|it freezes|talk|sheet|download|update)\b)|\bque (?:hago|hacemos|hacer)\b(?! (?:si|cuando|con) (?:la app|la aplicacion|otis)\b)|\bwhat now\b|\bnow what\b|\bahora que\b/,
  // A person going down, not knowing where they are, giving up: "im going down", "i dont know where i am", "no puedo mas"
  /\b(?:im|i am|i m|i)(?: (?:about to|gonna|going to|think im|think i am|feel like im|feel like i am))? (?:going|go|gonna go|goin) down\b|\b(?:i think )?(?:im|i am) (?:all |so |really )?(?:messed up|out of it|not right|off)\b|\bsomething (?:is )?(?:going on|happening|wrong) (?:with|to) me\b/,
  /\b(?:everything|things|it all|its all|it is all|all|everything is all)(?: is| are| was| keeps| started| just| went| goes| going| getting| turning| turned| gone)* (?:black|dark|white|blurry|fuzzy|spinning|red)\b|\ball i (?:can )?see is\b/,
  /\b(?:dont|do not|cant|cannot|didnt) (?:know|tell|see) where (?:i|we|he|she|they) (?:am|are|is|went)\b|\bwhere am i\b|\bwhere are we\b/,
  /\bi give up\b|\bi (?:cant|cannot|can not) (?:do|take|handle) (?:this|it) (?:anymore|no more)\b|\bno (?:puedo|aguanto) mas\b|\bya no (?:puedo|aguanto)\W*$|\bya no aguanto\b|\by (?:ya )?no puedo(?: mas)?\W*$/,
  /\bentro\b.{0,25}\bno (?:ha )?(?:sal(?:e|ido|io)|contesta|responde|se oye|se escucha|regresa|vuelve)\b|\bya no (?:sale|aparece)\W*$/,
  // Rights and lockout, in app words: "can i run it now", "do i have to give my name", "its 108 today", "puedo entrar"
  /(?<!\bhow )\b(?:can|should|do|could|may|must|shall) (?:i|we) (?:have to |need to |still )?(?:run|open|fix|use|change|say no|say|go|answer|tell|ask|work|put|give|show|send|take)\b(?! (?:the |my |this |a |an |in the |on the |to the |into the )?(?:new |different |another |other )?(?:app|otis|talk|talks|toolbox talks?|crew sign in|sign in|video|sheet|crew sheet|settings|account|email|language|spanish|english|photo|picture|data|password|notifications?|reminders?|group photo|name in the app|it in spanish|it in english|offline|without (?:signal|wifi|internet|data))\b)/,
  /\b(?:put|give|show|tell) (?:them |him |her |you |the boss )?(?:my |your )?(?:name|id|info|information|number|badge)\b(?! (?:in|on|into) (?:the |my )?(?:app|otis|account|profile|sheet|crew sheet)\b)|\b(?:photo|picture|pic|video|foto) (?:of|de) (?:it|this|that|him|her|eso|esto|el|ella)\b/,
  /\b(?:its|it is|is it|hay|esta en|estamos a|it says|says its|says it is|card says|it reads|reads|shows|marca) \d+\b(?! (?:percent|mb|gb|kb)\b)/,
  /(?<!\bno )\b(?:puedo|podemos|se puede|hay que|tengo que|tenemos que|debo|ya puedo|cuando puedo|lo puedo) (?:entrar|abrir|apagar|prender|meterme|meter)\b(?! (?:a |en |de )?(?:la app|la aplicacion|otis|mi cuenta|sesion|la cuenta)\b)|\blo (?:apago|abro|prendo|puedo abrir|apagamos)\b/,
  /\bwho (?:should|can|do|would|could) (?:i|we) (?:ask|tell|call|talk to|go to)\b|\bwhile (?:it is|its|it s|it was|its still) (?:running|on|going|moving|hot|live)\b|\b(?:it|this|that) (?:wont|will not|doesnt|does not|cant|didnt|did not) (?:shut|turn|power) (?:down|off)\b/,
  /\bbefore (?:i|we|you|he|she|they) (?:go|leave|head out)\W*$/,
  // Round 5. The person joined to the app's state, said in small words: "the app froze and i am too", "and me too",
  // "same with me", "y yo igual", "me and my phone are stuck", "el celular y yo estamos pegados". Any first-person
  // subject (i, im, me, yo, we) with "too", "igual" or "as well" after it, or "also" or "tambien" at the end, is how
  // the person is, not the app.
  /(?<!\b(?:on|to|for|with|at|by|from|para|a|con) )\b(?:i|im|i m|me|myself|yo|we|us|nosotros)(?: (?:am|is|are|was|were|m|be|been|feel|feeling|getting|got|going|gonna|kinda|so|really|just|all|now|still|probably|estoy|estamos|ando|andamos|me|se|quede|quedo|stuck|frozen|froze|down|lost|gone|hanging|dead|done|spinning|blank|black|dark|broke|broken|pegad[oa]s?|trabad[oa]s?|atorad[oa]s?|perdid[oa]s?|mal|also|tambien))* (?:too|igual|as well|aswell|tmb|tb)\b|\b(?:i|im|i m|me|yo|we|us|nosotros)(?: (?:am|is|are|was|were|m|estoy|estamos|ando))? (?:also|tambien)(?: (?:stuck|frozen|down|lost|gone|hanging|dead|pegad[oa]s?|trabad[oa]s?|atorad[oa]s?|perdid[oa]s?|mal))?$/,
  /\bsame (?:with|for|goes for|thing with|thing for|thing happening to|happening to|as) (?:me|us)\b|\bsame here\b|\b(?:igual|lo mismo) (?:que yo|conmigo|para mi|a mi)\b|\b(?:a mi|conmigo) (?:tambien|igual|lo mismo)\b|\b(?:and|y|n|but|pero|plus) (?:so )?(?:i am|im|i m|we are|were|yo|nosotros)(?: (?:am|is|are|estoy|estamos|ando))?$/,
  /\b(?:me|i|yo|we|us|myself)(?: and| y| n| plus| with| con) (?:my|the|mi|el|la|this|este|esta) (?:phone|cell|cellphone|iphone|android|tablet|ipad|app|otis|celular|cel|telefono|movil|aplicacion)\b|\b(?:phone|cell|cellphone|iphone|android|tablet|ipad|app|otis|celular|cel|telefono|movil|aplicacion) (?:and|y|n|plus) (?:me|i|yo|we|us|myself)(?: (?:both|are|were|r|estamos|seguimos|quedamos|nos|andamos|got|get|keep|kept|just|stuck|frozen|down|lost))\b/,
  // No answer for a time or a count, or on someone's phone: "no answer on my phone for 40 minutes", "tried the phone 5
  // times no answer", "no answer on the phone". Not "otis gives no answer for 2 minutes": that is OTIS not answering.
  /^(?!.*\b(?:otis|app|chat|chatbot|aplicacion)\b(?: \w+){0,3} no (?:answer|reply|response)\b)(?=.*\bno (?:answer|reply|response|one answers|one answered|one picks up)\b).*\b(?:\d+|a few|few|several|many|like \d+) (?:min|mins|minutes|hours?|hrs?|times|tries|calls)\b/,
  /\bno (?:answer|reply|response|one answer\w*) (?:on|from|at) (?:the|his|her|their) (?:phone|cell|celular|line|radio)\b|\b(?:tried|called|calling|call|try|trying|keep calling|kept calling|been calling|rang|ringing) (?:the|his|her|their|your) (?:phone|cell|celular|cellphone|radio)\b/,
  // Something crashing into a person, not finding the way, a swollen battery, a broken bone, messages telling you to quit
  /\bcrash\w* (?:into|in to|inta|against) (?:me|him|her|us|them|my|his|their|someone|somebody)\b/,
  /\b(?:cant|cannot|can not|couldnt|could not|dont|do not|didnt)(?: even)? (?:find|know|see|remember|tell) (?:the|my|our|which|a) way\b(?! to (?:the |my )?(?:settings|menu|page|change|delete|turn|sign|log|switch|update|save|share|find|get to (?:the |my )?(?:settings|menu|page)))|\blost (?:the|my|our) way\b|\bthe way (?:out|back|home)\b/,
  /\b(?:battery|bateria)\b.{0,25}\b(?:big|bigger|biggr|huge|swell\w*|swole|swollen|puff\w*|bulg\w*|fat|fatter|thick|thicker|expand\w*|grow\w*|hinchad\w*|inflad\w*|grande|gorda)\b|\b(?:phone|cell|celular|telefono|screen|back|case)\b.{0,20}\b(?:swell\w*|swollen|bulg\w*|puff\w*|popping off|lifting|hinchad\w*|inflad\w*)\b/,
  /\b(?:i|he|she|we|they)(?: think i| think he| think she)? (?:broke|busted|cracked|snapped|tore|fractured|twisted|dislocated|popped) (?:something|somethin|smth|sumthin|a bone|my (?!phone|screen|cell|app|iphone|ipad|tablet|charger|case)\w+|his \w+|her \w+)\b|\bsomething (?:is |got |just )?(?:broke|broken|snapped|cracked|popped)\b(?! (?:in|on|with) (?:the |my )?(?:app|otis|phone)\b)/,
  /\b(?:telling|told|tells|tell|texting|messaging|sending|keep sending|keeps sending) me (?:to )?(?:quit|leave|go away|die|kill|hurt|watch out|watch my back|shut up|stop|im dead|i am dead|they will|ill be)\b|\b(?:messages|texts|calls) (?:telling|saying|that say|that tell) me\b/,
  // OTIS or the app giving the go-ahead, in "i can" order: "otis says i can go in now", "the app said i can use it now",
  // "otis says it is ok if i do it now", "otis dice que lo puedo cambiar ahora". "Says" followed by a go-ahead never
  // counts as the app: it is a question about doing the work.
  /\b(?:says?|said|saying|sayin|tells? me|told me|telling me|tellin me|keeps telling me|dice|dijo|decia|me dice|me dijo|me esta diciendo)\b(?: (?:that|que|its|it|yes|yeah|yep|si|ok|okay|so|then|ya|lo|la|me|i|we|yo|you|all|now|ahora))*? (?:(?:i|we|yo|you) (?:can|could|may|am allowed to|are allowed to|get to|dont have to|do not have to|dont need to|do not need to|no longer have to|dont gotta|(?:dont|do not|no longer) need (?:it|them|that|this|one|a|an|any))|(?:yo )?(?:puedo|podemos|ya puedo|lo puedo|la puedo|se puede|no tengo que|no hay que|no necesito|entro|entre|entrar|meterme|empiezo|arranco)|(?:its|it is|is|im|i am|we are|were|todo esta|esta) (?:ok|okay|fine|safe|good|alright|clear|cleared|bien)(?: (?:to|if|so|now)\b|$)|to (?:go|start|enter|run|proceed|continue|go ahead|begin)(?: (?:in|inside|ahead|now|it|again|back)\b|$)|(?:good|ok|okay|safe|clear) to (?:go|enter|start|run|use|touch|open|remove|work))\b(?!(?: \w+){0,2} (?:the |my |el |la |mi |los |las |a |an )?(?:app|otis|language|languages|idioma|email|correo|password|contrasena|settings|ajustes|font|notifications?|notificaciones|account|cuenta|profile|perfil|talks?|charlas?|videos?|sheets?|hojas?|crew sign in|sign in|photos?|fotos?|offline|without (?:wifi|internet|signal|data))\b)/,
  /\b(?:i|we) (?:can|could|may|am allowed to|are allowed to|get to) (?:go|run|fix|open|use|start|remove|change|do|enter|turn|take|touch|skip|leave|work|keep going|keep working|cut|lift|move|restart|climb|unlock|pull|put|go ahead|proceed|continue)(?: (?:it|this|that|them|in|inside|up|down|back|out|ahead|on|off|again|without))*(?:(?: (?:now|again|yet|already|today|right now|ahora|ya))?$| (?:now|right now)\b)|\b(?:good|ok|okay|safe|clear) to go\b/,
  // A head count: "the other is still in", "no veo al otro", "the rest of them". Not "the other talk", "the other day".
  /\b(?:the|el|al|la|los|las|a los|a las|that|this) (?:other|otro|otra|otros|otras|others|rest|demas)\b(?! (?:talks?|pages?|tabs?|apps?|phones?|charlas?|days?|options?|languages?|idioma|videos?|episodes?|screens?|buttons?|sheets?|accounts?|emails?|menus?|settings|features?|versions?|weeks?|dia|semana|pagina|opcion|boton|pantalla|cuenta|of the (?:app|talks?|options?|settings))\b)/,
  // Who to send a photo of it to is a reporting question: "who do i send the photo to"
  /\bwho (?:do|should|can|would) (?:i|we) (?:send|give|show) (?:it|this|that|the (?:photo|picture|pic|video|pics|photos))(?: of it)? to\b/,
  // Distress: "ya no quiero nada", "ya no quiero seguir", "i dont want anything anymore". The safety answer, never support.
  /\bya no quiero (?:nada|hacer nada|seguir|vivir|estar aqui|estar aca|seguir aqui|seguir asi|saber nada|intentar|luchar|existir)\b|\bno quiero (?:vivir|seguir viviendo|seguir vivo|seguir viva|existir)\b|\b(?:i|we) (?:dont|do not|dont even) want (?:anything|nothing|to do anything|to do nothing|to go on|to keep going|to try|to be here|to live)(?: any ?more| no more)?\b/,
];

/**
 * Round 6: a second look, for sayings in app words that the lines above miss, each built as a rule rather than one
 * phrase: the person after a join ("and i did too", "y yo tampoco"), what OTIS or the app said with no app talk in it
 * (a go-ahead), not knowing where you are, someone else as "another" or "otro", no answer for a time in Spanish, a
 * swollen battery, a threat, signing for someone else, and lockout questions in Spanish. Taken only when nothing above
 * has already kept the message from the app, so the reasons given for a message stay the first ones found.
 */
const SECOND_LOOK: readonly RegExp[] = [
  // Round 6. The person after a join, in any form: "and i did too", "and im the same", "and me also now", "and i keep
  // spinning", "and so i did", "then i did", "and me to", "and i have been since 3am", "and me with it", "but im not".
  // A join (and, but, then, so, now, as, while) and a first-person subject that ends the message with a state word, a
  // helper ("did", "have", "am") or "too", "to", "also", "as well" is how the person is, not the app.
  new RegExp(
    `\\b${R6_JOIN}(?: (?:then|now|so|also|yeah|like))* ${R6_ME}(?: ${R6_HELPER})*(?: ${R6_END})(?: ${R6_TAIL})*$`,
  ),
  // The person first and the app after: "i just froze and so did the app", "i keep crashing and the app does too"
  new RegExp(
    `^(?:otis )?(?:i|im|i m|we|me)(?: (?:just|keep|keeps|kept|am|m|was|also|really|totally|got|get|went|started|been|have been))* (?:froze|frozen|freez\\w*|crash\\w*|stuck|spin\\w*|hang\\w*|hung|broke\\w*|blank|black|dark|glitch\\w*|down|dead|lost)\\b.*\\b(?:so (?:did|does|is|was|has|have|do)|(?:did|does|is|was|has|have|do) (?:too|to|also|as well))\\b`,
  ),
  /\bas (?:am|is|are|did|do|does|was|were|have|has) (?:i|me|we)\b/,
  // Spanish: "y yo tampoco", "y yo sigo igual", "y yo tambien estoy", "y yo no puedo ya", "pero yo no"
  /\b(?:y|pero|e|ni) (?:yo|nosotros)(?: (?:ya|no|tambien|tampoco|igual|sigo|seguimos|sigue|estoy|estamos|ando|andamos|me|nos|quede|quedo|quedamos|siento|puedo|podemos|pegad[oa]s?|trabad[oa]s?|atorad[oa]s?|perdid[oa]s?|mal|lo mismo|asi|mas|nada|todavia|aun|peor))+$/,
  // Someone else named only as "another" or "otro": "and another too", "y otro igual". Not "y otra vez", "another talk"
  /\b(?:and|y|n|but|pero|plus) (?:another|otro|otra)(?: (?:one|uno|una|guy|worker|person|mas))?\b(?! (?:vez|veces|time|times|thing|things|talk|talks|charla|charlas|page|pages|pagina|video|videos|error|errors|problem|problema|issue|question|pregunta|day|dia|app|aplicacion|phone|celular|account|cuenta|screen|pantalla|message|mensaje|update|download|option|opcion|link|enlace|sheet|hoja|tab|photo|foto|episode|episodio|notification|reminder)s?\b)/,
  // Not knowing where you are, said other ways, and a person in small words: "not sure where i am", "i dont know
  // where", "what is happening to me", "something happened to me", "que me esta pasando", "its just me left"
  /\b(?:not sure|no idea|unsure|dunno|idk|cant tell|cannot tell|dont know|do not know)(?: of)? where (?:i|im|we|he|she|they)(?: (?:am|are|is|went|at))?\b|\b(?:dont|do not|cant|cannot|didnt) know where\W*$|\bno se (?:donde|adonde) (?:esta|estoy|estamos|anda|quedo|se metio|se fue)\W*$/,
  /\b(?:what|whats|what is)(?: is)? (?:happening|going on|wrong|up) (?:with|to) me\b|\bsomething (?:is |just |has |)?(?:happened|happening|going on|off) (?:with|to) me\b|\bque me (?:esta |estoy |)?pas(?:a|ando|o)\b|\bi (?:dont|do not) know what to do\b|\b(?:just|only) me (?:left|here)\b|\bme left\W*$/,
  // Spanish distress and a person not talking: "ya no puedo hacer nada", "no puedo ya", "y yo no puedo", "no se ve
  // nada", "ya se fue", "y no habla". Not "la pantalla no se ve" or "otis no habla espanol".
  /\bya no puedo hacer nada\b(?! (?:en|con) (?:la app|la aplicacion|otis)\b)|\bno puedo ya\W*$|^(?:otis )?ya se (?:fue|murio|desmayo|cayo)\W*$|(?<!\b(?:pantalla|app|aplicacion|charla|video|foto|pagina|hoja)\b.{0,20})\bno se ve nada\b|\bno habla\b(?! (?:en )?(?:espanol|ingles|spanish|english)\b)/,
  // "Fine, but I'm not": "my phone is fine but i am not", "la app esta bien pero yo no"
  /\b(?:but|pero|tho|though) (?:i|im|i am|i m|yo|we|we are|were)(?: (?:am|m|are|estoy|estamos))? (?:not|no|aint)(?: (?:ok|okay|fine|good|alright|bien))?$/,
  // A leading "otis" and a stuck state for a time is a person ("otis stuck since 3am"); "otis is stuck for 40 min" is OTIS
  /^otis (?:stuck|hung|hanging|frozen|froze|down|lost|gone|dead)\b(?: (?:since|for|at|from|like|about|over|almost|around))+ (?:\d|an? (?:hour|while)|hours|minutes)/,
  // No answer since a clock time, nothing on the phone for a time, no answer in Spanish with a time or a count, and
  // his or her phone: "no contesta desde las 3pm", "20 minutes and still nothing on the phone", "mi celular 30 min sin
  // respuesta", "su celular sigue sin respuesta", "mi celular 5 min y nada"
  /\b(?:no (?:contesta|responde)|sin respuesta|no answer|not answering|hasnt answered|no reply)\b.{0,30}\b(?:desde las|since|from) \d{1,2} ?(?:am|pm)?\b|(?=.*\b\d+ ?(?:min|mins|minutes|minutos|hours?|hrs?|horas?)\b).*\b(?:nothing|nada) (?:on|from|en) (?:the|his|her|their|my|el|su|mi) (?:phone|cell|radio|celular|telefono)\b/,
  /^(?!.*\b(?:otis|app|chat|chatbot|aplicacion)\b(?: \w+){0,3} (?:sin respuesta|no contesta|no responde)\b)(?=.*\b(?:sin respuesta|no contesta|no responde|y nada)\b).*\b(?:\d+|unos|varios|muchas|como \d+) ?(?:min|mins|minutos|minutes|horas?|hrs?|veces|times|llamadas)\b/,
  /\bsu (?:celular|telefono|cel|radio)\b.{0,30}\b(?:no contesta|no responde|sin respuesta|sin contestar|se apago|nada|no suena|buzon)\b|\b\d+ ?(?:min|mins|minutos|minutes)\b.{0,10}\by nada\b/,
  // "No signal, lost": the signal is not what is lost ("no signal lost phone at 4 percent")
  /\bno (?:signal|service|bars|battery|wifi|senal)\b(?: \w+){0,3}? (?:lost|gone|perdid[oa])\b(?! (?:my |the |all |mi |la )?(?:signal|service|connection|data|sign|signatures?|sigs|links?|talks?|photos?|sheets?|info|account|progress|download|charlas?|hojas?))/,
  // What OTIS or the app said counts as the app only when it holds app talk: "the app says error 503", "otis says it
  // needs an update", "it says no internet". "Otis says go", "otis said run it", "otis says i will be fine", "the app
  // keeps asking me to start it", "otis dijo dale", "otis dice que esta bien entrar" are a go-ahead for the work.
  new RegExp(`\\b(?:says?|said|saying|sayin|tells? me|told me|telling me|tellin me|asking me|asks me|asked me|gave|gave me|gives|gives me|giving|giving me|dice|dijo|decia|me dice|me dijo|me esta diciendo|pide|me pide|me pidio)\\b(?!.*\\b(?:${R6_APP_TALK})\\b)`),
  // A swollen battery said without "battery": "my phone looks bigger than before", "my phone is so much bigger now"
  /\b(?:phone|cell|celular|telefono|iphone|android|tablet|ipad|case|funda)\b(?: (?!(?:text|font|letters?|letra|letras|words?|icons?|keyboard|buttons?|zoom\w*|videos?|photos?|pictures?|images?|pages?|display|screen|pantalla)\b)\w+){0,4} (?:big|bigger|biggr|huge|fat|fatter|thick|thicker|swole|grande|gorda|gordo|inflad\w*|hinchad\w*)\b/,
  /\bback of (?:my |the |his |her )?(?:phone|cell|celular|telefono|iphone)\b.{0,20}\b(?:popping|lifting|separating|coming (?:off|apart)|pushing|bulg\w*|swell\w*)\b|\bscreen (?:is |keeps )?(?:lifting|separating|popping off|pushing up|coming off)\b/,
  // A threat said with "should", "saying" or "next": "keeps telling me i should quit", "keeps saying i am next"
  /\b(?:telling|told|tells|tell|saying|says|said|texting|messaging) me(?: that)?(?: (?:i|you|u))? (?:(?:should|need to|have to|must|better|gotta|gonna|will|are|is|am) )?(?:quit|leave|go away|die|be next|next|dead|watch out|watch my back|regret)\b|\b(?:i am|im|you are|youre|ur|i will be|ill be|you will be|youll be) next\b/,
  // Out there with no phone or radio: "the app froze and i dont have my phone"
  /\b(?:i|we) (?:dont|do not|didnt|did not) (?:have|got|bring|carry) (?:my|a|the|our) (?:phone|cell|celular|radio)\b(?!.*\b(?:new|other|another|different|sign in|log in|account|switch|email)\b)/,
  // Signing for someone else, and a record that is not true: "can you put my name on the crew sheet", "can i sign
  // without watching the talk", "puedo firmar sin ver la charla", "mi nombre esta en la hoja y yo no"
  /\b(?:can|could|will|would|pls|please) (?:you|someone|somebody|he|she|they|u) (?:put|write|add|sign|mark) (?:me|my|his|her|their|our) (?:name |initials |signature )?(?:in|on|down|as|for)\b/,
  /\bsign\w*\b.{0,40}\bwithout (?:watching|seeing|being|going|attending|listening|doing|hearing|reading|taking)\b|\bfirm\w*\b.{0,40}\bsin (?:ver|estar|ir|asistir|haber|escuchar|oir|tomar)\b|\bmi nombre\b.{0,40}\b(?:y|pero) (?:yo )?no\b/,
  // A lockout or restart question to OTIS in Spanish: "otis ya lo puedo cambiar", "otis se puede iniciar ahora"
  /(?<!\bno )\b(?:puedo|podemos|se puede|ya puedo|lo puedo|la puedo|ya lo puedo|ya la puedo|ya se puede|ya podemos)(?: ya| ahora)? (?:iniciar|cambiar|cerrar|poner|quitar|mover|seguir|arrancar|empezar|tocar|prender|apagar|abrir|entrar|meter|meterme|usar|correr|echar|trabajar|subir|bajar|jalar|cortar|limpiar|reparar|arreglar)\b(?! (?:a |en |de |el |la |mi |las |los |mis )?(?:la app|app|la aplicacion|aplicacion|otis|cuenta|sesion|idioma|correo|contrasena|nombre|foto|fotos|charla|charlas|notificaciones|lenguaje|espanol|ingles|hoja|perfil|configuracion|ajustes|video|videos)\b)/,
];

/** The words that keep a message from being only about the app ("mike", "moving"). Empty for "the app keeps crashing". */
export function wordsNotOfTheApp(text: string): string[] {
  const all = words(text);
  const sayings = NOT_ABOUT_THE_APP.map((rule) => rule.exec(all)?.[0]).filter((said): said is string => Boolean(said));
  const found = [...sayings, ...strayState(text), ...appSplit(text).left.filter((word) => !appWord(word))];
  if (found.length > 0) return found;
  return SECOND_LOOK.map((rule) => rule.exec(all)?.[0]).filter((said): said is string => Boolean(said));
}

/**
 * True when every word of the message is one of the app's words (APP_THINGS, APP_SMALL_WORDS): "still broken",
 * "it closes when I tap Start crew sign-in". Used inside the report flow, where the talk is already about the app.
 */
export function onlyAppWords(text: string): boolean {
  return Boolean(words(text)) && wordsNotOfTheApp(text).length === 0;
}

/**
 * The gate for the tech-support paths: true when every word of the message is one of the app's words AND it names
 * the app or a part of it. "the app keeps crashing", "otis wont download", "la app se cierra sola", "how do I change
 * my email". False as soon as one word is about anything else ("the app froze and mike is not moving", "la app se
 * cerró y me torcí el tobillo", "the app froze and the floor is slippery"), and false when nothing of the app is named
 * ("im stuck", "its freezing", "the sign is missing"). It is a gate, not a match: it says nothing about whether the
 * app is going wrong.
 */
export function onlyAboutTheApp(text: string): boolean {
  if (wordsNotOfTheApp(text).length > 0) return false;
  const { left, phrase } = appSplit(withoutCalling(text));
  return phrase || left.some(appThing);
}

/** Slang and fast typing, said the way the support entries say it. An empty value drops the word. */
const SAID_AS: Readonly<Record<string, string>> = {
  dl: 'download', notifs: 'notifications', notif: 'notification', reminder: 'notification', reminders: 'notifications',
  comin: 'coming', thru: 'through', showin: 'showing', takin: 'taking', sigs: 'signatures', kickin: 'kicking', crashin: 'crashing',
  freezin: 'freezing', loadin: 'loading', workin: 'working', openin: 'opening', closin: 'closing', spinnin: 'spinning',
  laggin: 'lagging', glitchin: 'glitching', funsiona: 'funciona', switch: 'change', ocupa: '', mucho: '', trippin: 'acting up', descargo: 'descargar', aint: 'not',
  wtf: '', af: '', smh: '', rn: '', lol: '', idk: '', pls: '', plz: '', nomas: '', pon: '', eso: '',
};

/**
 * The message with slang and app-word typos written out ("otis wont dl", "notifs stopped comin thru", "la aplicasion
 * se cierra"), for finding the right support entry once the gate has said the message is only about the app. Never
 * used for the gate or the 911 rail.
 */
export function spelledOut(text: string): string {
  const fix = (word: string) => {
    if (word in SAID_AS) return SAID_AS[word];
    if (APP_THINGS.has(word) || APP_SMALL_WORDS.has(word)) return word;
    return typoTarget(word, TYPO_THINGS) ?? typoTarget(word, TYPO_SMALL) ?? word;
  };
  return words(text).split(' ').map(fix).filter(Boolean).join(' ');
}

/**
 * Every pattern in this file that is used with .test(). Exported so the tests can check that none carries the /g
 * flag: a /g pattern remembers where it stopped, and the same message would get a different answer the second time.
 */
export const TESTED_PATTERNS: readonly RegExp[] = [
  ...PROBLEM,
  ...NEEDS_THE_APP,
  NAMES_APP,
  ...ABOUT_THE_APP,
  ...SAFETY,
  ...SAFETY_UNLESS_APP.flatMap(({ hit, unless }) => (unless ? [hit, unless] : [hit])),
  APP_OR_OTIS,
  SOMEONE_ELSE,
  EL_IS_HE,
  A_NUMBER_IS_SOMEONE,
  SOFTWARE_FAILS,
  ...NOT_ABOUT_THE_APP,
  ...SECOND_LOOK,
  ...APP_THING_STEMS,
  ...APP_SMALL_STEMS,
];
