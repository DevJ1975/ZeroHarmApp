import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { AccessibilityInfo, StyleSheet } from 'react-native';

import { IntroSplash } from '@/components/IntroSplash';

const mockPlayer = { play: jest.fn(), pause: jest.fn(), muted: false, loop: true };

jest.mock('expo-video', () => {
  const { View } = jest.requireActual('react-native');
  return {
    useVideoPlayer: (_src: unknown, setup?: (p: typeof mockPlayer) => void) => {
      setup?.(mockPlayer);
      return mockPlayer;
    },
    VideoView: (props: object) => <View testID="intro-video" {...props} />,
  };
});
jest.mock('expo-status-bar', () => ({ StatusBar: () => null }));
jest.mock('react-native-safe-area-context', () => ({
  useSafeAreaInsets: () => ({ top: 20, bottom: 34, left: 0, right: 0 }),
}));

// The phone's light/dark setting; the native launch screen is yellow in light mode and navy in dark mode.
let mockScheme: 'light' | 'dark' = 'light';
jest.mock('react-native/Libraries/Utilities/useColorScheme', () => ({ __esModule: true, default: () => mockScheme }));

const FADE_OUT_MS = 350;

function setReduceMotion(on: boolean) {
  jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(on);
}

/** Advance fake time and flush React updates (timers, Animated frames, resolved promises). */
async function advance(ms: number) {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
}

/** The cover image (native-splash look-alike) is the only Image with an onLoadEnd handler. */
function coverImage() {
  const withLoad = screen.container.queryAll((i) => i.type === 'Image' && typeof i.props.onLoadEnd === 'function');
  expect(withLoad).toHaveLength(1);
  return withLoad[0];
}

async function renderIntro(reduceMotion = false) {
  setReduceMotion(reduceMotion);
  const onReady = jest.fn();
  const onDone = jest.fn();
  const utils = await render(<IntroSplash onReady={onReady} onDone={onDone} />);
  await act(async () => {}); // let isReduceMotionEnabled resolve
  return { onReady, onDone, ...utils };
}

/** Render, then fire the cover's onLoadEnd so the intro starts at t=0. */
async function startIntro(reduceMotion = false) {
  const r = await renderIntro(reduceMotion);
  await act(async () => {
    coverImage().props.onLoadEnd();
  });
  return r;
}

beforeEach(() => {
  jest.useFakeTimers();
  mockPlayer.play.mockClear();
  mockPlayer.pause.mockClear();
  mockPlayer.muted = false;
  mockPlayer.loop = true;
  mockScheme = 'light';
});

afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});

