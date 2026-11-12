import { looksUrgent } from '@/lib/otis/safety';
import { asksAboutApp, looksLikeAppProblem, mentionsSafety, TESTED_PATTERNS } from '@/lib/support/intent';

/**
 * The spec for "is this message about the app going wrong?". A miss is cheap (the Report a problem button is always
 * there); a false alarm takes a safety question away from the safety answers. So both lists are long, and the quiet
 * list holds every ordinary safety question the 911 rail's own spec keeps quiet.
 */
describe('looksLikeAppProblem: must fire', () => {
  test.each([
    // plain requests for support, with the app named
    'report a bug in the app',
    'how do I contact app support',
    'contact Trainovate',
    'is there tech support for the Zero Harm app',
    'file a ticket for the app',
    'file a ticket about the app',
    'report a problem with the app',
    'I need to report an issue with OTIS',
    // the app and a failure word
    'the app crashed',
    'app keeps crashing',
    'the app is broken',
    'the app froze',
    'The App Crashed',
    'the app keeps freezing on my phone',
    'app wont open',
    "the app won't load",
    'the app just closes by itself',
    'the app is so slow',
    'this app is buggy',
    'app is laggy',
    'the app is down',
    'the app, it keeps crashing',
    'the app on my phone just keeps crashing',
    'the zero harm app stopped working after the update',
    'otis is not working',
    'OTIS is stuck',
    "OTIS won't answer",
    'otis crashed',
    'OTIS keeps freezing',
    'hey OTIS, the app keeps crashing',
    'the otis download is stuck',
    'the download in the app is stuck',
    'the app download failed',
    'notifications from the app are not working',
    "the app won't let me sign in",
    "I can't log in to the app",
    'the app logged me out',
    'the screen in the app froze',
    'the app screen went black',
    'white screen when I open the app',
    "the talk video in the app won't play",
    'the app is glitchy',
    'the app is lagging',
    'the app keeps logging me out',
    'the app is stuck on loading',
    'the app is in the wrong language',
    'the app says no connection',
    'this app sucks it never works',
    'my phone froze',
    'Zero Harm keeps crashing',
    'the zero harm app is not working',
    'otis download is stuck at 40%',
    'there is a bug in the app',
    'problem with the app',
    'something is wrong with the app',
    'I need help with the app',
    'it crashes every time I open the app',
    "I can't open the app",
    'cant use otis',
    'weather is not showing in the app',
    'the app closes when I tap Start crew sign-in',
    // notifications, sign-in sheets, signing in
    // parts of the app, with a failure only software has
    'this screen is broken',
    // things only an app does
    'phone is burning hot',
    'my phone gets hot',
    'OTIS gave me a wrong answer',
    'otis is wrong',
    // the 911 rail fires on these too; this rule still has to see them
    'app died',
    'the app is dead',
    'app blew up',
  ])('fires for %p', (text) => {
    expect(looksLikeAppProblem(text)).toBe(true);
  });

  test.each([
    'la app no funciona',
    'La aplicación no funciona',
    'la aplicación se cierra sola',
    'la app se cerró',
    'la app se cayó',
    'la app se traba',
    'la app está muy lenta',
    'la app ya no abre en mi teléfono',
    'no funciona la app',
    'se cierra la aplicación',
    'no puedo abrir la app',
    'OTIS no responde',
    'otis no funciona',
    'tengo un problema con la aplicación',
    'ayuda con la app',
    'hay un error en la app',
    'la descarga de OTIS se quedó trabada',
    'reportar un problema con la app',
    'necesito soporte técnico para la app',
    'no me llegan las notificaciones de la app',
    'la pantalla de la app se congeló',
    'la aplicación del teléfono no funciona',
    'se cierra cuando abro la app',
  ])('fires for Spanish %p', (text) => {
    expect(looksLikeAppProblem(text)).toBe(true);
  });
});

/**
 * These used to count without the app being named. Each word also has a floor or paperwork meaning (a gas monitor has
 * a screen, lockout requires notification, plants file tickets), so on its own it no longer takes a message away
 * from the safety answers. The chat screen still shows the matching help entry for most of them, through the support
 * search, when the message names no hazard: __tests__/otis-routing-served.test.ts checks that on the served KB.
 */
