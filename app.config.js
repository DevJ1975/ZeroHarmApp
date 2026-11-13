/**
 * app.json holds the settings. This file only changes what must differ from one kind of build to another:
 * - Push notifications use Apple's production service when EAS builds the "production" profile.
 * - Builds for testers and for the store leave out Android's "draw over other apps" permission. The app never
 *   uses it. A development build keeps it, because React Native's developer tools ask for it.
 *
 * One permission is left in on purpose: WRITE_EXTERNAL_STORAGE. On Android 7, 8 and 9 the camera (the crew photo
 * on the sign-in sheet) will not open without it. Newer Android versions ignore it. Do not add it to
 * android.blockedPermissions in app.json while the app still runs on those versions.
 */

// The EAS profiles that make a development build (developmentClient in eas.json).
const DEVELOPMENT_PROFILES = ['development', 'simulator'];

module.exports = ({ config }) => {
  // EAS sets this while it builds. It is not set for a build made on this computer, which is treated as development.
  const profile = process.env.EAS_BUILD_PROFILE;
  const production = profile === 'production';
  const development = !profile || DEVELOPMENT_PROFILES.includes(profile);
  return {
    ...config,
    android: {
      ...config.android,
      blockedPermissions: [
        ...(config.android?.blockedPermissions ?? []),
        ...(development ? [] : ['android.permission.SYSTEM_ALERT_WINDOW']),
      ],
    },
    plugins: config.plugins.map((p) =>
      Array.isArray(p) && p[0] === 'onesignal-expo-plugin' ? [p[0], { ...p[1], mode: production ? 'production' : 'development' }] : p,
    ),
  };
};