describe('IntroSplash: hiding the native launch screen (onReady)', () => {
  test('calls onReady once the cover image has loaded, before any fallback time passes', async () => {
    const { onReady } = await renderIntro();
    expect(onReady).not.toHaveBeenCalled();

    await act(async () => {
      coverImage().props.onLoadEnd();
    });
    expect(onReady).toHaveBeenCalledTimes(1);

    // The 1.5 s fallback firing later must not call it again.
    await advance(2000);
    expect(onReady).toHaveBeenCalledTimes(1);
  });

  test('calls onReady via the 1.5 s fallback if the cover image never loads', async () => {
    const { onReady } = await renderIntro();
    await advance(1499);
    expect(onReady).not.toHaveBeenCalled();
    await advance(1);
    expect(onReady).toHaveBeenCalledTimes(1);
  });

  test('the intro clock does not start until the cover is ready', async () => {
    const { onDone } = await renderIntro();
    // 1.5 s fallback, then 3.4 s of footage, then the 350 ms fade.
    await advance(1500); // fallback fires; the footage clock starts on the next commit
    await advance(3400 - 1);
    expect(onDone).not.toHaveBeenCalled();
    await advance(1 + FADE_OUT_MS + 50);
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});

describe('IntroSplash: normal motion', () => {
  test('plays the muted, non-looping video and finishes after ~3.4 s', async () => {
    const { onDone } = await startIntro(false);

    expect(screen.getByTestId('intro-video')).toBeTruthy();
    expect(mockPlayer.play).toHaveBeenCalledTimes(1);
    expect(mockPlayer.muted).toBe(true);
    expect(mockPlayer.loop).toBe(false);

    await advance(3399);
    expect(onDone).not.toHaveBeenCalled();

    await advance(1 + FADE_OUT_MS + 50);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(mockPlayer.pause).toHaveBeenCalled();
  });

  test('is still playing at 1.2 s (the Reduce Motion duration does not apply)', async () => {
    const { onDone } = await startIntro(false);
    await advance(1200 + FADE_OUT_MS + 100);
    expect(onDone).not.toHaveBeenCalled();
  });

  // Fixed: onDone/onReady now live in refs, so a new callback identity no longer restarts the 3.4 s timer or the fades.
  test('a new onDone identity does not restart the intro timer or animations', async () => {
    // A parent re-render (e.g. a colour-scheme change) can hand a new function; the intro must keep its 3.4 s clock.
    const { onDone, onReady, rerender } = await startIntro(false);
    await advance(3000);
    const onDone2 = jest.fn();
    await rerender(<IntroSplash onReady={onReady} onDone={onDone2} />);
    expect(mockPlayer.play).toHaveBeenCalledTimes(1); // the video is not restarted
    await advance(400 + FADE_OUT_MS + 50);
    expect(onDone2).toHaveBeenCalledTimes(1); // the latest callback is the one called
    expect(onDone).not.toHaveBeenCalled();
  });

  test('a new onReady identity after the cover is ready does not call onReady again', async () => {
    const { onReady, onDone, rerender } = await startIntro(false);
    expect(onReady).toHaveBeenCalledTimes(1);
    const onReady2 = jest.fn();
    await rerender(<IntroSplash onReady={onReady2} onDone={onDone} />);
    await advance(100);
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(onReady2).not.toHaveBeenCalled();
  });

  test('a new onReady before the cover is ready: only the latest one is called', async () => {
    const { onReady, onDone, rerender } = await renderIntro(false);
    const onReady2 = jest.fn();
    await rerender(<IntroSplash onReady={onReady2} onDone={onDone} />);
    await act(async () => {
      coverImage().props.onLoadEnd();
    });
    expect(onReady).not.toHaveBeenCalled();
    expect(onReady2).toHaveBeenCalledTimes(1);
  });
});

describe('IntroSplash: frame 1 matches the native launch screen', () => {
  /** The cover is the only pointerEvents="none" layer; it holds the splash look-alike. */
  function coverBackground() {
    const layers = screen.container.queryAll((i) => i.type === 'View' && i.props.pointerEvents === 'none');
    expect(layers).toHaveLength(1);
    return StyleSheet.flatten(layers[0].props.style).backgroundColor;
  }

  test('light mode: safety-yellow cover with the logo drawn for a yellow background', async () => {
    await renderIntro();
    expect(coverBackground()).toBe('#F5C400');
    expect(coverImage().props.source).toBe(require('../assets/video/logo-on-yellow.png'));
  });

  test('dark mode: navy cover with the logo drawn for a navy background', async () => {
    mockScheme = 'dark';
    await renderIntro();
    expect(coverBackground()).toBe('#13233F');
    expect(coverImage().props.source).toBe(require('../assets/video/logo-on-navy.png'));
  });
});

describe('IntroSplash: unmounting', () => {
  test('unmounting mid-intro cancels the auto-finish, so onDone never fires', async () => {
    const { onDone, unmount } = await startIntro(false);
    await advance(1000);
    await unmount();
    await advance(3400 + FADE_OUT_MS + 500);
    expect(onDone).not.toHaveBeenCalled();
  });
});

describe('IntroSplash: Reduce Motion', () => {
  test('does not render or play the video, and finishes after ~1.2 s', async () => {
    const { onDone } = await startIntro(true);

    expect(screen.queryByTestId('intro-video')).toBeNull();
    expect(mockPlayer.play).not.toHaveBeenCalled();

    await advance(1199);
    expect(onDone).not.toHaveBeenCalled();

    await advance(1 + FADE_OUT_MS + 50);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(mockPlayer.play).not.toHaveBeenCalled();
  });

  test('treats a failing Reduce Motion query as motion allowed', async () => {
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockRejectedValue(new Error('unavailable'));
    const onDone = jest.fn();
    await render(<IntroSplash onReady={jest.fn()} onDone={onDone} />);
    await act(async () => {});
    await act(async () => {
      coverImage().props.onLoadEnd();
    });
    expect(mockPlayer.play).toHaveBeenCalled();
    await advance(3400 + FADE_OUT_MS + 50);
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});

describe('IntroSplash: skipping', () => {
  test('tapping "Skip intro" ends the intro early and calls onDone after the fade', async () => {
    const { onDone } = await startIntro(false);
    await advance(500);

    await fireEvent.press(screen.getByLabelText('Skip intro'));
    expect(onDone).not.toHaveBeenCalled(); // waits for the 350 ms fade-out
    await advance(FADE_OUT_MS + 50);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(mockPlayer.pause).toHaveBeenCalled();
  });

  test('onDone is called exactly once when Skip is tapped twice and the timer also runs out', async () => {
    const { onDone } = await startIntro(false);
    const skip = screen.getByLabelText('Skip intro');
    await fireEvent.press(skip);
    await fireEvent.press(skip);
    await advance(FADE_OUT_MS + 50);
    await advance(5000); // past the 3.4 s auto-finish too
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  test('tapping anywhere on the intro also skips it', async () => {
    const { onDone } = await startIntro(false);
    await fireEvent.press(screen.getByLabelText('Zero Harm. Tap to skip the intro.'));
    await advance(FADE_OUT_MS + 50);
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  test('Skip has a 44 pt minimum touch target', async () => {
    await startIntro(false);
    const skip = screen.getByLabelText('Skip intro');
    expect(skip).toHaveStyle({ minHeight: 44 });
  });
});