describe('looksLikeAppProblem: the app must be named', () => {
  test.each([
    'report a problem',
    'Report a problem.',
    'I want to report a problem',
    'how do I report a problem?',
    'report a problem please',
    'report a bug',
    'I need to report a bug',
    'file a ticket',
    'open a support ticket',
    'contact support',
    'how do I contact support?',
    'how do I reach tech support',
    'is there a help desk',
    'Zero Harm is not working',
    'the download is stuck',
    'download failed',
    'the download keeps stopping',
    'stuck on the download',
    'cant share the pdf',
    'bug report',
    'notifications are not working',
    'notifications not working right now',
    "I'm not getting notifications",
    'I get no notifications',
    "the sign-in sheet won't save",
    'my sign-in sheets are gone',
    'cant log in',
    "I can't sign in",
    "it won't let me sign in",
    'the login is broken',
    'it logged me out',
    'the screen froze',
    'the screen went black',
    'white screen',
    'blank screen when I open it',
    "the video won't play",
    "the talk won't load",
    'the page is blank',
    'cant get out of the screen',
    'the download is stuck at 0 percent',
    'stuck on loading',
    'loading forever',
    'video is burning my data',
    'reportar un problema',
    'quiero reportar un problema',
    'Reportar un error',
    'necesito soporte técnico',
    '¿cómo contacto a soporte?',
    'quiero levantar un ticket',
    'no me llegan las notificaciones',
    'las notificaciones no llegan',
    'no puedo iniciar sesión',
    'la pantalla se congeló',
    'pantalla en blanco',
    'el video no carga',
  ])('does not fire for %p on its own', (text) => {
    expect(looksLikeAppProblem(text)).toBe(false);
  });
});

describe('looksLikeAppProblem: must stay quiet', () => {
  test.each([
    // named in the design: safety questions that hold report, problem, broken or not working
    'who do I report a near miss to',
    'how do I write an accident report',
    'the guard is broken',
    'the e-stop is not working',
    'there is a problem with the forklift brakes',
    'how do I troubleshoot the conveyor',
    // reporting, on the floor
    'how do I report a problem with the forklift',
    'I need to report a problem to my supervisor',
    'report a problem I saw on the line',
    'how do I report a safety problem',
    'report an injury',
    'how do I report a hazard to my supervisor',
    'who do I report an issue with the guard to',
    'file a ticket for the broken guard',
    'do I need a ticket to drive the forklift',
    'send a ticket to maintenance for the guard',
    'tech support for the conveyor PLC',
    'the scale is stuck at 40 percent',
    'the door keeps closing by itself',
    'the press keeps crashing down',
    // broken, stuck, not working: equipment
    'the emergency stop button is stuck',
    'the conveyor keeps stopping',
    'the alarm is not working',
    'the eyewash is not working',
    'the light curtain is broken',
    'my harness is broken',
    'the machine is down',
    "the press won't start",
    "the truck won't load",
    'the freezer door is stuck',
    'the forklift crashed into the rack',
    'the gas monitor screen is broken',
    'the screen guard on the grinder is missing',
    'error on the conveyor display',
    'it crashed right now',
    'it is not working',
    'help',
    // the app or OTIS is named, but the trouble is on the floor
    'the app says the guard is broken, what do I do',
    'OTIS, the e-stop is not working',
    'OTIS what do I do if the guard is broken',
    'otis my harness is broken',
    'OTIS, it is stuck',
    'hey otis the conveyor is stuck',
    'OTIS I have a problem with my back',
    'otis problem with the forklift brakes',
    'OTIS, is it wrong to bypass a guard',
    'what does OTIS say about ladders',
    'can OTIS help with lockout',
    'the app is on fire lol',
    'the app hurt my eyes',
    // look-alikes
    'the Otis elevator is stuck',
    'the emergency notification system is not working',
    'what is the notification rule for a fatality',
    'how do I download the OSHA 300 form',
    'where do I sign in for training',
    'should I never sign in for a coworker',
    'the roof needs support',
    'does it support the load',
    'I found a bug in the flour',
    'the video shows a broken guard',
    'the safety talk was about a broken ladder',
    'is there a problem with using a ladder on a scaffold',
    'scope and application of the lockout standard',
    // Spanish
    'el montacargas no funciona',
    'la guarda está rota',
    'la puerta se cierra sola',
    '¿cómo reporto un accidente?',
    'reportar una falla en la máquina',
    'reportar un problema con el montacargas',
    'hay un problema con los frenos del montacargas',
    'el paro de emergencia no sirve',
    'se cayó de la escalera',
    'la banda se traba',
    'la descarga del camión está lenta',
    'el sistema de notificación de emergencia no funciona',
  ])('does not fire for %p', (text) => {
    expect(looksLikeAppProblem(text)).toBe(false);
  });

  // Every ordinary question the 911 rail's spec keeps quiet (otis-safety.test.ts) is a safety question here too.
  test.each([
    'how often do forklifts need inspection', 'what is the OSHA rule for guardrail height', 'what PPE for welding',
    'how do I fill out a JSA', 'toolbox talk on heat stress', 'how do I inspect a harness before use',
    'who do I report a near miss to', 'when is my CPR training due', 'where do I find the SDS for bleach',
    'how do I use a fire extinguisher', 'how often should eyewash stations be flushed', 'first aid kit requirements',
    'bloodborne pathogens training', 'what is a wheel chock', 'chocking the wheels on a trailer',
    'flame resistant clothing requirements', 'how do I bleed the hydraulic lines', 'suicide prevention training',
    'aed inspection checklist', 'how do I write an accident report', 'smoke detector batteries',
    'fall arrest system inspection', 'how do I calibrate the gas monitor', 'what is a bump test for a gas detector',
    'where is the emergency stop', 'how often should lanyards be replaced', 'how do I prevent electrocution',
    'active shooter training', 'how do I troubleshoot the conveyor', 'sense of humor in toolbox talks',
    '¿cómo uso el extintor?', '¿qué EPP necesito para soldar?', '¿dónde está el botiquín?', 'paro de emergencia',
    'ruta de evacuación', 'prevención de incendios', '¿cómo se usa el lavaojos?',
  ])('does not fire for routine %p', (text) => {
    expect(looksLikeAppProblem(text)).toBe(false);
  });

  test.each(['He is not breathing', 'my hand is caught in the conveyor', 'se cayó de la escalera', 'there is a fire', 'chest pain', 'he collapsed', 'no respira'])(
    'does not fire for the emergency %p',
    (text) => {
      expect(looksLikeAppProblem(text)).toBe(false);
    },
  );
});

/**
 * From the review of the first version: real safety and emergency messages that the app rule took. None may fire.
 * The full order (rail, support, safety search) for each is checked on the served KB in otis-routing-served.test.ts.
 */
describe('looksLikeAppProblem: equipment, paperwork and lockout words never count alone', () => {
  test.each([
    // emergencies with an equipment failure in them
    'the press glitched and came down on his hand',
    'the light curtain glitched and the press cycled on her arm',
    'the gas monitor screen went blank and Tom is not answering from inside the tank',
    'the crew got no notification and they started the line with Luis still working on it',
    'the buggy rolled on top of him',
    'a guy is stuck at the loading dock between the trailer and the wall',
    // "report a problem" and then a hazard
    'I need to report a problem, the guard on the saw is missing',
    'I want to report an issue. There is a spill in aisle 4',
    'How do I report a problem? My supervisor ignores safety complaints',
    'report a problem: the dock plate is cracked',
    'I have to report an issue, who do I tell about a frayed sling',
    '¿Dónde reporto un problema?',
    'necesito reportar un problema, el montacargas no tiene frenos',
    'quiero reportar un problema. La guarda de la sierra no está',
    // screens, sheets, videos, signatures on equipment and paperwork
    'the gas monitor screen is blank, can I still enter the tank?',
    'the forklift display screen went black, is it safe to drive',
    'the crane LMI screen is frozen, can we still make the pick',
    'the backup camera screen is not showing anything, can I still drive the forklift',
    'the safety data sheet is blank for this chemical',
    'the inspection sheet is blank, do I still need to sign it',
    'I can not find the sheet for this chemical',
    'we cannot find the signature of the authorized employee on the permit',
    'I did not see the video on forklift safety, can I still drive',
    'can I never save a signature for a coworker on the permit',
    'the fusible link did not open on the fire door',
    'what is the white screen around the welding booth for',
    'do I need a black screen for welding in the shop',
    // lockout and permit words
    'we did not get notification of the lockout before they started work',
    'the crew did not receive notification before the equipment was re-energized',
    'workers got no notification before the line restarted, is that a violation',
    'employee notification is missing from our lockout procedure',
    'the confined space sign in sheet is missing, can we still enter',
    'visitors can not sign in without safety glasses, right?',
    'my coworker will not sign in on the confined space permit',
    'I have a problem with the application of lockout on the mixer',
    'is there an error in the application of the tag if the lock is missing',
    'tengo un problema con la aplicación del candado en la prensa',
    'hay un error en la aplicación del bloqueo y etiquetado',
    'the gas monitor download failed at the docking station, can I still use it',
    'zero harm is not working at our plant, the crew does not buy in',
    'is there a problem with zero harm as a goal',
    'zero harm no funciona en mi planta',
    'otis is that stuck valve dangerous',
    'otis is it still broken if I tape the cord',
    // floor meanings of glitch, buggy, lagging, force close, "me out", loading, setup, reach, ticket, bug
    'is the old pipe lagging asbestos',
    'how do I install lagging in a trench',
    'how do I operate a concrete buggy safely',
    'does the power buggy operator need training',
    'the robot arm is glitching and moving on its own',
    'the light curtain glitched and the press cycled',
    'can I force close a stuck gate valve',
    'the foreman booted me out of the area for refusing unsafe work, what are my rights',
    'my supervisor kicked me out for not wearing a hard hat, can he do that',
    'my coworker signed me out of the confined space log while I was still inside',
    'a trailer is stuck at the loading dock, can I push it with the forklift',
    'a pallet is stuck on the loading dock plate',
    'the die is stuck at setup, can I reach in',
    'what ladder do I use to reach the support beams',
    'how do I safely reach the support bracket on the mezzanine',
    'I put in a ticket and maintenance still has not fixed the guard',
    'do I need to open a ticket before I lock out the mixer',
    'hay que levantar un ticket para arreglar la guarda',
    'how do I report a bug in the flour bin',
    'the e-stop is glitching',
    'the conveyor keeps glitching and starts by itself',
    'the light curtain is glitchy, can we keep running',
    'the forklift is buggy, the brakes stick',
    'is the lagging on the steam pipe asbestos',
    'pipe lagging is falling off, is it safe to touch',
    'the crane remote is lagging',
    'the robot cell screen went black and the arm is still moving',
    'the HMI screen froze while the press was cycling',
    'the vibrating screen will not open, how do I lock it out',
    'my coworker signed me out of the confined space permit while I was inside',
    'the permit app crashed, is it ok to enter the confined space without a permit',
    'our gas monitor app is not working, can I enter the tank',
    "I can't find the sheet for acetone",
    'the emergency phone at the dock is not working',
  ])('does not fire for %p', (text) => {
    expect(looksLikeAppProblem(text)).toBe(false);
  });
});

describe('mentionsSafety', () => {
  test.each([
    'I need to report a problem, the guard on the saw is missing',
    'forklift 3 has no brakes and they are still using it',
    'the app froze, can I still enter the tank',
    'how do I lock out the mixer',
    'quiero reportar un problema. La guarda de la sierra no está',
    "I can't find the sheet for acetone",
    'who do I report a near miss to',
  ])('is true for %p', (text) => {
    expect(mentionsSafety(text)).toBe(true);
  });

  test.each([
    'the app keeps crashing',
    'the talk is locked',
    'la firma no se guarda',
    'no se guarda la hoja de asistencia',
    'heat card missing',
    'the talk will not load',
    'I got locked out of the app',
    'the app boots me out',
    'how do I find past talks',
    'report a problem',
    'what is OTIS',
  ])('is false for %p', (text) => {
    expect(mentionsSafety(text)).toBe(false);
  });
});

/**
 * Where the two rules overlap. The screen shows the banner first whenever the first column is true, and then takes
 * no support path at all, whatever the second column says.
 */
describe('911 rail and app-problem rule on the same message', () => {
  test.each([
    // [message, 911 banner, app problem]
    ['I need help with the app', true, true],
    ['help', true, false],
    ['ayuda con la app', true, true],
    ['app died', true, true],
    ['the app is dead', true, true],
    ['it crashed right now', true, false],
    ['notifications not working right now', true, false],
    ['the app is on fire lol', true, false],
    ['video is burning my data', true, false],
    ['phone is burning hot', true, true],
    ['app blew up', true, true],
    ['the app hurt my eyes', true, false],
    ['cant get out of the screen', true, false],
    ['la app se cayó', true, true],
    ['the app crashed', false, true],
    ['app keeps crashing', false, true],
    ['the app is broken', false, true],
    ['the app froze', false, true],
    ['report a problem', false, false],
    ['report a bug', false, false],
    ['file a ticket', false, false],
    ['contact support', false, false],
    ['otis is not working', false, true],
    ['la app no funciona', false, true],
    ['reportar un problema', false, false],
    ["the app crashed and he's not breathing", true, true],
  ] as const)('%p: 911 %p, app problem %p', (text, urgent, app) => {
    expect(looksUrgent(text)).toBe(urgent);
    expect(looksLikeAppProblem(text)).toBe(app);
  });
});

describe('looksLikeAppProblem: input handling', () => {
  test('no pattern used with .test() carries the /g flag', () => {
    expect(TESTED_PATTERNS.length).toBeGreaterThan(20);
    expect(TESTED_PATTERNS.filter((rule) => rule.global || rule.sticky)).toEqual([]);
  });

  test('gives the same answer on repeated calls (no regex state carried between messages)', () => {
    expect([1, 2, 3].map(() => looksLikeAppProblem('the app crashed'))).toEqual([true, true, true]);
    expect(looksLikeAppProblem('the guard is broken')).toBe(false);
    expect([1, 2, 3].map(() => looksLikeAppProblem('hey otis, the app keeps crashing'))).toEqual([true, true, true]);
    expect([1, 2].map(() => looksLikeAppProblem('the Otis elevator is stuck'))).toEqual([false, false]);
    expect([1, 2, 3].map(() => asksAboutApp('what is OTIS'))).toEqual([true, true, true]);
  });

  test('is case-insensitive and ignores accents and curly apostrophes', () => {
    expect(looksLikeAppProblem('THE APP CRASHED')).toBe(true);
    expect(looksLikeAppProblem('LA APLICACION NO FUNCIONA')).toBe(true);
    expect(looksLikeAppProblem('the app won’t open')).toBe(true);
  });

  test('empty and odd input is quiet', () => {
    for (const text of ['', '   ', '?!', '12345', 'app', 'otis', 'OTIS?']) expect(looksLikeAppProblem(text)).toBe(false);
  });

  test('finds the complaint inside a longer message', () => {
    expect(looksLikeAppProblem('We did the toolbox talk this morning and then the app froze when I tried to save the sheet')).toBe(true);
  });

  test('a long message is checked quickly', () => {
    const long = `${'the guard on the press is not working and the app says to lock out '.repeat(60)}`;
    const started = Date.now();
    expect(looksLikeAppProblem(long)).toBe(false);
    expect(Date.now() - started).toBeLessThan(500);
  });
});

describe('asksAboutApp', () => {
  test.each([
    'what is OTIS',
    "what's otis?",
    'what can OTIS do',
    'who made this app',
    'how does OTIS work',
    'how do I use the app',
    'how do I run a toolbox talk in the app',
    'where are past talks in the app',
    'is the app free',
    'does OTIS work offline',
    '¿qué es OTIS?',
    '¿cómo funciona la app?',
    'cómo uso la aplicación',
    'la app es gratis',
  ])('is true for %p', (text) => {
    expect(asksAboutApp(text)).toBe(true);
  });

  test.each([
    'what does OTIS say about ladders',
    'can OTIS help with lockout',
    'OTIS, what PPE for welding',
    'how do I use a fire extinguisher',
    'what is lockout tagout',
    'is the guard required',
    'the Otis elevator inspection',
    '¿cómo uso el extintor?',
    '',
  ])('is false for %p', (text) => {
    expect(asksAboutApp(text)).toBe(false);
  });
});
